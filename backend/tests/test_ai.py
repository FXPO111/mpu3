from app.services.scoring import evaluate_user_message


def test_ai_message_scoring_has_rubrics():
    result = evaluate_user_message("I changed my routine for 3 months and have no relapses.")
    assert "rubric_scores" in result
    assert set(result["rubric_scores"].keys()) >= {"clarity", "specificity", "consistency", "responsibility"}