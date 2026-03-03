from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Tuple

from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.domain.models import APIError


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _int_meta(meta: dict[str, Any], key: str, default: int) -> int:
    v = meta.get(key, default)
    try:
        v = int(v)
    except Exception as exc:
        raise APIError(
            "BAD_PRODUCT_METADATA",
            f"Product metadata '{key}' must be an integer",
            {"key": key},
            status_code=422,
        ) from exc
    return v


def _entitlement_for_product(product) -> Tuple[str, int, int | None]:
    """
    Returns (entitlement_kind, qty_total, valid_days).

    Contract:
      - ai_pack: metadata.credits optional (default 50)
                metadata.valid_days optional
      - booking: metadata.qty optional (default 1)
                metadata.valid_days optional
    """
    meta = getattr(product, "metadata_json", None) or {}
    ptype = product.type

    if ptype == "ai_pack":
        credits = _int_meta(meta, "credits", 50)
        if credits <= 0:
            raise APIError(
                "BAD_PRODUCT_METADATA",
                "AI credits must be > 0",
                {"credits": credits},
                status_code=422,
            )
        valid_days = meta.get("valid_days")
        if valid_days is not None:
            valid_days = _int_meta(meta, "valid_days", 0)
            if valid_days <= 0:
                valid_days = None
        return ("ai_credits", credits, valid_days)

    if ptype == "booking":
        qty = _int_meta(meta, "qty", 1)
        if qty <= 0:
            raise APIError(
                "BAD_PRODUCT_METADATA",
                "Booking qty must be > 0",
                {"qty": qty},
                status_code=422,
            )
        valid_days = meta.get("valid_days")
        if valid_days is not None:
            valid_days = _int_meta(meta, "valid_days", 0)
            if valid_days <= 0:
                valid_days = None
        return ("booking_access", qty, valid_days)

    raise APIError(
        "UNSUPPORTED_PRODUCT_TYPE",
        "Unsupported product type",
        {"type": ptype},
        status_code=422,
    )


def _program_metadata(product) -> tuple[int, int]:
    meta = getattr(product, "metadata_json", None) or {}
    valid_days = _int_meta(meta, "valid_days", 0)
    ai_credits = _int_meta(meta, "ai_credits", 0)

    if valid_days <= 0:
        raise APIError(
            "BAD_PRODUCT_METADATA",
            "Program valid_days must be > 0",
            {"valid_days": valid_days},
            status_code=422,
        )
    if ai_credits < 0:
        raise APIError(
            "BAD_PRODUCT_METADATA",
            "Program ai_credits must be >= 0",
            {"ai_credits": ai_credits},
            status_code=422,
        )

    return valid_days, ai_credits


def apply_paid_event(db: Session, provider_ref: str) -> None:
    """
    Idempotent: if order already marked paid, exits.
    Grants entitlements strictly based on Product.type + Product.metadata_json.
    """
    repo = Repo(db)

    order = repo.find_order_by_provider_ref(provider_ref)
    if not order:
        raise APIError("ORDER_NOT_FOUND", "Order for provider reference not found", status_code=404)

    # idempotency
    if order.status == "paid":
        return

    product = order.product
    if not product or not getattr(product, "active", True):
        raise APIError("PRODUCT_NOT_FOUND", "Product not found or inactive", status_code=404)

    now = _now_utc()

    if product.type == "program":
        valid_days, ai_credits = _program_metadata(product)
        valid_to = now + timedelta(days=int(valid_days))

        access = repo.grant_entitlement_once(order, "program_access", 1)
        access.valid_from = now
        if access.valid_to is None:
            access.valid_to = valid_to

        if ai_credits > 0:
            credits = repo.grant_entitlement_once(order, "ai_credits", ai_credits)
            credits.valid_from = now
            if credits.valid_to is None:
                credits.valid_to = valid_to
    else:
        kind, qty_total, valid_days = _entitlement_for_product(product)

        ent = repo.grant_entitlement_once(order, kind, qty_total)
        ent.valid_from = now
        if valid_days is not None and ent.valid_to is None:
            ent.valid_to = now + timedelta(days=int(valid_days))

    if db is not None:
        db.flush()