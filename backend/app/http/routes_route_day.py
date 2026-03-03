from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.deps import require_program_access
from app.domain.models import APIError
from app.services.question_bank import next_question
from app.services.scoring import evaluate_user_message

router = APIRouter(prefix="/api/route", tags=["route"])


def _safe_tz(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _today_key(user_timezone: str | None) -> str:
    tz = _safe_tz(user_timezone)
    return datetime.now(tz).date().isoformat()  # YYYY-MM-DD


def _mk_tasks(db: Session, locale: str, topic_id: UUID | None) -> list[dict]:
    # 2 задания: одно "practice", одно "mock" (разные формулировки, разный band)
    q1 = next_question(db, locale=locale, mode="practice", topic_id=topic_id)
    q2 = next_question(db, locale=locale, mode="mock", topic_id=topic_id)

    return [
        {
            "task_id": "q1",
            "mode": "practice",
            "title": "Antwort-Training",
            "question": q1,
            "answer": None,
            "evaluation": None,
            "done": False,
        },
        {
            "task_id": "q2",
            "mode": "mock",
            "title": "MPU-Stil Frage",
            "question": q2,
            "answer": None,
            "evaluation": None,
            "done": False,
        },
    ]


def _extract_topic_id(db: Session, case) -> UUID | None:
    """
    case.topic expected like: 'alcohol'|'drugs'|'points'|'incident' (твоя схема из шага 1).
    Если в topics нет такого slug — вернём None, тогда question_bank сам возьмёт random/fallback.
    """
    try:
        from sqlalchemy import select
        from app.domain.models import Topic

        slug = (getattr(case, "topic", None) or "").strip().lower()
        if not slug:
            return None
        return db.scalar(select(Topic.id).where(Topic.slug == slug))
    except Exception:  # noqa: BLE001
        return None


def _ensure_today(db: Session, user, case):
    repo = Repo(db)
    date_key = _today_key(getattr(user, "timezone", None))
    day = repo.get_route_day_by_date(user.id, date_key)
    if day:
        return day

    max_idx = repo.get_max_route_day_index(user.id)
    topic_id = _extract_topic_id(db, case)
    tasks = _mk_tasks(db, locale=user.locale, topic_id=topic_id)
    return repo.create_route_day(user.id, date_key, max_idx + 1, tasks)


class DayAnswerIn(BaseModel):
    task_id: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=2, max_length=6000)


@router.get("/day/today")
def get_today(user=Depends(require_program_access), db: Session = Depends(get_db)):
    repo = Repo(db)

    # Требуем, чтобы кейс был полностью собран (шаг 1)
    case = repo.get_route_case(user.id)  # <-- метод из шага 1
    if not case or getattr(case, "setup_status", None) != "complete":
        raise APIError(
            "SETUP_REQUIRED",
            "Route setup is not complete",
            {"next": "route_setup"},
            status_code=409,
        )

    day = _ensure_today(db, user, case)

    tasks = list(day.tasks_json or [])
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("done"))

    return {
        "data": {
            "day": {
                "date_key": day.date_key,
                "day_index": day.day_index,
                "status": day.status,
                "done": done,
                "total": total,
            },
            "tasks": tasks,
        }
    }


@router.post("/day/answer")
def submit_answer(payload: DayAnswerIn, user=Depends(require_program_access), db: Session = Depends(get_db)):
    repo = Repo(db)

    case = repo.get_route_case(user.id)  # <-- метод из шага 1
    if not case or getattr(case, "setup_status", None) != "complete":
        raise APIError("SETUP_REQUIRED", "Route setup is not complete", status_code=409)

    try:
        day = _ensure_today(db, user, case)

        tasks = list(day.tasks_json or [])
        idx = next((i for i, t in enumerate(tasks) if t.get("task_id") == payload.task_id), None)
        if idx is None:
            raise APIError("TASK_NOT_FOUND", "Task not found", {"task_id": payload.task_id}, status_code=404)

        evaluation = evaluate_user_message(payload.content)

        t = dict(tasks[idx])  # copy
        t["answer"] = payload.content
        t["evaluation"] = evaluation
        t["done"] = True

        tasks[idx] = t
        day.tasks_json = tasks  # IMPORTANT: reassign to mark dirty

        if all(bool(x.get("done")) for x in tasks):
            day.status = "complete"

        db.commit()

        return {
            "data": {
                "day": {
                    "date_key": day.date_key,
                    "day_index": day.day_index,
                    "status": day.status,
                    "done": sum(1 for x in tasks if x.get("done")),
                    "total": len(tasks),
                },
                "task": t,
            }
        }

    except APIError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc