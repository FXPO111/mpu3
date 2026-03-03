import hmac
from hashlib import sha256

from app.integrations.payments_stripe import parse_event, verify_signature


def test_verify_signature_accepts_valid_hash():
    payload = b'{"id":"evt_1","type":"payment_intent.succeeded"}'
    secret = "whsec_test"
    signature = hmac.new(secret.encode(), payload, sha256).hexdigest()

    assert verify_signature(payload, signature, secret) is True


def test_parse_event_reads_json_payload():
    payload = b'{"id":"evt_1","type":"checkout.session.completed"}'
    event = parse_event(payload)
    assert event["id"] == "evt_1"
    assert event["type"] == "checkout.session.completed"