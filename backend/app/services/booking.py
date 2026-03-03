from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.domain.models import APIError


def create_booking(db: Session, user_id: UUID, slot_id: UUID, note: str | None = None):
    """
    Creates a confirmed booking for an open slot.
    Slot locking and status change happen in Repo.book_slot().

    Transaction management (commit/rollback) must be handled by the caller.
    """
    repo = Repo(db)

    # Normalize note
    if note is not None:
        note = note.strip()
        if not note:
            note = None
        # hard guard to avoid accidental huge payloads
        if note is not None and len(note) > 2000:
            raise APIError("NOTE_TOO_LONG", "Client note is too long", {"max_len": 2000}, status_code=422)

    try:
        booking = repo.book_slot(user_id, slot_id)

        # Attach note if provided
        if note is not None:
            booking.client_note = note
            db.flush()

        return booking

    except (ValueError, IntegrityError) as exc:
        # ValueError: slot missing or not open
        # IntegrityError: uq_booking_slot_id collision in race
        raise APIError("SLOT_UNAVAILABLE", "Slot already booked or not available", status_code=409) from exc
