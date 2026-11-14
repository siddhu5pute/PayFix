"""Append-only audit log (UPDATE/DELETE/TRUNCATE blocked by a DB trigger) and replay."""
from __future__ import annotations

import json
import logging

from psycopg.types.json import Jsonb

log = logging.getLogger("engine.audit")


def _jsonb(obj) -> Jsonb:
    return Jsonb(obj or {}, dumps=lambda o: json.dumps(o, default=str))


class Audit:
    def __init__(self, db):
        self.db = db

    def log(self, step: str, action: str, *, txn_id=None, run_id=None, from_status=None, to_status=None,
            reason=None, details=None, dry_run=False) -> int:
        with self.db.connection() as conn:
            row = conn.execute(
                "INSERT INTO audit_log (txn_id, run_id, step, action, from_status, to_status, reason, details, dry_run) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (txn_id, run_id, step, action, from_status, to_status, reason, _jsonb(details), dry_run),
            ).fetchone()
        log.info("AUDIT %s %s txn=%s %s->%s %s%s", step, action, txn_id, from_status, to_status,
                 reason or "", " [dry-run]" if dry_run else "")
        return row["id"]

    def history(self, txn_id) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM audit_log WHERE txn_id=%s ORDER BY id", (txn_id,)).fetchall()
        return [_row(r) for r in rows]

    def replay(self, txn_id) -> dict:
        """Reconstruct a transaction's story purely from the audit log."""
        events = self.history(txn_id)
        state = None
        timeline = []
        acts = 0
        for e in events:
            if state is None and e["from_status"]:
                state = e["from_status"]
            if e["step"] == "ACT" and not e["dry_run"] and e["to_status"]:
                state = e["to_status"]
                acts += 1
            timeline.append({**e, "state_after": state})
        return {
            "txn_id": str(txn_id),
            "events": timeline,
            "initial_status": next((e["from_status"] for e in events if e["from_status"]), None),
            "final_status": state,
            "actions_taken": acts,
            "refunds": sum(1 for e in events if e["step"] == "REFUND"),
            "sent_to_manual_review": any(e["step"] == "MANUAL_REVIEW" for e in events),
        }


def _row(r: dict) -> dict:
    out = dict(r)
    out["created_at"] = r["created_at"].isoformat()
    if out.get("txn_id") is not None:
        out["txn_id"] = str(out["txn_id"])
    return out
