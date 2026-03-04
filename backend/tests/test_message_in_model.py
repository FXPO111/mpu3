from app.domain.models import MessageIn


def test_message_in_allows_empty_content_for_bootstrap_paths():
    m = MessageIn(content="")
    assert m.content == ""


def test_message_in_defaults_to_empty_string_when_omitted():
    m = MessageIn()
    assert m.content == ""
