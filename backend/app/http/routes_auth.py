from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.deps import get_current_user
from app.domain.models import APIError, LoginIn, RegisterIn
from app.security.auth import create_access_token, hash_password, verify_password
from app.security.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _norm_locale(locale: str) -> str:
    loc = (locale or "de").strip().lower()
    return "de" if loc.startswith("de") else "en"


def _user_status_value(user) -> str:
    # supports both Enum and plain string
    st = getattr(user, "status", "active")
    return getattr(st, "value", st) or "active"


@router.post("/register")
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterIn, db: Session = Depends(get_db)):
    repo = Repo(db)

    if repo.get_user_by_email(payload.email):
        raise APIError("EMAIL_EXISTS", "Email already registered", status_code=409)

    locale = _norm_locale(payload.locale)

    user = repo.create_user(
        payload.email,
        hash_password(payload.password),
        payload.name,
        locale,
    )

    db.commit()
    return {"data": {"id": str(user.id), "email": user.email, "locale": user.locale}}


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    repo = Repo(db)
    user = repo.get_user_by_email(payload.email)

    if not user or not verify_password(payload.password, user.password_hash):
        raise APIError("INVALID_CREDENTIALS", "Invalid credentials", status_code=401)

    status = _user_status_value(user)
    if status != "active":
        raise APIError("USER_BLOCKED", "User is not active", {"status": status}, status_code=403)

    token = create_access_token(str(user.id), user.role)
    return {"data": {"access_token": token, "token_type": "bearer"}}


@router.post("/logout")
def logout():
    # Stateless Bearer token (no denylist in MVP)
    return {"data": {"ok": True}}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "locale": user.locale,
            "role": user.role,
            "status": getattr(user.status, "value", user.status),
        }
    }