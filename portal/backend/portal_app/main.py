"""CampusPay demo portal backend. Deliberately thin: no reconciliation logic lives here."""
from __future__ import annotations

import hmac

import anyio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from contract import CREATED, FAILED, PAID, PAYMENT_STATUSES, PENDING, UNKNOWN, validate_amount_paise

from . import db, gateway
from .config import settings
from .flags import flags
from .payments import payment_public, record_history, transition
from .signatures import verify_checkout_signature
from .webhooks import ingest

logging.basicConfig(level=logging.INFO, format="%(asctime)s portal %(name)s %(levelname)s %(message)s")
log = logging.getLogger("portal")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_pool(settings.database_url)
    db.apply_schema()
    log.info("portal ready (gateway_mode=%s, api_base=%s)", settings.gateway_mode, settings.razorpay_api_base)
    yield
    db.close_pool()


app = FastAPI(title="CampusPay Portal Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ auth helpers
def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    if not settings.internal_api_key or not x_internal_key or not hmac.compare_digest(
            x_internal_key, settings.internal_api_key):
        raise HTTPException(401, "invalid internal key")


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if settings.demo_mode:
        return
    if not settings.admin_key or not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(401, "admin key required")


# ------------------------------------------------------------------ public
@app.get("/health")
def health():
    with db.pool().connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "service": "portal-backend"}


@app.get("/config/public")
def public_config():
    return {"gateway_mode": settings.gateway_mode, "key_id": settings.razorpay_key_id,
            "merchant_name": settings.merchant_name, "demo_mode": settings.demo_mode}


class PayIn(BaseModel):
    payer_name: str = Field(min_length=2, max_length=100)
    payer_email: EmailStr
    purpose: str = Field(min_length=2, max_length=120)
    amount_paise: int

    @field_validator("amount_paise", mode="before")
    @classmethod
    def _int_paise(cls, v):
        if isinstance(v, float) or isinstance(v, str):
            raise ValueError("amount_paise must be an integer (paise), not a float/string")
        return validate_amount_paise(v)


