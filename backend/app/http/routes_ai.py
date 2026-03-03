from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.deps import get_current_user
from app.domain.models import APIError, MessageIn, SessionCreateIn
from app.services.ai_orchestrator import process_user_message

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _norm_locale(locale: str) -> str:
    # Только ru/de. Никакого en.
    loc = (locale or "de").strip().lower()
    if loc.startswith("de"):
        return "de"
    if loc.startswith("ru"):
        return "ru"
    return "de"


def _norm_mode(mode: str) -> str:
    m = (mode or "").strip().lower()
    if m not in {"diagnostic", "practice", "mock"}:
        raise APIError("BAD_MODE", "Invalid mode. Use: diagnostic, practice, mock", {"mode": mode}, status_code=422)
    return m


_MACHINE_PREFIXES = (
    "[[DAY_PLAN]]",
    "[[EVAL]]",
    "[[COURSE]]",
    "[[DOSSIER_UPDATE]]",
    "[[ОБНОВЛЕНИЕ_ДОСЬЕ]]",
)

# Любые варианты, которые иногда просачиваются в «человеческий» текст
_MACHINE_TOKENS_ANYWHERE = (
    "[[DAY_PLAN]]",
    "[[EVAL]]",
    "[[DOSSIER_UPDATE]]",
    "[[ОБНОВЛЕНИЕ_ДОСЬЕ]]",
    "[ПЛАН_ДНЯ]",
    "[ПЛАН ДНЯ]",
    "[DAY_PLAN]",
    "DAY_PLAN",
    "[[COURSE]]",
    "COURSE",
    "DOSSIER_UPDATE",
    "ОБНОВЛЕНИЕ_ДОСЬЕ",
    "Политика следующего шага:",
    "boot=",
)


def _public_content(text: str) -> str:
    """Контент для UI: без машинных блоков и без промпт-маркеров."""
    if not text:
        return ""

    out: list[str] = []

    for line in text.splitlines():
        raw = line
        t = raw.strip()

        # 1) удаляем строки-машинные блоки целиком
        if any(t.startswith(p) for p in _MACHINE_PREFIXES):
            continue

        # 2) если маркер попал в середину строки — режем всё после него
        for token in _MACHINE_TOKENS_ANYWHERE:
            if token in raw:
                raw = raw.split(token, 1)[0].rstrip()
                t = raw.strip()

        # 3) если внезапно протащился JSON-кусок — выкидываем
        low = t.lower()
        if any(k in low for k in ('"agenda"', '"success_criteria"', '"rubric"', '"timebox_min"', '"shortstory"', '"redzones"')):
            continue

        if t:
            out.append(raw)

    return "\n".join(out).strip()


@router.post("/sessions")
def create_session(payload: SessionCreateIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo = Repo(db)
    try:
        mode = _norm_mode(payload.mode)
        locale = _norm_locale(payload.locale)

        sess = repo.create_ai_session(user.id, mode, locale)
        db.commit()
        return {"data": {"id": str(sess.id), "mode": sess.mode, "locale": sess.locale, "status": sess.status}}
    except APIError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc


@router.get("/sessions/{session_id}")
def get_session(session_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo = Repo(db)
    sess = repo.get_ai_session(session_id)
    if not sess or sess.user_id != user.id:
        raise APIError("NOT_FOUND", "Session not found", status_code=404)
    return {"data": {"id": str(sess.id), "mode": sess.mode, "locale": sess.locale, "status": sess.status}}


@router.get("/sessions/{session_id}/messages")
def messages(session_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo = Repo(db)
    sess = repo.get_ai_session(session_id)
    if not sess or sess.user_id != user.id:
        raise APIError("NOT_FOUND", "Session not found", status_code=404)

    rows = repo.list_messages(session_id)
    return {
        "data": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": _public_content(m.content),  # UI-safe
                "raw_content": m.content,  # если нужно для отладки/будущего парсинга
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ]
    }


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: UUID, payload: MessageIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo = Repo(db)
    sess = repo.get_ai_session(session_id)
    if not sess or sess.user_id != user.id:
        raise APIError("NOT_FOUND", "Session not found", status_code=404)

    if sess.status != "active":
        raise APIError("SESSION_CLOSED", "Session is closed", status_code=409)

    try:
        # Проверяем: первое сообщение в сессии?
        try:
            existing = repo.list_messages(session_id)
            is_first_message = len(existing) == 0
        except Exception:  # noqa: BLE001
            is_first_message = False

        content = (payload.content or "").strip()

        # 1) Если UI отправляет пусто на "Начать" — превращаем в boot (только для первого сообщения)
        if not content and is_first_message and sess.mode in {"practice", "mock"}:
            content = "[[START_PRACTICE]]" if sess.mode == "practice" else "[[START_MOCK]]"

        if not content:
            raise APIError("EMPTY_MESSAGE", "Message is empty", status_code=422)

        # 2) Если UI отправляет "Начать" текстом — тоже превращаем в boot (только первое сообщение)
        if is_first_message and sess.mode in {"practice", "mock"} and not content.startswith("[[START_"):
            low = content.lower()
            if low in {"start", "/start", "начать", "начать обучение", "начать экзамен"}:
                content = "[[START_PRACTICE]]" if sess.mode == "practice" else "[[START_MOCK]]"

        is_boot = content.startswith("[[START_")

        # ВАЖНО: стартовые триггеры (boot) не списывают кредит.
        if not is_boot:
            if not repo.consume_credit(user.id):
                raise APIError(
                    "NO_CREDITS",
                    "No AI credits left. Please buy an AI package.",
                    {"pricing_url": "/pricing"},
                    status_code=402,
                )

        assistant = process_user_message(db, session_id, content, sess.locale, sess.mode)
        db.commit()

        # UI получает очищенный текст, raw — отдельно
        return {
            "data": {
                "assistant_message": {
                    "id": str(assistant.id),
                    "content": _public_content(assistant.content),
                    "raw_content": assistant.content,
                }
            }
        }

    except APIError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc


@router.post("/sessions/{session_id}/close")
def close_session(session_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo = Repo(db)
    sess = repo.get_ai_session(session_id)
    if not sess or sess.user_id != user.id:
        raise APIError("NOT_FOUND", "Session not found", status_code=404)

    if sess.status != "active":
        return {"data": {"id": str(sess.id), "status": sess.status}}

    try:
        sess.status = "closed"
        if hasattr(sess, "closed_at"):
            sess.closed_at = _now_utc()
        db.commit()
        return {"data": {"id": str(sess.id), "status": "closed"}}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise exc