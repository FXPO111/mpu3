from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.deps import require_program_access
from app.domain.models import APIError
from app.services.route_case import apply_answer, get_next_step

router = APIRouter(prefix="/api/route", tags=["route"])


class SetupAnswerIn(BaseModel):
    step_id: str = Field(min_length=2, max_length=64)
    value: object | None = None


@router.get("/bootstrap")
def bootstrap(user=Depends(require_program_access), db: Session = Depends(get_db)):
    repo = Repo(db)
    case = repo.get_or_create_route_case(user.id, topic="unknown")

    if case.setup_status != "complete":
        if case.setup_status == "not_started":
            case.setup_status = "in_progress"

        idx, nxt, total = get_next_step(case.topic, case.data_json or {}, case.setup_step)
        case.setup_step = idx

        if nxt is None:
            case.setup_status = "complete"
            db.commit()
            return {"data": {"state": "session", "case": {"topic": case.topic, "setup_complete": True}}}

        db.commit()
        return {
            "data": {
                "state": "setup",
                "case": {"topic": case.topic, "setup_complete": False},
                "next": {**nxt, "index": idx + 1, "total": total},
            }
        }

    return {"data": {"state": "session", "case": {"topic": case.topic, "setup_complete": True}}}


@router.get("/setup/next")
def setup_next(user=Depends(require_program_access), db: Session = Depends(get_db)):
    repo = Repo(db)
    case = repo.get_route_case(user.id)
    if not case:
        raise APIError("NOT_FOUND", "Route case not found", status_code=404)

    if case.setup_status == "complete":
        return {"data": {"done": True}}

    idx, nxt, total = get_next_step(case.topic, case.data_json or {}, case.setup_step)
    case.setup_step = idx

    if nxt is None:
        case.setup_status = "complete"
        db.commit()
        return {"data": {"done": True}}

    db.commit()
    return {"data": {"done": False, **nxt, "index": idx + 1, "total": total}}


@router.post("/setup/answer")
def setup_answer(payload: SetupAnswerIn, user=Depends(require_program_access), db: Session = Depends(get_db)):
    repo = Repo(db)
    case = repo.get_route_case(user.id)
    if not case:
        raise APIError("NOT_FOUND", "Route case not found", status_code=404)

    if case.setup_status == "complete":
        return {"data": {"done": True}}

    try:
        apply_answer(case, payload.step_id, payload.value)

        # advance pointer
        case.setup_step = int(case.setup_step) + 1
        case.setup_status = "in_progress"

        idx, nxt, total = get_next_step(case.topic, case.data_json or {}, case.setup_step)
        case.setup_step = idx

        if nxt is None:
            case.setup_status = "complete"
            db.commit()
            return {"data": {"done": True}}

        db.commit()
        return {"data": {"done": False, **nxt, "index": idx + 1, "total": total}}

    except ValueError as exc:
        db.rollback()
        raise APIError("BAD_INPUT", str(exc), status_code=422) from exc