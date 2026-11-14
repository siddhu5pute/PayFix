"""Razorpay webhook ingestion with failure injection.

Order of operations (each step must pass before the next):
  1. verify X-Razorpay-Signature over the RAW body
  2. derive event id (X-Razorpay-Event-Id header, else sha256 of the body)
  3. apply DROP_WEBHOOKS (store as dropped, acknowledge, do nothing else)
  4. store the event, deduplicating on event_id (UNIQUE)
  5. process now, or after DELAY_WEBHOOK_SECONDS
  6. DUPLICATE_WEBHOOKS re-delivers the same signed event once more to prove dedupe
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time

from psycopg.types.json import Jsonb

from contract import FAILED, PAID, PENDING, UNKNOWN

from . import db
from .config import settings
from .flags import flags
from .payments import transition
from .signatures import verify_webhook_signature

log = logging.getLogger("portal.webhooks")


def ingest(raw: bytes, signature: str | None, event_id_header: str | None, *, redelivery: bool = False) -> dict:
    if not verify_webhook_signature(raw, signature, settings.razorpay_webhook_secret):
        with db.pool().connection() as conn:
            conn.execute("INSERT INTO rejected_webhooks (reason) VALUES (%s)",
                         ("invalid or missing X-Razorpay-Signature",))
        log.warning("webhook rejected: invalid signature")
        return {"status": "rejected", "reason": "invalid signature", "http": 400}

    try:
        payload = json.loads(raw)
    except ValueError:
        return {"status": "rejected", "reason": "malformed json", "http": 400}

    event_id = event_id_header or ("sha256:" + hashlib.sha256(raw).hexdigest())
    event_type = payload.get("event", "unknown")
    f = flags.snapshot()

    if f["drop_webhooks"] and not redelivery:
        with db.pool().connection() as conn:
            conn.execute(
                "INSERT INTO webhook_events (event_id, event_type, payload, processed, outcome) "
                "VALUES (%s,%s,%s,false,%s) ON CONFLICT (event_id) DO NOTHING",
                (event_id, event_type, Jsonb(payload), "dropped by DROP_WEBHOOKS flag"))
        log.warning("DROP_WEBHOOKS: acknowledged and ignored %s %s", event_type, event_id)
        return {"status": "dropped", "event_id": event_id, "http": 200}

    with db.pool().connection() as conn:
        inserted = conn.execute(
            "INSERT INTO webhook_events (event_id, event_type, payload) VALUES (%s,%s,%s) "
            "ON CONFLICT (event_id) DO NOTHING RETURNING id",
            (event_id, event_type, Jsonb(payload))).fetchone()
    if inserted is None:
        log.info("duplicate webhook ignored %s %s", event_type, event_id)
        return {"status": "duplicate", "event_id": event_id, "http": 200}

    delay = f["delay_webhook_seconds"]
    if delay > 0 and not redelivery:
        log.warning("DELAY_WEBHOOK_SECONDS: processing %s in %ss", event_id, delay)
        _later(delay, lambda: process_event(event_id, payload))
        result = {"status": "accepted_delayed", "event_id": event_id, "delay": delay, "http": 200}
    else:
        outcome = process_event(event_id, payload)
        result = {"status": "processed", "event_id": event_id, "outcome": outcome, "http": 200}

    if f["duplicate_webhooks"] and not redelivery:
        def again():
            r = ingest(raw, signature, event_id, redelivery=True)
            log.warning("DUPLICATE_WEBHOOKS: re-delivered %s -> %s", event_id, r["status"])
        _later(0.5, again)
    return result


def _later(seconds: float, fn) -> None:
    def run():
        time.sleep(seconds)
        try:
            fn()
        except Exception:
            log.exception("deferred webhook work failed")
    threading.Thread(target=run, daemon=True).start()


def process_event(event_id: str, payload: dict) -> str:
    event_type = payload.get("event")
    entity = (payload.get("payload", {}).get("payment") or {}).get("entity") or {}
    order_id = entity.get("order_id") or ((payload.get("payload", {}).get("order") or {}).get("entity") or {}).get("id")
    payment_id = entity.get("id")

    with db.pool().connection() as conn:
        row = conn.execute("SELECT txn_id, status FROM payments WHERE razorpay_order_id=%s",
                           (order_id,)).fetchone() if order_id else None
        if row is None:
            outcome = f"ignored: no payment for order {order_id}"
        elif event_type in ("payment.captured", "order.paid"):
            res = transition(conn, row["txn_id"], PAID, source=f"webhook:{event_type}",
                             reason=f"confirmed by webhook {event_type}", payment_id=payment_id,
                             details={"event_id": event_id})
            outcome = ("rejected invalid transition " if res.rejected else
                       "marked paid " if res.changed else "already paid ") + f"({res.from_status} -> paid)"
        elif event_type == "payment.failed":
            if row["status"] in (PENDING, UNKNOWN):
                res = transition(conn, row["txn_id"], FAILED, source="webhook:payment.failed",
                                 reason=entity.get("error_description") or "payment failed at gateway",
                                 payment_id=payment_id, details={"event_id": event_id})
                outcome = f"marked failed ({res.from_status} -> failed)"
            else:
                outcome = f"ignored payment.failed: portal status is {row['status']}"
        else:
            outcome = f"no status change for {event_type}"
        conn.execute("UPDATE webhook_events SET processed=true, outcome=%s WHERE event_id=%s",
                     (outcome, event_id))
    log.info("webhook %s %s: %s", event_type, event_id, outcome)
    return outcome
