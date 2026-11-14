"""Transient errors are retried with backoff; stubborn ones go to manual review; verify-before-act;
duplicate captures are refunded exactly once."""
from helpers import audit_rows, new_txn


def _txn(fakes, portal_status="pending", gw_statuses=("captured",)):
    portal, gw = fakes
    txn, order = new_txn(), "order_" + new_txn()[:8]
    portal.add(txn, order, portal_status)
    gw.ensure_order(order)
    for s in gw_statuses:
        gw.add_payment(order, s)
    return portal, gw, txn, order


def test_transient_gateway_errors_are_retried(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _txn(fakes)
    gw.fail_next = 2
    assert make_reconciler(portal, gw).process_txn(portal.get_transaction(txn)) == "resolved"
    with engine_db.connection() as conn:
        retries = conn.execute("SELECT count(*) n FROM audit_log WHERE txn_id=%s AND step='RETRY'", (txn,)).fetchone()["n"]
    assert retries == 2
    assert portal.txns[txn]["status"] == "paid"


def test_stubborn_gateway_errors_go_to_manual_review(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _txn(fakes)
    gw.fail_next = 1000
    assert make_reconciler(portal, gw, max_retries=3).process_txn(portal.get_transaction(txn)) == "manual_review"
    gw.fail_next = 0
    assert portal.mark_calls == []
    assert len(audit_rows(engine_db, txn, "MANUAL_REVIEW")) == 1
    # later cycles leave it for the human
    assert make_reconciler(portal, gw).process_txn(portal.get_transaction(txn)) == "skipped_manual_review_open"


def test_unclear_gateway_state_is_never_guessed(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _txn(fakes, gw_statuses=("authorized",))
    assert make_reconciler(portal, gw).process_txn(portal.get_transaction(txn)) == "manual_review"
    assert portal.mark_calls == []


def test_verify_step_refuses_stale_data(fakes, make_reconciler, engine_db):
    """Webhook lands between DETECT and VERIFY: PayFix must notice and not act."""
    portal, gw, txn, _ = _txn(fakes)
    rec = make_reconciler(portal, gw)
    original_get = portal.get_transaction

    def get_after_webhook(t):
        portal.txns[t]["status"] = "paid"  # the late webhook arrives
        return original_get(t)

    portal.get_transaction = get_after_webhook
    snapshot = dict(portal.txns[txn])
    assert rec.process_txn(snapshot) == "verify_changed"
    assert portal.mark_calls == []
    assert audit_rows(engine_db, txn, "VERIFY")[0]["action"] == "changed_before_act"


def test_old_pending_with_no_payment_is_marked_failed(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _txn(fakes, gw_statuses=())
    assert make_reconciler(portal, gw).process_txn(portal.get_transaction(txn)) == "resolved"
    assert portal.txns[txn]["status"] == "failed"


def test_duplicate_capture_refunded_once(fakes, make_reconciler, engine_db):
    portal, gw, txn, order = _txn(fakes, gw_statuses=("captured", "captured"))
    rec = make_reconciler(portal, gw)
    assert rec.process_txn(portal.get_transaction(txn)) == "resolved"
    assert portal.txns[txn]["status"] == "paid"
    assert len(gw.refunds) == 1
    kept = gw.orders[order][0]["id"]
    assert gw.refunds[0] != kept
    # next cycles: nothing more to do
    assert rec.process_txn(portal.get_transaction(txn)) == "in_sync"
    assert len(gw.refunds) == 1
    assert len(audit_rows(engine_db, txn, "REFUND")) == 1
    print(f"\nPROOF refund: {txn} kept {kept}, refunded {gw.refunds[0]} exactly once")


def test_paid_portal_with_duplicate_refunds_extra(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _txn(fakes, portal_status="paid", gw_statuses=("captured", "captured", "captured"))
    assert make_reconciler(portal, gw).process_txn(portal.get_transaction(txn)) == "refunded"
    assert len(gw.refunds) == 2
    assert portal.mark_calls == []
