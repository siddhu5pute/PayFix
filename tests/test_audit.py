"""PROOF: the audit log is append-only and a transaction's history can be replayed from it alone."""
import psycopg
import pytest

from helpers import audit_rows, new_txn
from engine_app.audit import Audit


def _resolved_txn(fakes, make_reconciler):
    portal, gw = fakes
    txn, order = new_txn(), "order_" + new_txn()[:8]
    portal.add(txn, order, "unknown")
    gw.add_payment(order, "failed")
    gw.add_payment(order, "captured")
    assert make_reconciler(portal, gw).process_txn(portal.get_transaction(txn)) == "resolved"
    return txn


def test_audit_log_is_append_only(fakes, make_reconciler, engine_db):
    txn = _resolved_txn(fakes, make_reconciler)
    with engine_db.connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("UPDATE audit_log SET reason='tampered' WHERE txn_id=%s", (txn,))
    with engine_db.connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("DELETE FROM audit_log WHERE txn_id=%s", (txn,))
    with engine_db.connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("TRUNCATE audit_log")
    assert len(audit_rows(engine_db, txn)) >= 5
    print(f"\nPROOF audit: UPDATE, DELETE and TRUNCATE on audit_log all blocked by trigger")


def test_replay_reconstructs_history(fakes, make_reconciler, engine_db):
    txn = _resolved_txn(fakes, make_reconciler)
    r = Audit(engine_db).replay(txn)
    steps = [e["step"] for e in r["events"]]
    assert steps == ["COLLECT", "DETECT", "VERIFY", "DECIDE", "ACT"]
    assert r["initial_status"] == "unknown"
    assert r["final_status"] == "paid"
    assert r["actions_taken"] == 1
    print("\nPROOF audit replay for", txn)
    for e in r["events"]:
        print(f"   {e['created_at']}  {e['step']:<8} {e['action']:<34} state={e['state_after']:<8} {e['reason']}")


def test_dry_run_logs_but_never_acts(fakes, make_reconciler, engine_db):
    portal, gw = fakes
    txn, order = new_txn(), "order_" + new_txn()[:8]
    portal.add(txn, order, "pending")
    gw.add_payment(order, "captured")
    out = make_reconciler(portal, gw, dry_run=True).process_txn(portal.get_transaction(txn))
    assert out == "dry_run"
    assert portal.mark_calls == []
    assert portal.txns[txn]["status"] == "pending"
    acts = audit_rows(engine_db, txn, "ACT")
    assert len(acts) == 1 and acts[0]["dry_run"] is True
    assert Audit(engine_db).replay(txn)["final_status"] == "pending"