@app.post("/pay")
def pay(body: PayIn):
    if body.amount_paise < 100:
        raise HTTPException(422, "minimum amount is 100 paise (Rs 1.00)")
    txn_id = uuid.uuid4()
    with db.pool().connection() as conn:
        conn.execute(
            "INSERT INTO payments (txn_id, payer_name, payer_email, purpose, amount_paise, status) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (txn_id, body.payer_name, body.payer_email, body.purpose, body.amount_paise, CREATED))
        record_history(conn, txn_id, None, CREATED, "portal:/pay", True, "payment record created")
    try:
        order = gateway.create_order(body.amount_paise, receipt=f"txn_{str(txn_id)[:8]}",
                                     notes={"txn_id": str(txn_id), "purpose": body.purpose})
    except gateway.GatewayError as exc:
        log.error("order creation failed for txn=%s: %s", txn_id, exc)
        raise HTTPException(502, f"could not create gateway order: {exc}")
    with db.pool().connection() as conn:
        conn.execute("UPDATE payments SET razorpay_order_id=%s WHERE txn_id=%s", (order["id"], txn_id))
        transition(conn, txn_id, PENDING, source="portal:/pay",
                   reason="gateway order created, awaiting payment", details={"order_id": order["id"]})
    return {
        "txn_id": str(txn_id), "razorpay_order_id": order["id"], "amount_paise": body.amount_paise,
        "currency": "INR", "key_id": settings.razorpay_key_id, "gateway_mode": settings.gateway_mode,
        "name": settings.merchant_name, "description": body.purpose,
        "prefill": {"name": body.payer_name, "email": body.payer_email},
    }


class VerifyIn(BaseModel):
    txn_id: uuid.UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@app.post("/payments/verify")
def verify(body: VerifyIn):
    """Checkout callback. A valid signature is only a HINT: status becomes paid only via a
    verified webhook or the reconciliation engine, never because a browser said so."""
    with db.pool().connection() as conn:
        row = conn.execute("SELECT * FROM payments WHERE txn_id=%s FOR UPDATE", (body.txn_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "unknown txn")
        valid = (row["razorpay_order_id"] == body.razorpay_order_id and verify_checkout_signature(
            body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature, settings.razorpay_key_secret))
        record_history(conn, body.txn_id, row["status"], row["status"], "checkout:callback", valid,
                       "checkout signature verified (hint only, awaiting gateway confirmation)" if valid
                       else "checkout signature INVALID, ignored",
                       {"payment_id": body.razorpay_payment_id})
        if valid and not row["razorpay_payment_id"]:
            conn.execute("UPDATE payments SET razorpay_payment_id=%s WHERE txn_id=%s",
                         (body.razorpay_payment_id, body.txn_id))
        status = row["status"]
    if not valid:
        raise HTTPException(400, "invalid checkout signature")
    return {"signature_valid": True, "status": status,
            "note": "Signature valid. Final status is set by the gateway webhook or PayFix reconciliation."}


class ClientEventIn(BaseModel):
    type: str  # checkout_interrupted | checkout_failed | checkout_dismissed
    detail: str | None = None


@app.post("/payments/{txn_id}/client-event")
def client_event(txn_id: uuid.UUID, body: ClientEventIn):
    """The browser reports something went wrong. The portal now honestly does not know."""
    with db.pool().connection() as conn:
        if body.type == "checkout_interrupted":
            res = transition(conn, txn_id, UNKNOWN, source="checkout:client",
                             reason="connection lost during checkout, outcome unknown",
                             details={"detail": body.detail})
            if res.not_found:
                raise HTTPException(404, "unknown txn")
            return res.as_dict()
        row = conn.execute("SELECT status FROM payments WHERE txn_id=%s", (txn_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "unknown txn")
        record_history(conn, txn_id, row["status"], row["status"], "checkout:client", True,
                       f"client reported {body.type} (hint only)", {"detail": body.detail})
        return {"txn_id": str(txn_id), "status": row["status"], "changed": False}


@app.get("/payments/{txn_id}")
def get_payment(txn_id: uuid.UUID):
    with db.pool().connection() as conn:
        row = conn.execute("SELECT * FROM payments WHERE txn_id=%s", (txn_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "unknown txn")
        hist = conn.execute(
            "SELECT from_status, to_status, source, accepted, reason, created_at FROM status_history "
            "WHERE txn_id=%s ORDER BY id", (txn_id,)).fetchall()
    out = payment_public(row)
    out["history"] = [{**h, "created_at": h["created_at"].isoformat()} for h in hist]
    return out


@app.get("/payments")
def list_payments(limit: int = Query(50, ge=1, le=500)):
    with db.pool().connection() as conn:
        rows = conn.execute("SELECT * FROM payments ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    return [payment_public(r) for r in rows]


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    raw = await request.body()  # RAW bytes: the signature is computed over these exact bytes
    result = await anyio.to_thread.run_sync(
        lambda: ingest(raw, request.headers.get("x-razorpay-signature"),
                       request.headers.get("x-razorpay-event-id")))
    code = result.pop("http", 200)
    return JSONResponse(result, status_code=code)


@app.get("/webhooks/recent")
def recent_webhooks(limit: int = Query(30, ge=1, le=200)):
    with db.pool().connection() as conn:
        rows = conn.execute(
            "SELECT event_id, event_type, received_at, processed, outcome, "
            "payload->'payload'->'payment'->'entity'->>'order_id' AS order_id "
            "FROM webhook_events ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
        rejected = conn.execute("SELECT count(*) AS n FROM rejected_webhooks").fetchone()["n"]
    return {"events": [{**r, "received_at": r["received_at"].isoformat()} for r in rows],
            "rejected_signature_count": rejected}


# ------------------------------------------------------------------ internal API (engine only)
@app.get("/internal/transactions", dependencies=[Depends(require_internal_key)])
def internal_list(status: str = Query("pending,unknown"), older_than: int = Query(0, ge=0),
                  updated_within_hours: int | None = Query(None, ge=1), limit: int = Query(500, ge=1, le=5000)):
    statuses = [s for s in status.split(",") if s]
    bad = [s for s in statuses if s not in PAYMENT_STATUSES]
    if bad:
        raise HTTPException(422, f"unknown status {bad}")
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than)
    sql = "SELECT * FROM payments WHERE status = ANY(%s) AND created_at <= %s AND razorpay_order_id IS NOT NULL"
    params: list = [statuses, cutoff]
    if updated_within_hours:
        sql += " AND updated_at >= %s"
        params.append(datetime.now(timezone.utc) - timedelta(hours=updated_within_hours))
    sql += " ORDER BY created_at LIMIT %s"
    params.append(limit)
    with db.pool().connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [payment_public(r) for r in rows]


@app.get("/internal/transactions/{txn_id}", dependencies=[Depends(require_internal_key)])
def internal_get(txn_id: uuid.UUID):
    with db.pool().connection() as conn:
        row = conn.execute("SELECT * FROM payments WHERE txn_id=%s", (txn_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "unknown txn")
    return payment_public(row)


class MarkIn(BaseModel):
    reason: str = "resolved by PayFix reconciliation"
    razorpay_payment_id: str | None = None
    resolution_id: str | None = None


def _mark(txn_id: uuid.UUID, to_status: str, body: MarkIn):
    with db.pool().connection() as conn:
        res = transition(conn, txn_id, to_status, source="payfix-engine", reason=body.reason,
                         payment_id=body.razorpay_payment_id, details={"resolution_id": body.resolution_id})
    if res.not_found:
        raise HTTPException(404, "unknown txn")
    if res.rejected:
        return JSONResponse(res.as_dict(), status_code=409)
    return res.as_dict()


@app.post("/internal/transactions/{txn_id}/mark-paid", dependencies=[Depends(require_internal_key)])
def mark_paid(txn_id: uuid.UUID, body: MarkIn):
    return _mark(txn_id, PAID, body)


@app.post("/internal/transactions/{txn_id}/mark-failed", dependencies=[Depends(require_internal_key)])
def mark_failed(txn_id: uuid.UUID, body: MarkIn):
    return _mark(txn_id, FAILED, body)


# ------------------------------------------------------------------ demo control room
class FlagsIn(BaseModel):
    drop_webhooks: bool | None = None
    delay_webhook_seconds: int | None = Field(default=None, ge=0, le=600)
    duplicate_webhooks: bool | None = None


@app.get("/admin/flags")
def get_flags():
    return flags.snapshot()


@app.put("/admin/flags", dependencies=[Depends(require_admin)])
def put_flags(body: FlagsIn):
    new = flags.update(**body.model_dump())
    log.warning("failure flags changed: %s", new)
    return new


class TransitionTestIn(BaseModel):
    to_status: str


@app.post("/admin/payments/{txn_id}/force-transition", dependencies=[Depends(require_admin)])
def force_transition(txn_id: uuid.UUID, body: TransitionTestIn):
    """Demo only: attempt an arbitrary transition to show the state machine rejecting it."""
    if body.to_status not in PAYMENT_STATUSES:
        raise HTTPException(422, "unknown status")
    with db.pool().connection() as conn:
        res = transition(conn, txn_id, body.to_status, source="admin:force-transition",
                         reason="manual transition attempt from demo control room")
    if res.not_found:
        raise HTTPException(404, "unknown txn")
    return JSONResponse(res.as_dict(), status_code=409 if res.rejected else 200)
