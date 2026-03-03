import json
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_program_access

router = APIRouter(prefix="/api/client", tags=["client"])


class ProgressPutIn(BaseModel):
    state_json: dict = Field(default_factory=dict)


@router.get("/progress")
def get_progress(db: Session = Depends(get_db), user=Depends(require_program_access)):
    row = (
        db.execute(
            text(
                "select state_json, state_version, updated_at "
                "from user_progress where user_id = :uid"
            ),
            {"uid": str(user.id)},
        )
        .mappings()
        .first()
    )
    if not row:
        return {"data": None}

    updated_at = row["updated_at"]
    return {
        "data": {
            "state_json": row["state_json"],
            "state_version": int(row["state_version"]),
            "updated_at": updated_at.isoformat() if updated_at else None,
        }
    }


@router.put("/progress")
def put_progress(payload: ProgressPutIn, db: Session = Depends(get_db), user=Depends(require_program_access)):
    state_str = json.dumps(payload.state_json, ensure_ascii=False)

    # ограничение, чтобы не засунули гигабайт
    if len(state_str) > 300_000:
        return {"error": {"message": "Progress payload too large"}}

    row = (
        db.execute(
            text(
                "insert into user_progress (id, user_id, state_json, state_version, created_at, updated_at) "
                "values (:id, :uid, (:state)::jsonb, 1, now(), now()) "
                "on conflict (user_id) do update set "
                "state_json = excluded.state_json, "
                "state_version = excluded.state_version, "
                "updated_at = now() "
                "returning state_json, state_version, updated_at"
            ),
            {"id": str(uuid4()), "uid": str(user.id), "state": state_str},
        )
        .mappings()
        .first()
    )
    db.commit()

    return {
        "data": {
            "state_json": row["state_json"],
            "state_version": int(row["state_version"]),
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    }