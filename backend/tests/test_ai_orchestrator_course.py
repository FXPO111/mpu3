from app.services.ai_orchestrator import _course_needs_rewrite, _course_start_intent


def test_course_start_intent_ru_accepts_start_commands():
    assert _course_start_intent("Начать обучение", "ru") is True
    assert _course_start_intent("/start", "ru") is True
    assert _course_start_intent("поехали", "ru") is True
    assert _course_start_intent("да", "ru") is False


def test_course_default_rewrite_policy_does_not_require_timeline_for_every_question():
    text = "Я полностью отказался от вождения после алкоголя и ввёл нулевое правило: если есть даже теоретический алкоголь, я не еду за рулём. Я заранее планирую такси или ночёвку, а если мероприятие затягивается, оставляю машину дома, предупреждаю близких и фиксирую это правило в календаре как обязательное."
    flags = {"missing_timeline": True, "missing_actions": False, "blame_shift": False}
    assert _course_needs_rewrite(flags, "alc_avoid_future_dui", text) is False
