"""MockPay: a small Razorpay-compatible test gateway.

Why it exists: the Razorpay sandbox cannot fail on command, and the demo must run on a laptop
with no internet keys. MockPay implements the subset of the Razorpay REST API PayFix uses
(orders, order payments, payments, refunds) with the same JSON shapes, the same Basic auth,
the same Checkout signature (HMAC-SHA256 of "order_id|payment_id" with the key secret) and the
same signed webhooks (HMAC-SHA256 of the raw body with the webhook secret,
X-Razorpay-Signature + X-Razorpay-Event-Id headers).

Point RAZORPAY_API_BASE at https://api.razorpay.com/v1 instead and the exact same portal and
engine code talks to real Razorpay Test Mode.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import string
import threading
import time
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s mockpay %(levelname)s %(message)s")
log = logging.getLogger("mockpay")

KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_mockpay000001")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "mockpay_key_secret")
WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "mockpay_webhook_secret")
WEBHOOK_URL = os.environ.get("MOCKPAY_WEBHOOK_URL", "http://portal-backend:8000/webhooks/razorpay")
WEBHOOK_DELAY = float(os.environ.get("MOCKPAY_WEBHOOK_DELAY_SECONDS", "0.7"))
STATE_FILE = Path(os.environ.get("MOCKPAY_STATE_FILE", "/data/mockpay_state.json"))

app = FastAPI(title="MockPay (Razorpay-compatible test gateway)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_lock = threading.RLock()
_state: dict = {"orders": {}, "payments": {}, "refunds": {}, "flaky_remaining": 0}


def _load() -> None:
    global _state
    try:
        if STATE_FILE.exists():
            _state = json.loads(STATE_FILE.read_text())
            _state.setdefault("flaky_remaining", 0)
    except Exception as exc:  # corrupt file should not stop the demo
        log.warning("could not load state: %s", exc)


def _save() -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_state))
        tmp.replace(STATE_FILE)
    except Exception as exc:
        log.warning("could not save state: %s", exc)


_load()

_ALPHABET = string.ascii_letters + string.digits


def _rid(prefix: str) -> str:
    return prefix + "_" + "".join(secrets.choice(_ALPHABET) for _ in range(14))


def _now() -> int:
    return int(time.time())


def require_auth(request: Request) -> None:
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        raise HTTPException(401, {"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}})
    try:
        user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        raise HTTPException(401, {"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}})
    if not (hmac.compare_digest(user, KEY_ID) and hmac.compare_digest(pwd, KEY_SECRET)):
        raise HTTPException(401, {"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}})
    # Optional transient-failure injection so the engine's retry/backoff can be demonstrated
    with _lock:
        if _state.get("flaky_remaining", 0) > 0:
            _state["flaky_remaining"] -= 1
            _save()
            raise HTTPException(503, {"error": {"code": "SERVER_ERROR", "description": "MockPay injected transient error"}})


# ---------------------------------------------------------------- REST API (Razorpay subset)
class OrderIn(BaseModel):
    amount: int
    currency: str = "INR"
    receipt: str | None = None
    notes: dict | None = None


@app.post("/v1/orders", dependencies=[Depends(require_auth)])
def create_order(body: OrderIn):
    if body.amount < 100:
        raise HTTPException(400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "The amount must be atleast INR 1.00"}})
    order = {
        "id": _rid("order"), "entity": "order", "amount": body.amount, "amount_paid": 0,
        "amount_due": body.amount, "currency": body.currency, "receipt": body.receipt,
        "offer_id": None, "status": "created", "attempts": 0, "notes": body.notes or {},
        "created_at": _now(),
    }
    with _lock:
        _state["orders"][order["id"]] = order
        _save()
    return order


@app.get("/v1/orders/{order_id}", dependencies=[Depends(require_auth)])
def get_order(order_id: str):
    with _lock:
        order = _state["orders"].get(order_id)
    if not order:
        raise HTTPException(400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
    return order


@app.get("/v1/orders/{order_id}/payments", dependencies=[Depends(require_auth)])
def get_order_payments(order_id: str):
    with _lock:
        if order_id not in _state["orders"]:
            raise HTTPException(400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
        items = [p for p in _state["payments"].values() if p["order_id"] == order_id]
    items.sort(key=lambda p: p["created_at"], reverse=True)  # Razorpay returns newest first
    return {"entity": "collection", "count": len(items), "items": items}


@app.get("/v1/payments/{payment_id}", dependencies=[Depends(require_auth)])
def get_payment(payment_id: str):
    with _lock:
        p = _state["payments"].get(payment_id)
    if not p:
        raise HTTPException(400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
    return p


class RefundIn(BaseModel):
    amount: int | None = None
    notes: dict | None = None
    receipt: str | None = None


@app.post("/v1/payments/{payment_id}/refund", dependencies=[Depends(require_auth)])
def refund_payment(payment_id: str, body: RefundIn | None = None):
    body = body or RefundIn()
    with _lock:
        p = _state["payments"].get(payment_id)
        if not p:
            raise HTTPException(400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
        if p["status"] != "captured":
            raise HTTPException(400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "The payment has been fully refunded already" if p["status"] == "refunded" else "Payment is not captured"}})
        amount = body.amount or p["amount"]
        refund = {"id": _rid("rfnd"), "entity": "refund", "amount": amount, "currency": p["currency"],
                  "payment_id": payment_id, "notes": body.notes or {}, "receipt": body.receipt,
                  "status": "processed", "speed_processed": "normal", "created_at": _now()}
        _state["refunds"][refund["id"]] = refund
        p["amount_refunded"] = p.get("amount_refunded", 0) + amount
        if p["amount_refunded"] >= p["amount"]:
            p["status"] = "refunded"
            p["refund_status"] = "full"
        _save()
    _fire_webhook_threadsafe("refund.processed", payment=p, refund=refund)
    return refund


# ---------------------------------------------------------------- Checkout simulation (browser)
class CheckoutIn(BaseModel):
    outcome: str = "success"  # success | fail | authorized
    email: str | None = None
    contact: str | None = None


@app.post("/checkout/{order_id}/pay")
async def checkout_pay(order_id: str, body: CheckoutIn):
    """What Razorpay Checkout does when the user completes (or fails) a test payment."""
    with _lock:
        order = _state["orders"].get(order_id)
        if not order:
            raise HTTPException(404, {"error": {"code": "BAD_REQUEST_ERROR", "description": "order not found"}})
        pid = _rid("pay")
        status = {"success": "captured", "fail": "failed", "authorized": "authorized"}.get(body.outcome)
        if status is None:
            raise HTTPException(400, {"error": {"description": "outcome must be success|fail|authorized"}})
        payment = {
            "id": pid, "entity": "payment", "amount": order["amount"], "currency": order["currency"],
            "status": status, "order_id": order_id, "invoice_id": None, "international": False,
            "method": "upi", "amount_refunded": 0, "refund_status": None,
            "captured": status == "captured", "description": order.get("receipt"),
            "email": body.email or "student@example.com", "contact": body.contact or "+919000090000",
            "vpa": "success@razorpay", "notes": order.get("notes", {}), "fee": None, "tax": None,
            "error_code": "BAD_REQUEST_ERROR" if status == "failed" else None,
            "error_description": "Payment failed (MockPay test failure)" if status == "failed" else None,
            "error_reason": "payment_failed" if status == "failed" else None,
            "created_at": _now(),
        }
        _state["payments"][pid] = payment
        order["attempts"] += 1
        if status == "captured":
            order["amount_paid"] = min(order["amount"], order["amount_paid"] + payment["amount"])
            order["amount_due"] = order["amount"] - order["amount_paid"]
            order["status"] = "paid"
        elif order["status"] == "created":
            order["status"] = "attempted"
        _save()
        order_snapshot = dict(order)

    if status == "captured":
        asyncio.create_task(_send_webhook("payment.captured", payment=payment))
        asyncio.create_task(_send_webhook("order.paid", payment=payment, order=order_snapshot, extra_delay=0.3))
        sig = hmac.new(KEY_SECRET.encode(), f"{order_id}|{pid}".encode(), hashlib.sha256).hexdigest()
        return {"razorpay_payment_id": pid, "razorpay_order_id": order_id, "razorpay_signature": sig}
    if status == "failed":
        asyncio.create_task(_send_webhook("payment.failed", payment=payment))
        return {"error": {"code": "BAD_REQUEST_ERROR", "description": payment["error_description"],
                          "reason": "payment_failed", "metadata": {"order_id": order_id, "payment_id": pid}}}
    asyncio.create_task(_send_webhook("payment.authorized", payment=payment))
    return {"authorized_only": True, "razorpay_payment_id": pid, "razorpay_order_id": order_id}


# ---------------------------------------------------------------- Webhooks
def _event_body(event: str, payment: dict | None, order: dict | None = None, refund: dict | None = None) -> dict:
    payload, contains = {}, []
    if payment:
        payload["payment"] = {"entity": payment}
        contains.append("payment")
    if order:
        payload["order"] = {"entity": order}
        contains.append("order")
    if refund:
        payload["refund"] = {"entity": refund}
        contains.append("refund")
    return {"entity": "event", "account_id": "acc_MockPay00000001", "event": event,
            "contains": contains, "payload": payload, "created_at": _now()}


async def _send_webhook(event: str, payment=None, order=None, refund=None, extra_delay: float = 0.0) -> None:
    await asyncio.sleep(WEBHOOK_DELAY + extra_delay)
    raw = json.dumps(_event_body(event, payment, order, refund), separators=(",", ":")).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    event_id = _rid("evt")
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature,
               "X-Razorpay-Event-Id": event_id, "User-Agent": "MockPay-Webhooks/1.0"}
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(WEBHOOK_URL, content=raw, headers=headers)
            log.info("webhook %s %s -> %s", event, event_id, r.status_code)
            if r.status_code < 500:
                return
        except Exception as exc:
            log.warning("webhook %s attempt %d failed: %s", event, attempt + 1, exc)
        await asyncio.sleep(2 ** attempt)


def _fire_webhook_threadsafe(event: str, **kw) -> None:
    def runner():
        asyncio.run(_send_webhook(event, **kw))
    threading.Thread(target=runner, daemon=True).start()


# ---------------------------------------------------------------- Demo/admin helpers
class FlakyIn(BaseModel):
    fail_next_n: int = 3


@app.post("/admin/flaky")
def set_flaky(body: FlakyIn):
    with _lock:
        _state["flaky_remaining"] = max(0, body.fail_next_n)
        _save()
    return {"flaky_remaining": _state["flaky_remaining"]}


@app.get("/admin/orders/{order_id}")
def admin_order(order_id: str):
    """Unauthenticated read used by the demo UI to show 'what the gateway says' side by side."""
    with _lock:
        order = _state["orders"].get(order_id)
        if not order:
            raise HTTPException(404, "not found")
        payments = [p for p in _state["payments"].values() if p["order_id"] == order_id]
    return {"order": order, "payments": sorted(payments, key=lambda p: p["created_at"])}


@app.get("/admin/info")
def info():
    return {"gateway": "mockpay", "key_id": KEY_ID, "webhook_url": WEBHOOK_URL,
            "flaky_remaining": _state.get("flaky_remaining", 0)}


@app.get("/health")
def health():
    return {"ok": True}
