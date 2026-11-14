"""The reconciliation loop: COLLECT -> DETECT -> VERIFY -> DECIDE -> ACT (exactly once) -> LOG."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from contract import FAILED, G_NONE, PAID, PENDING, UNKNOWN

from .audit import Audit
from .gateway import GatewayView, PermanentGatewayError, TransientGatewayError
from .portal_client import PortalError, PortalTransientError
from .retry import RetriesExhausted, with_retry
from .rules import MANUAL_REVIEW, MARK_FAILED, MARK_PAID, REFUND_DUPLICATES, Decision, decide

log = logging.getLogger("engine.reconciler")


@dataclass
class EngineConfig:
    min_age_seconds: int = 30
    lookback_hours: int = 24
    abandon_after_seconds: int = 300
    dry_run: bool = False
    auto_refund_duplicates: bool = True
    max_retries: int = 4
    retry_base_seconds: float = 0.5


def _jsonb(obj) -> Jsonb:
    return Jsonb(obj or {}, dumps=lambda o: json.dumps(o, default=str))


def _age_seconds(txn: dict) -> float:
    ts = txn.get("created_at")
    if not ts:
        return float("inf")
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except ValueError:
        return float("inf")


class Reconciler:
    def __init__(self, db, portal, gateway, config: EngineConfig, worker_id: str = "worker-1",
                 sleep=time.sleep):
        self.db = db
        self.portal = portal
        self.gateway = gateway
        self.cfg = config
        self.worker_id = worker_id
        self.audit = Audit(db)
        self._sleep = sleep

    # ------------------------------------------------------------------ cycle
    def run_cycle(self, trigger: str = "loop") -> dict:
        dry = self.cfg.dry_run
        with self.db.connection() as conn:
            run_id = conn.execute("INSERT INTO recon_runs (dry_run, trigger) VALUES (%s,%s) RETURNING id",
                                  (dry, trigger)).fetchone()["id"]
        counts = {"collected": 0, "mismatches": 0, "resolved": 0, "manual": 0, "errors": 0}
        outcomes: dict[str, int] = {}
        try:
            txns = self._collect()
        except Exception as exc:
            self.audit.log("ERROR", "collect_failed", run_id=run_id, reason=str(exc))
            counts["errors"] += 1
            txns = []
        counts["collected"] = len(txns)
        for txn in txns:
            try:
                outcome = self.process_txn(txn, run_id)
            except Exception as exc:  # one bad txn must never stop the loop
                log.exception("processing txn %s failed", txn.get("txn_id"))
                self.audit.log("ERROR", "process_failed", txn_id=txn.get("txn_id"), run_id=run_id, reason=str(exc))
                outcome = "error"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            if outcome not in ("in_sync", "waiting", "skipped_manual_review_open"):
                counts["mismatches"] += 1
            if outcome in ("resolved", "refunded"):
                counts["resolved"] += 1
            elif outcome == "manual_review":
                counts["manual"] += 1
            elif outcome == "error":
                counts["errors"] += 1
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE recon_runs SET finished_at=now(), collected=%s, mismatches=%s, resolved=%s, manual=%s, "
                "errors=%s WHERE id=%s",
                (counts["collected"], counts["mismatches"], counts["resolved"], counts["manual"],
                 counts["errors"], run_id))
        return {"run_id": run_id, "dry_run": dry, **counts, "outcomes": outcomes}

    def _collect(self) -> list[dict]:
        open_ = self._portal_call(lambda: self.portal.list_transactions(
            [PENDING, UNKNOWN], older_than=self.cfg.min_age_seconds))
        settled = self._portal_call(lambda: self.portal.list_transactions(
            [PAID, FAILED], older_than=self.cfg.min_age_seconds, updated_within_hours=self.cfg.lookback_hours))
        return open_ + settled

    # ------------------------------------------------------------------ per transaction
    def process_txn(self, txn: dict, run_id: int | None = None) -> str:
        txn_id = txn["txn_id"]
        order_id = txn["razorpay_order_id"]
        portal_status = txn["status"]

        if self._has_open_manual_review(txn_id):
            return "skipped_manual_review_open"

        view = self._gateway_or_manual(txn, run_id)
        if view is None:
            return "manual_review"

        decision = decide(portal_status, view.status, view.captured_payment_ids, self.cfg.auto_refund_duplicates)
        if not decision.is_mismatch:
            return "in_sync"
        if (decision.action == MARK_FAILED and view.status == G_NONE
                and _age_seconds(txn) < self.cfg.abandon_after_seconds):
            return "waiting"  # user may still be on the checkout page

        self.audit.log("COLLECT", "candidate", txn_id=txn_id, run_id=run_id, from_status=portal_status,
                       reason=f"portal reports {portal_status}",
                       details={"order_id": order_id, "amount_paise": txn.get("amount_paise"), "worker": self.worker_id})
        self.audit.log("DETECT", decision.mismatch_type or "mismatch", txn_id=txn_id, run_id=run_id,
                       from_status=portal_status, reason=f"portal={portal_status} gateway={view.status}: {decision.reason}",
                       details={"gateway": view.as_dict()})
        self._open_mismatch(txn, portal_status, view.status, decision.mismatch_type, run_id)

        # VERIFY: ask both sides again right before acting. Never act on stale data.
        fresh_txn = self._portal_call(lambda: self.portal.get_transaction(txn_id))
        fresh_view = self._gateway_or_manual(fresh_txn, run_id)
        if fresh_view is None:
            return "manual_review"
        fresh = decide(fresh_txn["status"], fresh_view.status, fresh_view.captured_payment_ids,
                       self.cfg.auto_refund_duplicates)
        if fresh.key() != decision.key():
            self.audit.log("VERIFY", "changed_before_act", txn_id=txn_id, run_id=run_id,
                           from_status=fresh_txn["status"],
                           reason=f"state changed between detect and verify (now portal={fresh_txn['status']}, "
                                  f"gateway={fresh_view.status}); not acting on stale data",
                           details={"gateway": fresh_view.as_dict()})
            if not fresh.is_mismatch:
                self._resolve_mismatches(txn_id, "self-healed before PayFix acted (e.g. late webhook)")
            return "verify_changed"
        self.audit.log("VERIFY", "confirmed", txn_id=txn_id, run_id=run_id, from_status=fresh_txn["status"],
                       reason=f"re-checked gateway: {fresh_view.detail}", details={"gateway": fresh_view.as_dict()})
        self.audit.log("DECIDE", fresh.action, txn_id=txn_id, run_id=run_id, from_status=fresh_txn["status"],
                       reason=fresh.reason, details={"refund_payment_ids": fresh.refund_payment_ids,
                                                     "keep_payment_id": fresh.keep_payment_id})
        if self.cfg.dry_run:
            self.audit.log("ACT", f"would_{fresh.action}", txn_id=txn_id, run_id=run_id,
                           from_status=fresh_txn["status"], reason="DRY_RUN: detect and log only", dry_run=True)
            return "dry_run"
        return self.execute(fresh_txn, fresh, fresh_view, run_id)

    # ------------------------------------------------------------------ ACT
    def execute(self, txn: dict, decision: Decision, view: GatewayView, run_id: int | None = None) -> str:
        txn_id = txn["txn_id"]
        if decision.action == MANUAL_REVIEW:
            self._manual_review(txn, decision.reason, txn["status"], view.status,
                                {"mismatch_type": decision.mismatch_type, "gateway": view.as_dict()}, run_id)
            return "manual_review"

        if decision.action in (MARK_PAID, MARK_FAILED):
            to_status = PAID if decision.action == MARK_PAID else FAILED
            claim_id = self._claim(txn_id, decision.action)
            if claim_id is None:
                self.audit.log("SKIP", "already_claimed", txn_id=txn_id, run_id=run_id, from_status=txn["status"],
                               reason=f"{decision.action} already claimed by another worker/cycle "
                                      f"(UNIQUE(txn_id, action)); exactly-once guard held",
                               details={"worker": self.worker_id})
                return "skipped_duplicate"
            try:
                res = self._portal_call(lambda: self.portal.mark(
                    txn_id, to_status, f"PayFix: {decision.reason}", decision.keep_payment_id, str(claim_id)))
            except (RetriesExhausted, PortalError) as exc:
                self._finish_claim(claim_id, "failed", {"error": str(exc)})
                self._manual_review(txn, f"portal could not be updated: {exc}", txn["status"], view.status, {}, run_id)
                return "manual_review"
            if res.rejected:
                self._finish_claim(claim_id, "failed", {"rejected": True, "from": res.from_status})
                self._manual_review(txn, f"portal rejected {res.from_status} -> {to_status}", res.from_status,
                                    view.status, {}, run_id)
                return "manual_review"
            self._finish_claim(claim_id, "done", {"changed": res.changed, "from": res.from_status})
            self.audit.log("ACT", decision.action, txn_id=txn_id, run_id=run_id, from_status=res.from_status,
                           to_status=to_status, reason=decision.reason,
                           details={"resolution_id": claim_id, "portal_changed": res.changed,
                                    "payment_id": decision.keep_payment_id, "worker": self.worker_id})
            self._resolve_mismatches(txn_id, f"auto-resolved: marked {to_status}")
            if decision.refund_payment_ids:
                self._refund(txn, decision, run_id)
            return "resolved"

        if decision.action == REFUND_DUPLICATES:
            self._refund(txn, decision, run_id)
            self._resolve_mismatches(txn_id, "auto-resolved: duplicate capture refunded")
            return "refunded"
        return "in_sync"

    def _refund(self, txn: dict, decision: Decision, run_id) -> None:
        txn_id = txn["txn_id"]
        for pid in decision.refund_payment_ids:
            claim_id = self._claim(txn_id, f"refund:{pid}")
            if claim_id is None:
                self.audit.log("SKIP", "refund_already_claimed", txn_id=txn_id, run_id=run_id,
                               reason=f"refund of {pid} already claimed", details={"payment_id": pid})
                continue
            try:
                refund = self._gateway_call(lambda: self.gateway.refund(
                    pid, {"reason": "duplicate payment on one order", "kept_payment": decision.keep_payment_id,
                          "txn_id": str(txn_id)}), txn_id, run_id)
            except (RetriesExhausted, PermanentGatewayError) as exc:
                self._finish_claim(claim_id, "failed", {"error": str(exc)})
                self._manual_review(txn, f"refund of {pid} failed: {exc}", txn["status"], "captured", {}, run_id)
                continue
            self._finish_claim(claim_id, "done", {"refund_id": refund.get("id")})
            self.audit.log("REFUND", "refund_duplicate", txn_id=txn_id, run_id=run_id, from_status=txn["status"],
                           reason=f"refunded duplicate capture {pid}, kept {decision.keep_payment_id}",
                           details={"payment_id": pid, "refund_id": refund.get("id"),
                                    "refund_status": refund.get("status")})

    # ------------------------------------------------------------------ helpers
    def _gateway_call(self, fn, txn_id, run_id):
        def on_retry(attempt, exc, delay):
            self.audit.log("RETRY", "gateway_transient_error", txn_id=txn_id, run_id=run_id,
                           reason=f"attempt {attempt} failed ({exc}); retrying in {delay:.2f}s")
        return with_retry(fn, retry_on=(TransientGatewayError,), max_attempts=self.cfg.max_retries,
                          base_delay=self.cfg.retry_base_seconds, on_retry=on_retry, sleep=self._sleep)

    def _gateway_or_manual(self, txn: dict, run_id) -> GatewayView | None:
        txn_id, order_id = txn["txn_id"], txn["razorpay_order_id"]
        try:
            return self._gateway_call(lambda: self.gateway.get_payment_status(order_id), txn_id, run_id)
        except RetriesExhausted as exc:
            self.audit.log("ERROR", "gateway_unreachable", txn_id=txn_id, run_id=run_id, from_status=txn["status"],
                           reason=str(exc))
            self._manual_review(txn, f"gateway unreachable: {exc}", txn["status"], "unclear", {}, run_id)
        except PermanentGatewayError as exc:
            self.audit.log("ERROR", "gateway_error", txn_id=txn_id, run_id=run_id, from_status=txn["status"],
                           reason=str(exc))
            self._manual_review(txn, f"gateway error: {exc}", txn["status"], "unclear", {}, run_id)
        return None

    def _portal_call(self, fn):
        return with_retry(fn, retry_on=(PortalTransientError,), max_attempts=self.cfg.max_retries,
                          base_delay=self.cfg.retry_base_seconds, sleep=self._sleep)

    def _claim(self, txn_id, action: str) -> int | None:
        """Exactly-once: the UNIQUE (txn_id, action) constraint lets only one claimant win, even
        across concurrent workers. Losers get no row back and must not act."""
        with self.db.connection() as conn:
            row = conn.execute(
                "INSERT INTO resolutions (txn_id, action, worker) VALUES (%s,%s,%s) "
                "ON CONFLICT ON CONSTRAINT resolutions_once DO NOTHING RETURNING id",
                (txn_id, action, self.worker_id)).fetchone()
        return row["id"] if row else None

    def _finish_claim(self, claim_id: int, state: str, result: dict) -> None:
        with self.db.connection() as conn:
            conn.execute("UPDATE resolutions SET state=%s, result=%s, finished_at=now() WHERE id=%s",
                         (state, _jsonb(result), claim_id))

    def _open_mismatch(self, txn, portal_status, gateway_status, mismatch_type, run_id) -> None:
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO mismatches (txn_id, razorpay_order_id, amount_paise, portal_status, gateway_status, "
                "mismatch_type, run_id) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (txn_id, mismatch_type) WHERE NOT resolved DO NOTHING",
                (txn["txn_id"], txn.get("razorpay_order_id"), txn.get("amount_paise"), portal_status,
                 gateway_status, mismatch_type or "UNKNOWN", run_id))

    def _resolve_mismatches(self, txn_id, resolution: str) -> None:
        with self.db.connection() as conn:
            conn.execute("UPDATE mismatches SET resolved=true, resolution=%s, resolved_at=now() "
                         "WHERE txn_id=%s AND NOT resolved", (resolution, txn_id))

    def _has_open_manual_review(self, txn_id) -> bool:
        with self.db.connection() as conn:
            return conn.execute("SELECT 1 FROM manual_review WHERE txn_id=%s AND status='open'",
                                (txn_id,)).fetchone() is not None

    def _manual_review(self, txn, reason, portal_status, gateway_status, details, run_id) -> None:
        with self.db.connection() as conn:
            row = conn.execute(
                "INSERT INTO manual_review (txn_id, reason, portal_status, gateway_status, details) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (txn_id) WHERE status='open' DO NOTHING RETURNING id",
                (txn["txn_id"], reason, portal_status, gateway_status, _jsonb(details))).fetchone()
            conn.execute("UPDATE mismatches SET resolution='sent to manual review' WHERE txn_id=%s AND NOT resolved",
                         (txn["txn_id"],))
        if row:
            self.audit.log("MANUAL_REVIEW", "queued", txn_id=txn["txn_id"], run_id=run_id, from_status=portal_status,
                           reason=reason, details={"gateway_status": gateway_status, **(details or {})})
