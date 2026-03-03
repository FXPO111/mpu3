from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.db.repo import Repo
from app.domain.models import APIError, User
from app.security.auth import decode_access_token


def _role_value(user: User) -> str:
    r = getattr(user, "role", None)
    return (getattr(r, "value", r) or "user").strip()


def _status_value(user: User) -> str:
    s = getattr(user, "status", None)
    return (getattr(s, "value", s) or "active").strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise APIError("UNAUTHORIZED", "Missing bearer token", status_code=401)

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise APIError("UNAUTHORIZED", "Missing bearer token", status_code=401)

    try:
        payload = decode_access_token(token)
    except Exception as exc:  # noqa: BLE001
        raise APIError("UNAUTHORIZED", "Invalid token", status_code=401) from exc

    sub = payload.get("sub")
    if not sub:
        raise APIError("UNAUTHORIZED", "Invalid token payload", status_code=401)

    try:
        user_id = sub if isinstance(sub, UUID) else UUID(str(sub))
    except Exception as exc:  # noqa: BLE001
        raise APIError("UNAUTHORIZED", "Invalid token subject", status_code=401) from exc

    user = db.get(User, user_id)
    if not user:
        raise APIError("UNAUTHORIZED", "User not found", status_code=401)

    if _status_value(user) != "active":
        raise APIError(
            "USER_BLOCKED",
            "User is not active",
            {"status": _status_value(user)},
            status_code=403,
        )

    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise APIError("FORBIDDEN", "Insufficient role", status_code=403)
        return user

    return checker

def require_program_access(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    repo = Repo(db)
    if not repo.has_active_entitlement(user.id, "program_access"):
        raise APIError(
            "NO_PROGRAM_ACCESS",
            "Program access required",
            {"pricing_url": "/pricing"},
            status_code=402,
        )
    return user