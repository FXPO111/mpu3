from app.integrations.llm_openai import _tone_guidance_ru


def test_tone_guidance_ru_detects_emotional_state():
    out = _tone_guidance_ru("Я боюсь завалить интервью и не понимаю, что говорить")
    assert "поддерживающий" in out


def test_tone_guidance_ru_prefers_simple_mode_for_short_text():
    out = _tone_guidance_ru("что мне ответить на мпу")
    assert "Короткие фразы" in out


def test_tone_guidance_ru_default_mode_for_regular_answer():
    out = _tone_guidance_ru("Я подробно описал ситуацию, добавил факты про прошлое поведение и теперь хочу усилить блок про ответственность и устойчивые изменения")
    assert "деловой, но живой" in out
