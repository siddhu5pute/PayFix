"""PROOF: the same resolution fired twice, concurrently, produces exactly ONE action."""
import threading

from helpers import audit_rows, new_txn
from engine_app.rules import decide


def _setup(fakes):
    portal, gw = fakes
    txn, order = new_txn(), "order_" + new_txn()[:8]
    portal.add(txn, order, "pending")
    gw.add_payment(order, "captured")
    return portal, gw, txn, order


def test_concurrent_execute_yields_one_action(fakes, make_reconciler, engine_db):
    portal, gw, txn, order = _setup(fakes)
    view = gw.get_payment_status(order)
    decision = decide("pending", view.status, view.captured_payment_ids)
    workers = [make_reconciler(portal, gw, worker_id=f"worker-{i}") for i in range(2)]
    barrier = threading.Barrier(2)
    results = []

    def fire(rec):
        barrier.wait()  # release both at the same instant
        results.append(rec.execute(portal.get_transaction(txn), decision, view))

    threads = [threading.Thread(target=fire, args=(w,)) for w in workers]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(results) == ["resolved", "skipped_duplicate"]
    assert portal.mark_calls == [(txn, "paid")]  # the portal was called exactly once
    with engine_db.connection() as conn:
        n = conn.execute("SELECT count(*) AS n FROM resolutions WHERE txn_id=%s", (txn,)).fetchone()["n"]
    assert n == 1
    assert len(audit_rows(engine_db, txn, "ACT")) == 1
    assert len(audit_rows(engine_db, txn, "SKIP")) == 1
    print(f"\nPROOF idempotency: 2 concurrent resolutions for {txn} -> results={sorted(results)}, "
          f"portal calls={len(portal.mark_calls)}, resolutions rows={n}, ACT entries=1")


def test_concurrent_full_pipeline_many_workers(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _setup(fakes)
    workers = [make_reconciler(portal, gw, worker_id=f"w{i}") for i in range(5)]
    barrier = threading.Barrier(5)
    outcomes = []

    def run(rec):
        barrier.wait()
        outcomes.append(rec.process_txn(portal.get_transaction(txn)))

    threads = [threading.Thread(target=run, args=(w,)) for w in workers]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert outcomes.count("resolved") == 1, outcomes
    assert len([c for c in portal.mark_calls if c[0] == txn]) == 1
    assert len(audit_rows(engine_db, txn, "ACT")) == 1
    assert portal.txns[txn]["status"] == "paid"
    print(f"\nPROOF idempotency: 5 workers raced on {txn}: outcomes={sorted(outcomes)}; exactly one ACT")


def test_repeated_cycles_do_not_reapply(fakes, make_reconciler, engine_db):
    portal, gw, txn, _ = _setup(fakes)
    rec = make_reconciler(portal, gw)
    first = rec.process_txn(portal.get_transaction(txn))
    second = rec.process_txn(portal.get_transaction(txn))
    assert first == "resolved" and second == "in_sync"
    assert len(portal.mark_calls) == 1
