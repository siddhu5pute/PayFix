"""Payment state changes. Every attempt goes through transition(), which checks the shared
contract first, records the attempt (accepted or rejected) in status_history, and relies on the
DB trigger as a backstop."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from contract import can_transition

log = logging.getLogger("portal.payments")


@dataclass
class TransitionResult:
    txn_id: str
    from_status: str | None
    to_status: str
    changed: bool
    rejected: bool = False
    not_found: bool = False

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def record_history(conn, txn_id, from_status, to_status, source, accepted, reason, details=None):
    conn.execute(
        "INSERT INTO status_history (txn_id, from_status, to_status, source, accepted, reason, details) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (txn_id, from_status, to_status, source, accepted, reason, Jsonb(details or {})),
    )


def transition(conn, txn_id: str, to_status: str, *, source: str, reason: str,
               payment_id: str | None = None, details: dict | None = None) -> TransitionResult:
    """Must be called inside a transaction. Locks the row, so concurrent callers serialise."""
    row = conn.execute("SELECT status, razorpay_payment_id FROM payments WHERE txn_id=%s FOR UPDATE",
                       (txn_id,)).fetchone()
    if row is None:
        return TransitionResult(str(txn_id), None, to_status, changed=False, not_found=True)
    current = row["status"]
    if current == to_status:
        # Idempotent: already in the requested state, nothing to do.
        if payment_id and not row["razorpay_payment_id"]:
            conn.execute("UPDATE payments SET razorpay_payment_id=%s WHERE txn_id=%s", (payment_id, txn_id))
        return TransitionResult(str(txn_id), current, to_status, changed=False)
    if not can_transition(current, to_status):
        log.warning("REJECTED invalid transition txn=%s %s -> %s (source=%s)", txn_id, current, to_status, source)
        record_history(conn, txn_id, current, to_status, source, False,
                       f"rejected: {current} -> {to_status} is not an allowed transition ({reason})", details)
        return TransitionResult(str(txn_id), current, to_status, changed=False, rejected=True)
    conn.execute(
        "UPDATE payments SET status=%s, status_note=%s, "
        "razorpay_payment_id=COALESCE(razorpay_payment_id, %s) WHERE txn_id=%s",
        (to_status, reason, payment_id, txn_id),
    )
    record_history(conn, txn_id, current, to_status, source, True, reason, details)
    log.info("txn=%s %s -> %s (source=%s)", txn_id, current, to_status, source)
    return TransitionResult(str(txn_id), current, to_status, changed=True)


def payment_public(row: dict) -> dict:
    return {
        "txn_id": str(row["txn_id"]),
        "razorpay_order_id": row["razorpay_order_id"],
        "razorpay_payment_id": row["razorpay_payment_id"],
        "payer_name": row["payer_name"],
        "payer_email": row["payer_email"],
        "purpose": row["purpose"],
        "amount_paise": row["amount_paise"],
        "currency": row["currency"],
        "status": row["status"],
        "status_note": row["status_note"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
