"""The engine talks to the portal ONLY through its internal API (never its database)."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

import httpx

from contract import can_transition


class PortalTransientError(Exception):
    pass


class PortalError(Exception):
    pass


@dataclass
class MarkResult:
    changed: bool
    rejected: bool
    from_status: str | None
    to_status: str


class PortalClient(Protocol):
    def list_transactions(self, statuses: list[str], older_than: int,
                          updated_within_hours: int | None = None) -> list[dict]: ...

    def get_transaction(self, txn_id: str) -> dict: ...

    def mark(self, txn_id: str, to_status: str, reason: str, payment_id: str | None,
             resolution_id: str | None) -> MarkResult: ...


class HttpPortalClient:
    def __init__(self, base_url: str, internal_key: str, timeout: float = 10.0):
        self._c = httpx.Client(base_url=base_url, headers={"X-Internal-Key": internal_key}, timeout=timeout)

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self._c.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise PortalTransientError(f"portal unreachable: {exc.__class__.__name__}") from exc
        if r.status_code >= 500 or r.status_code == 429:
            raise PortalTransientError(f"portal HTTP {r.status_code}")
        return r

    def list_transactions(self, statuses, older_than, updated_within_hours=None):
        params = {"status": ",".join(statuses), "older_than": older_than}
        if updated_within_hours:
            params["updated_within_hours"] = updated_within_hours
        r = self._req("GET", "/internal/transactions", params=params)
        if r.status_code != 200:
            raise PortalError(f"list failed HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def get_transaction(self, txn_id):
        r = self._req("GET", f"/internal/transactions/{txn_id}")
        if r.status_code != 200:
            raise PortalError(f"get failed HTTP {r.status_code}")
        return r.json()

    def mark(self, txn_id, to_status, reason, payment_id, resolution_id):
        path = {"paid": "mark-paid", "failed": "mark-failed"}[to_status]
        r = self._req("POST", f"/internal/transactions/{txn_id}/{path}",
                      json={"reason": reason, "razorpay_payment_id": payment_id, "resolution_id": resolution_id})
        if r.status_code not in (200, 409):
            raise PortalError(f"mark failed HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        return MarkResult(d.get("changed", False), d.get("rejected", False), d.get("from_status"), to_status)


class FakePortal:
    """In-memory portal for tests. Counts every mark call so tests can prove exactly-once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.txns: dict[str, dict] = {}
        self.mark_calls: list[tuple[str, str]] = []
        self.fail_next = 0

    def add(self, txn_id: str, order_id: str, status: str, amount_paise: int = 100000) -> None:
        with self._lock:
            self.txns[txn_id] = {"txn_id": txn_id, "razorpay_order_id": order_id, "status": status,
                                 "amount_paise": amount_paise, "razorpay_payment_id": None}

    def list_transactions(self, statuses, older_than, updated_within_hours=None):
        with self._lock:
            return [dict(t) for t in self.txns.values() if t["status"] in statuses]

    def get_transaction(self, txn_id):
        with self._lock:
            return dict(self.txns[txn_id])

    def mark(self, txn_id, to_status, reason, payment_id, resolution_id):
        with self._lock:
            self.mark_calls.append((txn_id, to_status))
            if self.fail_next > 0:
                self.fail_next -= 1
                raise PortalTransientError("fake portal down")
            t = self.txns[txn_id]
            cur = t["status"]
            if cur == to_status:
                return MarkResult(False, False, cur, to_status)
            if not can_transition(cur, to_status):
                return MarkResult(False, True, cur, to_status)
            t["status"] = to_status
            t["razorpay_payment_id"] = t["razorpay_payment_id"] or payment_id
            return MarkResult(True, False, cur, to_status)
