from app.integrations.llm_openai import _mpu_answer_standard_ru


def test_mpu_answer_standard_ru_contains_core_blocks():
    text = _mpu_answer_standard_ru()
    assert "Факты+таймлайн" in text
    assert "Личная ответственность" in text
    assert "профилактики рецидива" in text
