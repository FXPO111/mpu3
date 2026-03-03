from datetime import datetime, timedelta, timezone

from app.services.ai_orchestrator import (
    _course_needs_rewrite,
    _course_start_intent,
    _should_reuse_last_assistant_for_same_user_text,
)


def test_course_start_intent_ru_accepts_start_commands():
    assert _course_start_intent("Начать обучение", "ru") is True
    assert _course_start_intent("/start", "ru") is True
    assert _course_start_intent("поехали", "ru") is True
    assert _course_start_intent("да", "ru") is False


def test_course_default_rewrite_policy_does_not_require_timeline_for_every_question():
    text = "Я полностью отказался от вождения после алкоголя и ввёл нулевое правило: если есть даже теоретический алкоголь, я не еду за рулём. Я заранее планирую такси или ночёвку, а если мероприятие затягивается, оставляю машину дома, предупреждаю близких и фиксирую это правило в календаре как обязательное."
    flags = {"missing_timeline": True, "missing_actions": False, "blame_shift": False}
    assert _course_needs_rewrite(flags, "alc_avoid_future_dui", text) is False


def test_dedup_reuses_assistant_on_immediate_retry():
    now = datetime.now(timezone.utc)
    assert _should_reuse_last_assistant_for_same_user_text(
        incoming_text="один и тот же ответ",
        last_user_text="один и тот же ответ",
        last_user_created_at=now - timedelta(seconds=2),
        last_assistant_created_at=None,
        now_utc=now,
    ) is True


def test_dedup_reuses_assistant_when_response_already_exists_within_window():
    now = datetime.now(timezone.utc)
    last_user_at = now - timedelta(seconds=50)
    last_assistant_at = now - timedelta(seconds=45)
    assert _should_reuse_last_assistant_for_same_user_text(
        incoming_text="повтор",
        last_user_text="повтор",
        last_user_created_at=last_user_at,
        last_assistant_created_at=last_assistant_at,
        now_utc=now,
    ) is True


def test_dedup_allows_same_text_after_window_expires():
    now = datetime.now(timezone.utc)
    last_user_at = now - timedelta(seconds=181)
    last_assistant_at = now - timedelta(seconds=170)
    assert _should_reuse_last_assistant_for_same_user_text(
        incoming_text="повтор",
        last_user_text="повтор",
        last_user_created_at=last_user_at,
        last_assistant_created_at=last_assistant_at,
        now_utc=now,
    ) is False
