"""Unit tests: rule table and gateway classification (no DB, no network)."""
import pytest

from engine_app.gateway import classify
from engine_app.retry import RetriesExhausted, with_retry
from engine_app.rules import MANUAL_REVIEW, MARK_FAILED, MARK_PAID, NONE, REFUND_DUPLICATES, decide


@pytest.mark.parametrize("portal,gw,captured,action", [
    ("pending", "captured", ["p1"], MARK_PAID),
    ("unknown", "captured", ["p1"], MARK_PAID),
    ("pending", "failed", [], MARK_FAILED),
    ("unknown", "none", [], MARK_FAILED),
    ("pending", "unclear", [], MANUAL_REVIEW),
    ("paid", "captured", ["p1"], NONE),
    ("paid", "captured", ["p1", "p2"], REFUND_DUPLICATES),
    ("paid", "failed", [], MANUAL_REVIEW),
    ("paid", "none", [], MANUAL_REVIEW),
    ("paid", "unclear", [], MANUAL_REVIEW),
    ("failed", "captured", ["p1"], MANUAL_REVIEW),
    ("failed", "failed", [], NONE),
    ("failed", "unclear", [], MANUAL_REVIEW),
])
def test_rule_table(portal, gw, captured, action):
    assert decide(portal, gw, captured).action == action


def test_pending_with_duplicates_marks_paid_and_refunds_extras():
    d = decide("pending", "captured", ["p1", "p2", "p3"])
    assert d.action == MARK_PAID and d.keep_payment_id == "p1" and d.refund_payment_ids == ["p2", "p3"]


@pytest.mark.parametrize("statuses,expected", [
    ([], "none"),
    (["failed"], "failed"),
    (["failed", "failed"], "failed"),
    (["failed", "captured"], "captured"),
    (["authorized"], "unclear"),
    (["created"], "unclear"),
    (["refunded"], "unclear"),
])
def test_classify(statuses, expected):
    payments = [{"id": f"p{i}", "status": s, "created_at": i} for i, s in enumerate(statuses)]
    assert classify(payments).status == expected


def test_classify_keeps_first_capture_first():
    v = classify([{"id": "b", "status": "captured", "created_at": 2}, {"id": "a", "status": "captured", "created_at": 1}])
    assert v.captured_payment_ids == ["a", "b"]


def test_retry_backoff_then_success_and_exhaustion():
    calls, delays = {"n": 0}, []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("boom")
        return "ok"

    assert with_retry(flaky, retry_on=(TimeoutError,), max_attempts=4, base_delay=1, sleep=delays.append) == "ok"
    assert len(delays) == 2
    with pytest.raises(RetriesExhausted):
        with_retry(lambda: (_ for _ in ()).throw(TimeoutError()), retry_on=(TimeoutError,), max_attempts=3,
                   sleep=lambda s: None)
