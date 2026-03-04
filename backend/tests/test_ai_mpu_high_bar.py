from app.integrations.llm_openai import _mpu_high_bar_rules_ru


def test_mpu_high_bar_rules_ru_mentions_episode_and_decision_chain():
    text = _mpu_high_bar_rules_ru()
    assert "конкретный эпизод" in text
    assert "цепочку решения" in text
    assert "Не используй формы '(а)'" in text
