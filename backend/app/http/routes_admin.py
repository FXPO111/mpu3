from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_roles
from app.domain.models import Product, Slot, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/products")
def create_product(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_roles("admin", "consultant"))):
    row = Product(**payload)
    db.add(row)
    db.commit()
    return {"data": {"id": str(row.id)}}


@router.get("/users")
def users(db: Session = Depends(get_db), _admin=Depends(require_roles("admin", "consultant"))):
    rows = db.scalars(select(User)).all()
    return {"data": [{"id": str(u.id), "email": u.email, "role": u.role, "status": u.status} for u in rows]}


@router.post("/slots")
def create_slot(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_roles("admin", "consultant"))):
    payload.setdefault("starts_at_utc", datetime.fromisoformat(payload["starts_at_utc"]))
    row = Slot(**payload)
    db.add(row)
    db.commit()
    return {"data": {"id": str(row.id)}}