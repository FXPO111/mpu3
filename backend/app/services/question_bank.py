# question_bank.py
from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import Question
from app.integrations.llm_openai import translate_question_to_ru

_MODE_LEVELS = {
    "diagnostic": (1, 2),
    "practice": (2, 4),
    "mock": (2, 5),
}

# Анти-повтор: сколько последних вопросов держим в памяти для каждого "контекста выбора"
_RECENT_WINDOW = 6

# key -> deque[question_id]
_RECENT_IDS: dict[str, Deque[UUID]] = defaultdict(lambda: deque(maxlen=_RECENT_WINDOW))

# RU translation cache (in-memory, best-effort)
_RU_TRANSLATIONS: dict[UUID, str] = {}


def _normalize_locale(locale: str) -> str:
    loc = (locale or "de").lower().strip()
    if loc.startswith("de"):
        return "de"
    if loc.startswith("ru"):
        return "ru"
    return "de"  # никаких en по умолчанию


def _fallback_question(locale: str, mode: str | None) -> str:
    locale = _normalize_locale(locale)
    mode = (mode or "").strip().lower() or None

    if locale == "ru":
        if mode == "mock":
            return "Кратко опиши вашу ситуацию в 2–3 предложениях: факты, даты, твоя роль и вывод."
        if mode == "practice":
            return "Что именно произошло (когда, где, с кем) и какую ответственность ты берёшь на себя?"
        return "Коротко опиши текущую ситуацию по теме MPU."
    else:
        # Только DE (никаких EN)
        if mode == "mock":
            return "Fassen Sie Ihren Fall in 2–3 Sätzen zusammen: Fakten, Datum/Zeitraum, Ihre Rolle und Schlussfolgerung."
        if mode == "practice":
            return "Was ist genau passiert (wann, wo, mit wem) und welche Verantwortung übernehmen Sie?"
        return "Beschreiben Sie kurz Ihre aktuelle Situation im Zusammenhang mit MPU."


def _make_recent_key(
    *,
    locale: str,
    mode: str | None,
    topic_id: UUID | None,
    level_min: int | None,
    level_max: int | None,
    required_tags: list[str] | None,
) -> str:
    loc = _normalize_locale(locale)
    m = (mode or "").strip().lower() or ""
    t = str(topic_id) if topic_id else "-"
    lm = str(level_min) if level_min is not None else "-"
    lx = str(level_max) if level_max is not None else "-"
    tags = ",".join(sorted([str(x).strip().lower() for x in (required_tags or []) if str(x).strip()])) or "-"
    return f"{loc}|{m}|{t}|{lm}|{lx}|{tags}"


def _pick_question(
    db: Session,
    *,
    mode: str | None,
    topic_id: UUID | None,
    level_min: int | None,
    level_max: int | None,
    required_tags: list[str] | None,
    exclude_ids: list[UUID] | None = None,
) -> Question | None:
    stmt = select(Question)

    if topic_id is not None:
        stmt = stmt.where(Question.topic_id == topic_id)

    if (level_min is None or level_max is None) and mode in _MODE_LEVELS:
        lm, lx = _MODE_LEVELS[mode]
        level_min = lm if level_min is None else level_min
        level_max = lx if level_max is None else level_max

    if level_min is not None:
        stmt = stmt.where(Question.level >= int(level_min))
    if level_max is not None:
        stmt = stmt.where(Question.level <= int(level_max))

    if required_tags:
        # Postgres ARRAY: overlap = any common tag
        stmt = stmt.where(Question.tags.overlap(list(required_tags)))

    if exclude_ids:
        stmt = stmt.where(~Question.id.in_(list(exclude_ids)))

    stmt = stmt.order_by(func.random()).limit(1)
    return db.scalar(stmt)


def next_question(
    db: Session,
    locale: str = "de",
    *,
    mode: str | None = None,
    topic_id: UUID | None = None,
    level_min: int | None = None,
    level_max: int | None = None,
    required_tags: list[str] | None = None,
) -> str:
    loc = _normalize_locale(locale)
    mode_norm = (mode or "").strip().lower() or None

    # Анти-повтор: берём последние id для этого контекста выбора
    key = _make_recent_key(
        locale=loc,
        mode=mode_norm,
        topic_id=topic_id,
        level_min=level_min,
        level_max=level_max,
        required_tags=required_tags,
    )
    recent_ids = list(_RECENT_IDS[key]) if key in _RECENT_IDS else []
    exclude_ids = recent_ids if recent_ids else None

    def pick_with_fallbacks(exclude: list[UUID] | None) -> Question | None:
        q0 = _pick_question(
            db,
            mode=mode_norm,
            topic_id=topic_id,
            level_min=level_min,
            level_max=level_max,
            required_tags=required_tags,
            exclude_ids=exclude,
        )

        if not q0 and topic_id is not None:
            q0 = _pick_question(
                db,
                mode=mode_norm,
                topic_id=None,
                level_min=level_min,
                level_max=level_max,
                required_tags=required_tags,
                exclude_ids=exclude,
            )

        if not q0 and (level_min is not None or level_max is not None):
            q0 = _pick_question(
                db,
                mode=mode_norm,
                topic_id=topic_id,
                level_min=None,
                level_max=None,
                required_tags=required_tags,
                exclude_ids=exclude,
            )

        # If tag constraints are too strict -> drop them
        if not q0 and required_tags:
            q0 = _pick_question(
                db,
                mode=mode_norm,
                topic_id=topic_id,
                level_min=level_min,
                level_max=level_max,
                required_tags=None,
                exclude_ids=exclude,
            )

        return q0

    # 1) пробуем исключить недавние
    q = pick_with_fallbacks(exclude_ids)

    # 2) если всё вычистили — разрешаем повтор
    if not q and exclude_ids:
        q = pick_with_fallbacks(None)

    if not q:
        return _fallback_question(loc, mode_norm)

    # Запоминаем выбранный вопрос
    _RECENT_IDS[key].append(q.id)

    # Locale-specific output
    if loc == "ru":
        ru_text = getattr(q, "question_ru", None)
        if isinstance(ru_text, str) and ru_text.strip():
            return ru_text.strip()

        cached = _RU_TRANSLATIONS.get(q.id)
        if isinstance(cached, str) and cached.strip():
            return cached.strip()

        base = (q.question_de or "").strip()
        if not base:
            return _fallback_question(loc, mode_norm)

        translated = (translate_question_to_ru(base) or "").strip() or base
        _RU_TRANSLATIONS[q.id] = translated
        return translated

    # DE (default)
    text = (q.question_de or "").strip()
    return text or _fallback_question(loc, mode_norm)