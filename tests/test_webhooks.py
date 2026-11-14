"""PROOF: webhook signature is verified over the raw body; duplicates are ignored; failure flags work."""
import hashlib
import hmac
import json
import os
import time
import uuid

import psycopg

SECRET = "unit_webhook_secret"


def _pay(client):
    r = client.post("/pay", json={"payer_name": "Sample Student", "payer_email": "s@example.com",
                                  "purpose": "Review exam fee", "amount_paise": 100000})
    return r.json()


def _event(order_id, event="payment.captured", status="captured"):
    pay = {"id": "pay_" + uuid.uuid4().hex[:14], "entity": "payment", "amount": 100000, "currency": "INR",
           "status": status, "order_id": order_id}
    body = {"entity": "event", "event": event, "contains": ["payment"], "payload": {"payment": {"entity": pay}}}
    return json.dumps(body, separators=(",", ":")).encode()


def _send(client, raw, event_id=None, secret=SECRET, signature=None):
    sig = signature if signature is not None else hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": sig,
               "X-Razorpay-Event-Id": event_id or ("evt_" + uuid.uuid4().hex[:14])}
    return client.post("/webhooks/razorpay", content=raw, headers=headers)


def _count_events(event_id):
    with psycopg.connect(os.environ["PORTAL_DATABASE_URL"]) as conn:
        return conn.execute("SELECT count(*) FROM webhook_events WHERE event_id=%s", (event_id,)).fetchone()[0]


def test_invalid_signature_rejected(portal_client):
    o = _pay(portal_client)
    raw = _event(o["razorpay_order_id"])
    r = _send(portal_client, raw, secret="attacker-secret")
    assert r.status_code == 400
    r = _send(portal_client, raw, signature="")
    assert r.status_code == 400
    # tampered body with the original signature
    good_sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    r = _send(portal_client, raw.replace(b"100000", b"1"), signature=good_sig)
    assert r.status_code == 400
    assert portal_client.get(f"/payments/{o['txn_id']}").json()["status"] == "pending"
    print(f"\nPROOF webhook: 3 forged/tampered webhooks rejected with 400, txn {o['txn_id']} still pending")


def test_valid_webhook_marks_paid_and_duplicate_ignored(portal_client):
    o = _pay(portal_client)
    raw = _event(o["razorpay_order_id"])
    eid = "evt_" + uuid.uuid4().hex[:14]
    r1 = _send(portal_client, raw, event_id=eid)
    assert r1.status_code == 200 and r1.json()["status"] == "processed"
    r2 = _send(portal_client, raw, event_id=eid)
    assert r2.status_code == 200 and r2.json()["status"] == "duplicate"
    assert _count_events(eid) == 1
    p = portal_client.get(f"/payments/{o['txn_id']}").json()
    assert p["status"] == "paid"
    assert sum(1 for h in p["history"] if h["to_status"] == "paid" and h["accepted"]) == 1
    print(f"\nPROOF webhook: event {eid} delivered twice -> stored once, applied once ({r2.json()['status']})")


def test_drop_flag_keeps_portal_pending(portal_client, portal_flags):
    portal_flags.update(drop_webhooks=True)
    o = _pay(portal_client)
    r = _send(portal_client, _event(o["razorpay_order_id"]))
    assert r.status_code == 200 and r.json()["status"] == "dropped"
    assert portal_client.get(f"/payments/{o['txn_id']}").json()["status"] == "pending"


def test_delay_flag_processes_later(portal_client, portal_flags):
    portal_flags.update(delay_webhook_seconds=1)
    o = _pay(portal_client)
    r = _send(portal_client, _event(o["razorpay_order_id"]))
    assert r.json()["status"] == "accepted_delayed"
    assert portal_client.get(f"/payments/{o['txn_id']}").json()["status"] == "pending"
    time.sleep(2.0)
    assert portal_client.get(f"/payments/{o['txn_id']}").json()["status"] == "paid"


def test_duplicate_flag_redelivery_is_deduped(portal_client, portal_flags):
    portal_flags.update(duplicate_webhooks=True)
    o = _pay(portal_client)
    eid = "evt_" + uuid.uuid4().hex[:14]
    _send(portal_client, _event(o["razorpay_order_id"]), event_id=eid)
    time.sleep(1.2)
    assert _count_events(eid) == 1
    p = portal_client.get(f"/payments/{o['txn_id']}").json()
    assert sum(1 for h in p["history"] if h["to_status"] == "paid" and h["accepted"]) == 1


def test_captured_after_failed_is_rejected_by_state_machine(portal_client):
    o = _pay(portal_client)
    _send(portal_client, _event(o["razorpay_order_id"], "payment.failed", "failed"))
    assert portal_client.get(f"/payments/{o['txn_id']}").json()["status"] == "failed"
    r = _send(portal_client, _event(o["razorpay_order_id"]))
    assert "rejected" in r.json()["outcome"]
    p = portal_client.get(f"/payments/{o['txn_id']}").json()
    assert p["status"] == "failed"
    assert any(not h["accepted"] and h["to_status"] == "paid" for h in p["history"])


def test_checkout_signature_is_only_a_hint(portal_client):
    o = _pay(portal_client)
    pid = "pay_" + uuid.uuid4().hex[:14]
    sig = hmac.new(b"unit_key_secret", f"{o['razorpay_order_id']}|{pid}".encode(), hashlib.sha256).hexdigest()
    r = portal_client.post("/payments/verify", json={"txn_id": o["txn_id"], "razorpay_order_id": o["razorpay_order_id"],
                                                    "razorpay_payment_id": pid, "razorpay_signature": sig})
    assert r.status_code == 200 and r.json()["signature_valid"] is True
    assert r.json()["status"] == "pending"  # NOT paid: the browser is not the source of truth
    bad = portal_client.post("/payments/verify", json={"txn_id": o["txn_id"], "razorpay_order_id": o["razorpay_order_id"],
                                                      "razorpay_payment_id": pid, "razorpay_signature": "0" * 64})
    assert bad.status_code == 400
