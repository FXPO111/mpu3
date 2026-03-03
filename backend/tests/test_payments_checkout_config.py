from app.integrations.payments_stripe import is_stripe_configured


def test_is_stripe_configured_rejects_placeholders():
    assert is_stripe_configured("") is False
    assert is_stripe_configured("sk_test_xxx") is False
    assert is_stripe_configured("sk_live_xxx") is False
    assert is_stripe_configured("change-me") is False


def test_is_stripe_configured_accepts_real_prefixes():
    assert is_stripe_configured("sk_test_123456") is True
    assert is_stripe_configured("sk_live_abcdef") is True