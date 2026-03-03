from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.deps import get_current_user
from app.domain.models import APIError, Booking, Entitlement, Product, Slot
from app.services.booking import create_booking

router = APIRouter(prefix="/api/booking", tags=["booking"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _consume_entitlement(db: Session, user_id: UUID, kind: str) -> bool:
    """
    Atomically consumes 1 unit from the earliest expiring entitlement of given kind.
    Returns False if not available.
    """
    now = _now_utc()

    ent = db.scalar(
        select(Entitlement)
        .where(
            Entitlement.user_id == user_id,
            Entitlement.kind == kind,
            Entitlement.qty_used < Entitlement.qty_total,
            Entitlement.valid_from <= now,
            or_(Entitlement.valid_to.is_(None), Entitlement.valid_to >= now),
        )
        # Prefer those expiring sooner (FIFO by expiry), then older ones.
        .order_by(Entitlement.valid_to.is_(None), Entitlement.valid_to, Entitlement.created_at)
        .with_for_update(of=Entitlement)
    )
    if not ent:
        return False

    ent.qty_used += 1
    return True


@router.get("/slots")
def get_slots(db: Session = Depends(get_db)):
    rows = Repo(db).list_open_slots()
    return {
        "data": [
            {
                "id": str(s.id),
                "starts_at_utc": s.starts_at_utc.isoformat(),
                "duration_min": s.duration_min,
                "title": s.title,
            }
            for s in rows
        ]
    }


@router.post("/slots/{slot_id}/reserve")
def reserve(slot_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    MVP reserve: does not lock the slot (no reservation table yet).
    It tells whether user can book right now (has booking_access) or needs payment.
    """
    slot = db.get(Slot, slot_id)
    if not slot or slot.status != "open":
        raise APIError("SLOT_NOT_FOUND", "Slot not available", status_code=404)

    # Check if user already has booking_access remaining (without consuming)
    now = _now_utc()
    has_access = (
        db.scalar(
            select(Entitlement.id)
            .where(
                Entitlement.user_id == user.id,
                Entitlement.kind == "booking_access",
                Entitlement.qty_used < Entitlement.qty_total,
                Entitlement.valid_from <= now,
                or_(Entitlement.valid_to.is_(None), Entitlement.valid_to >= now),
            )
            .limit(1)
        )
        is not None
    )

    if has_access:
        return {"data": {"slot_id": str(slot_id), "status": "ready_to_book"}}

    booking_product = db.scalar(
        select(Product).where(and_(Product.type == "booking", Product.active.is_(True))).limit(1)
    )
    return {
        "data": {
            "slot_id": str(slot_id),
            "status": "payment_required",
            "booking_product_id": str(booking_product.id) if booking_product else None,
            "pricing_url": "/pricing",
        }
    }


@router.post("/slots/{slot_id}/book")
def book(slot_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Requires booking_access entitlement.
    Consumption + slot booking happen in the same transaction so failures rollback consumption.
    """
    try:
        # Consume booking entitlement first (will rollback on failure below)
        if not _consume_entitlement(db, user.id, "booking_access"):
            raise APIError(
                "NO_BOOKING_ACCESS",
                "No consultation credits left. Please purchase a consultation slot.",
                {"pricing_url": "/pricing"},
                status_code=402,
            )

        booking = create_booking(db, user.id, slot_id)
        db.commit()
        return {"data": {"booking_id": str(booking.id), "status": booking.status}}

    except APIError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc


@router.get("/my")
def my_bookings(user=Depends(get_current_user), db: Session = Depends(get_db)):
    # include slot info, meeting_url only for own bookings
    stmt = (
        select(Booking, Slot)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc())
    )
    rows = db.execute(stmt).all()

    out = []
    for b, s in rows:
        out.append(
            {
                "id": str(b.id),
                "slot_id": str(b.slot_id),
                "status": b.status,
                "created_at": b.created_at.isoformat(),
                "slot": {
                    "starts_at_utc": s.starts_at_utc.isoformat(),
                    "duration_min": s.duration_min,
                    "title": s.title,
                    "meeting_provider": s.meeting_provider,
                    "meeting_url": s.meeting_url if b.status == "confirmed" else None,
                },
            }
        )

    return {"data": out}


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    MVP cancel: marks booking cancelled and re-opens the slot if it was booked.
    Refund flow is not implemented here.
    """
    try:
        booking = db.get(Booking, booking_id)
        if not booking or booking.user_id != user.id:
            raise APIError("NOT_FOUND", "Booking not found", status_code=404)

        if booking.status != "confirmed":
            raise APIError("INVALID_STATE", "Booking cannot be cancelled", status_code=409)

        slot = db.get(Slot, booking.slot_id, with_for_update=True)
        booking.status = "cancelled"

        if slot and slot.status == "booked":
            slot.status = "open"

        db.commit()
        return {"data": {"id": str(booking_id), "status": "cancelled"}}

    except APIError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc
