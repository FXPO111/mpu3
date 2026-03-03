from types import SimpleNamespace

from app.services.payments import apply_paid_event


class FakeRepo:
    def __init__(self):
        self.order = SimpleNamespace(id="o1", status="pending", user_id="u1", product=SimpleNamespace(type="ai_pack"))
        self.grants = 0

    def find_order_by_provider_ref(self, _provider_ref):
        return self.order

    def grant_entitlement_once(self, order, kind, qty_total):
        if self.grants == 0:
            self.grants += 1
            order.status = "paid"
            return SimpleNamespace(valid_from=None, valid_to=None)
        return SimpleNamespace(valid_from=None, valid_to=None)


def test_webhook_idempotent(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr("app.services.payments.Repo", lambda _db: repo)

    apply_paid_event(None, "pi_1")
    apply_paid_event(None, "pi_1")

    assert repo.grants == 1


def test_program_grants_access_and_credits(monkeypatch):
    repo = FakeRepo()
    repo.order.product = SimpleNamespace(type="program", active=True, metadata_json={"valid_days": 14, "ai_credits": 10})
    granted = []

    def grant(order, kind, qty_total):
        granted.append((kind, qty_total))
        return SimpleNamespace(valid_from=None, valid_to=None)

    repo.grant_entitlement_once = grant
    monkeypatch.setattr("app.services.payments.Repo", lambda _db: repo)

    apply_paid_event(None, "pi_1")

    assert ("program_access", 1) in granted
    assert ("ai_credits", 10) in granted