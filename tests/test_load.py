"""PROOF (load): 100 concurrent simulated transactions, 4 engine workers racing on them with the fake
gateway. No duplicate resolutions, every final status correct."""
import random
import threading
import time
from collections import Counter

from helpers import new_txn

N = 100
WORKERS = 4

SCENARIOS = {
    # name: (portal start, gateway payments, expected portal final, expected refunds)
    "missed_capture": ("pending", ["captured"], "paid", 0),
    "unknown_capture": ("unknown", ["failed", "captured"], "paid", 0),
    "missed_failure": ("pending", ["failed"], "failed", 0),
    "abandoned": ("pending", [], "failed", 0),
    "double_charge": ("pending", ["captured", "captured"], "paid", 1),
    "unclear": ("pending", ["authorized"], "pending", 0),          # -> manual review, untouched
    "in_sync_paid": ("paid", ["captured"], "paid", 0),
}


def test_load_100_concurrent_transactions(fakes, make_reconciler, engine_db):
    random.seed(42)
    portal, gw = fakes
    plan = {}
    for i in range(N):
        name = list(SCENARIOS)[i % len(SCENARIOS)]
        start, payments, _, _ = SCENARIOS[name]
        txn, order = new_txn(), f"order_load{i:04d}"
        portal.add(txn, order, start)
        gw.ensure_order(order)
        for s in payments:
            gw.add_payment(order, s)
        plan[txn] = name
    gw.fail_next = 3  # sprinkle transient gateway errors (fewer than max_retries, so all recover)

    workers = [make_reconciler(portal, gw, worker_id=f"load-w{i}") for i in range(WORKERS)]
    barrier = threading.Barrier(WORKERS)
    summaries = []

    def run(rec):
        barrier.wait()
        for _ in range(2):  # two cycles each, all racing
            summaries.append(rec.run_cycle("load-test"))

    t0 = time.time()
    threads = [threading.Thread(target=run, args=(w,)) for w in workers]
    [t.start() for t in threads]
    [t.join() for t in threads]
    elapsed = time.time() - t0

    # 1. correct final statuses
    wrong = {t: (plan[t], portal.txns[t]["status"]) for t in plan
             if portal.txns[t]["status"] != SCENARIOS[plan[t]][2]}
    assert not wrong, wrong

    # 2. no duplicate resolutions: each txn's portal status was changed at most once
    calls = Counter(t for t, _ in portal.mark_calls)
    dupes = {t: n for t, n in calls.items() if n > 1}
    assert not dupes, dupes
    needs_fix = sum(1 for t in plan if SCENARIOS[plan[t]][0] != SCENARIOS[plan[t]][2])
    assert len(calls) == needs_fix

    # 3. refunds exactly once per double charge
    assert len(gw.refunds) == len(set(gw.refunds)) == sum(SCENARIOS[plan[t]][3] for t in plan)

    # 4. DB agrees: one resolution row per (txn, action), and one ACT per fixed txn
    txns = list(plan)
    with engine_db.connection() as conn:
        acts = conn.execute("SELECT txn_id, count(*) n FROM audit_log WHERE step='ACT' AND NOT dry_run "
                            "AND txn_id = ANY(%s::uuid[]) GROUP BY txn_id", (txns,)).fetchall()
        manual = conn.execute("SELECT count(*) n FROM manual_review WHERE txn_id = ANY(%s::uuid[])",
                              (txns,)).fetchone()["n"]
        skips = conn.execute("SELECT count(*) n FROM audit_log WHERE step='SKIP' AND txn_id = ANY(%s::uuid[])",
                             (txns,)).fetchone()["n"]
    assert all(r["n"] == 1 for r in acts)
    assert len(acts) == needs_fix
    assert manual == sum(1 for t in plan if plan[t] == "unclear")

    print(f"\nPROOF load: {N} txns x {WORKERS} concurrent workers x 2 cycles in {elapsed:.2f}s")
    print(f"   scenarios: {dict(Counter(plan.values()))}")
    print(f"   portal status changes: {len(calls)} (expected {needs_fix}), duplicates: 0")
    print(f"   refunds: {len(gw.refunds)} unique, manual review: {manual}, "
          f"lost races skipped by exactly-once guard: {skips}")
