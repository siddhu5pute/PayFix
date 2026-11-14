"""PROOF: invalid transitions are rejected in code AND in the database, and every rejection is logged."""
import psycopg
import pytest

from contract import ALLOWED_TRANSITIONS, can_transition, validate_amount_paise

KEY = {"X-Internal-Key": "unit-internal-key"}


def _pay(client, amount=100000):
    r = client.post("/pay", json={"payer_name": "Sample Student", "payer_email": "s@example.com",
                                  "purpose": "Review exam fee", "amount_paise": amount})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("frm,to,ok", [
    ("created", "pending", True), ("pending", "paid", True), ("pending", "failed", True),
    ("pending", "unknown", True), ("unknown", "paid", True), ("unknown", "failed", True),
    ("paid", "refunded", True),
    ("paid", "pending", False), ("paid", "failed", False), ("failed", "paid", False),
    ("failed", "pending", False), ("created", "paid", False), ("unknown", "pending", False),
])
def test_contract_table(frm, to, ok):
    assert can_transition(frm, to) is ok


def test_nothing_leaves_failed():
    assert ALLOWED_TRANSITIONS["failed"] == frozenset()


def test_money_is_integer_paise():
    assert validate_amount_paise(100000) == 100000
    for bad in (1000.5, "1000", 0, -5, True):
        with pytest.raises(ValueError):
            validate_amount_paise(bad)


def test_pay_rejects_float_amount(portal_client):
    r = portal_client.post("/pay", json={"payer_name": "A B", "payer_email": "a@example.com",
                                         "purpose": "fee", "amount_paise": 1000.5})
    assert r.status_code == 422


def test_invalid_transition_rejected_and_logged(portal_client):
    o = _pay(portal_client)
    txn = o["txn_id"]
    assert portal_client.get(f"/payments/{txn}").json()["status"] == "pending"

    r = portal_client.post(f"/internal/transactions/{txn}/mark-paid", json={"reason": "test"}, headers=KEY)
    assert r.status_code == 200 and r.json()["changed"] is True

    # paid -> pending is illegal
    r = portal_client.post(f"/admin/payments/{txn}/force-transition", json={"to_status": "pending"})
    assert r.status_code == 409
    assert r.json()["rejected"] is True
    # paid -> failed through the engine API is illegal too
    r = portal_client.post(f"/internal/transactions/{txn}/mark-failed", json={"reason": "test"}, headers=KEY)
    assert r.status_code == 409

    p = portal_client.get(f"/payments/{txn}").json()
    assert p["status"] == "paid"
    rejected = [h for h in p["history"] if not h["accepted"]]
    assert len(rejected) == 2
    assert {(h["from_status"], h["to_status"]) for h in rejected} == {("paid", "pending"), ("paid", "failed")}
    print(f"\nPROOF state-machine: txn {txn} stayed 'paid'; rejected+logged: "
          f"{[(h['from_status'], h['to_status'], h['reason']) for h in rejected]}")


def test_database_trigger_is_the_backstop(portal_client):
    import os
    o = _pay(portal_client)
    txn = o["txn_id"]
    portal_client.post(f"/internal/transactions/{txn}/mark-failed", json={"reason": "t"}, headers=KEY)
    with psycopg.connect(os.environ["PORTAL_DATABASE_URL"]) as conn:
        with pytest.raises(psycopg.errors.CheckViolation, match="invalid payment transition failed -> paid"):
            conn.execute("UPDATE payments SET status='paid' WHERE txn_id=%s", (txn,))
    with psycopg.connect(os.environ["PORTAL_DATABASE_URL"]) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("INSERT INTO payments (txn_id, payer_name, payer_email, purpose, amount_paise, status) "
                         "VALUES (gen_random_uuid(), 'x', 'x@x.com', 'p', 100, 'paid')")
    print(f"\nPROOF state-machine: raw SQL failed -> paid on {txn} blocked by DB trigger")


def test_internal_api_requires_key(portal_client):
    assert portal_client.get("/internal/transactions").status_code == 401
    assert portal_client.get("/internal/transactions", headers={"X-Internal-Key": "wrong"}).status_code == 401
    assert portal_client.get("/internal/transactions", headers=KEY).status_code == 200
