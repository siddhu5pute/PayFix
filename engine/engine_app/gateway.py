"""Gateway client interface: get_payment_status(order_id) -> captured | failed | none | unclear.

RazorpayGateway talks to Razorpay's REST API (or MockPay, which speaks the same API).
FakeGateway is an in-memory implementation for unit, idempotency and load tests.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from contract import G_CAPTURED, G_FAILED, G_NONE, G_UNCLEAR


class TransientGatewayError(Exception):
    """Network errors, timeouts, 429 and 5xx: worth retrying."""


class PermanentGatewayError(Exception):
    """4xx other than 429: retrying will not help."""


@dataclass
class GatewayView:
    status: str
    captured_payment_ids: list[str] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status, "captured_payment_ids": self.captured_payment_ids,
                "payments": self.payments, "detail": self.detail}


def classify(payments: list[dict]) -> GatewayView:
    """Map Razorpay payment entities of ONE order to a single gateway verdict.

    Razorpay payment.status values: created, authorized, captured, refunded, failed.
    """
    summary = sorted(
        ({"id": p.get("id"), "status": p.get("status"), "amount": p.get("amount"),
          "created_at": p.get("created_at", 0)} for p in payments),
        key=lambda p: (p["created_at"] or 0, p["id"] or ""))
    statuses = [p["status"] for p in summary]
    captured = [p["id"] for p in summary if p["status"] == "captured"]
    if captured:
        if any(s in ("authorized", "created", "refunded") for s in statuses):
            # captured AND something in flight / already refunded: let the rule table decide on
            # captured but expose the detail
            return GatewayView(G_CAPTURED, captured, summary, "captured (other attempts in flight or refunded)")
        return GatewayView(G_CAPTURED, captured, summary, f"{len(captured)} captured payment(s)")
    if not summary:
        return GatewayView(G_NONE, [], summary, "no payment attempts on this order")
    if all(s == "failed" for s in statuses):
        return GatewayView(G_FAILED, [], summary, f"{len(summary)} failed attempt(s), none captured")
    # authorized-but-not-captured, created (in progress), refunded: we cannot be sure. Never guess.
    return GatewayView(G_UNCLEAR, [], summary, "payment state not final: " + ",".join(statuses))


class GatewayClient(Protocol):
    def get_payment_status(self, order_id: str) -> GatewayView: ...

    def refund(self, payment_id: str, notes: dict | None = None) -> dict: ...


class RazorpayGateway:
    def __init__(self, api_base: str, key_id: str, key_secret: str, timeout: float = 10.0):
        self._client = httpx.Client(base_url=api_base, auth=(key_id, key_secret), timeout=timeout)

    def _req(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise TransientGatewayError(f"{exc.__class__.__name__}: {exc}") from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise TransientGatewayError(f"gateway HTTP {r.status_code}")
        if r.status_code >= 400:
            try:
                desc = r.json().get("error", {}).get("description", r.text)
            except Exception:
                desc = r.text
            raise PermanentGatewayError(f"gateway HTTP {r.status_code}: {desc}")
        return r.json()

    def get_payment_status(self, order_id: str) -> GatewayView:
        data = self._req("GET", f"/orders/{order_id}/payments")
        return classify(data.get("items", []))

    def refund(self, payment_id: str, notes: dict | None = None) -> dict:
        return self._req("POST", f"/payments/{payment_id}/refund", json={"notes": notes or {}})

    def order_snapshot(self, order_id: str) -> dict:
        """Raw order + its payments, for the read-only 'what does the gateway say' view."""
        order = self._req("GET", f"/orders/{order_id}")
        payments = self._req("GET", f"/orders/{order_id}/payments").get("items", [])
        return {"order": order, "payments": sorted(payments, key=lambda p: p.get("created_at", 0))}


class FakeGateway:
    """Thread-safe in-memory gateway for tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.orders: dict[str, list[dict]] = {}
        self.fail_next = 0
        self.permanent_fail_orders: set[str] = set()
        self.status_calls = 0
        self.refunds: list[str] = []
        self._seq = 0

    def add_payment(self, order_id: str, status: str) -> str:
        with self._lock:
            self._seq += 1
            pid = f"pay_fake{self._seq:08d}"
            self.orders.setdefault(order_id, []).append(
                {"id": pid, "status": status, "amount": 100000, "created_at": self._seq})
            return pid

    def ensure_order(self, order_id: str) -> None:
        with self._lock:
            self.orders.setdefault(order_id, [])

    def get_payment_status(self, order_id: str) -> GatewayView:
        with self._lock:
            self.status_calls += 1
            if self.fail_next > 0:
                self.fail_next -= 1
                raise TransientGatewayError("fake transient error")
            if order_id in self.permanent_fail_orders:
                raise PermanentGatewayError("fake permanent error")
            payments = [dict(p) for p in self.orders.get(order_id, [])]
        return classify(payments)

    def refund(self, payment_id: str, notes: dict | None = None) -> dict:
        with self._lock:
            for payments in self.orders.values():
                for p in payments:
                    if p["id"] == payment_id:
                        if p["status"] != "captured":
                            raise PermanentGatewayError("payment not captured")
                        p["status"] = "refunded"
                        self.refunds.append(payment_id)
                        return {"id": f"rfnd_{payment_id}", "payment_id": payment_id, "status": "processed"}
        raise PermanentGatewayError("unknown payment")
