"""PayFix reconciliation engine: FastAPI (read API for the dashboard) + background worker loop."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .audit import Audit, _row
from .config import settings
from .db import Database
from .gateway import RazorpayGateway
from .portal_client import HttpPortalClient
from .reconciler import EngineConfig, Reconciler

logging.basicConfig(level=logging.INFO, format="%(asctime)s engine %(name)s %(levelname)s %(message)s")
log = logging.getLogger("engine")
logging.getLogger("httpx").setLevel(logging.WARNING)


class State:
    db: Database
    reconciler: Reconciler
    stop = threading.Event()
    run_lock = threading.Lock()
    last_run: dict | None = None
    worker: threading.Thread | None = None


S = State()


def _run(trigger: str) -> dict | None:
    if not S.run_lock.acquire(blocking=False):
        return None
    try:
        S.last_run = S.reconciler.run_cycle(trigger)
        if S.last_run["mismatches"]:
            log.info("cycle %s", S.last_run)
        return S.last_run
    finally:
        S.run_lock.release()


def _loop() -> None:
    log.info("worker loop started: every %ss, MIN_AGE=%ss, DRY_RUN=%s", settings.recon_interval_seconds,
             settings.min_age_seconds, S.reconciler.cfg.dry_run)
    while not S.stop.is_set():
        try:
            _run("loop")
        except Exception:
            log.exception("cycle crashed; continuing")
        S.stop.wait(settings.recon_interval_seconds)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    S.db = Database(settings.database_url)
    S.db.apply_schema()
    cfg = EngineConfig(min_age_seconds=settings.min_age_seconds, lookback_hours=settings.lookback_hours,
                       abandon_after_seconds=settings.abandon_after_seconds,
                       dry_run=settings.dry_run, auto_refund_duplicates=settings.auto_refund_duplicates,
                       max_retries=settings.max_retries, retry_base_seconds=settings.retry_base_seconds)
    S.reconciler = Reconciler(
        S.db, HttpPortalClient(settings.portal_internal_url, settings.internal_api_key),
        RazorpayGateway(settings.razorpay_api_base, settings.razorpay_key_id, settings.razorpay_key_secret),
        cfg, worker_id="engine-loop")
    if settings.run_worker:
        S.worker = threading.Thread(target=_loop, daemon=True, name="recon-loop")
        S.worker.start()
    yield
    S.stop.set()
    S.db.close()


app = FastAPI(title="PayFix Reconciliation Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


def _rows(sql: str, params=()) -> list[dict]:
    with S.db.connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = {}
        for k, v in r.items():
            d[k] = v.isoformat() if hasattr(v, "isoformat") else (str(v) if k == "txn_id" and v else v)
        out.append(d)
    return out


@app.get("/health")
def health():
    with S.db.connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "service": "payfix-engine"}


@app.get("/api/config")
def get_config():
    c = S.reconciler.cfg
    return {"recon_interval_seconds": settings.recon_interval_seconds, "min_age_seconds": c.min_age_seconds,
            "dry_run": c.dry_run, "auto_refund_duplicates": c.auto_refund_duplicates,
            "abandon_after_seconds": c.abandon_after_seconds, "worker_running": bool(S.worker and S.worker.is_alive()),
            "gateway": "razorpay" if "api.razorpay.com" in settings.razorpay_api_base else "mockpay",
            "demo_mode": settings.demo_mode, "last_run": S.last_run}


class ConfigIn(BaseModel):
    dry_run: bool | None = None
    min_age_seconds: int | None = None


@app.put("/api/config")
def put_config(body: ConfigIn):
    if not settings.demo_mode:
        raise HTTPException(403, "runtime config changes are only allowed in DEMO_MODE")
    if body.dry_run is not None:
        S.reconciler.cfg.dry_run = body.dry_run
    if body.min_age_seconds is not None:
        S.reconciler.cfg.min_age_seconds = max(0, body.min_age_seconds)
    log.warning("engine config changed: dry_run=%s min_age=%s", S.reconciler.cfg.dry_run,
                S.reconciler.cfg.min_age_seconds)
    return get_config()


@app.post("/api/recon/run")
def run_now():
    result = _run("manual")
    if result is None:
        raise HTTPException(409, "a reconciliation cycle is already running")
    return result


@app.get("/api/stats")
def stats():
    with S.db.connection() as conn:
        q = lambda sql: conn.execute(sql).fetchone()["n"]  # noqa: E731
        return {
            "mismatches_total": q("SELECT count(*) n FROM mismatches"),
            "mismatches_open": q("SELECT count(*) n FROM mismatches WHERE NOT resolved"),
            "auto_resolved": q("SELECT count(*) n FROM resolutions WHERE state='done' AND action IN ('mark_paid','mark_failed')"),
            "marked_paid": q("SELECT count(*) n FROM resolutions WHERE state='done' AND action='mark_paid'"),
            "marked_failed": q("SELECT count(*) n FROM resolutions WHERE state='done' AND action='mark_failed'"),
            "refunds": q("SELECT count(*) n FROM resolutions WHERE state='done' AND action LIKE 'refund:%%'"),
            "manual_review_open": q("SELECT count(*) n FROM manual_review WHERE status='open'"),
            "audit_entries": q("SELECT count(*) n FROM audit_log"),
            "runs": q("SELECT count(*) n FROM recon_runs"),
            "amount_recovered_paise": q("SELECT COALESCE(sum(m.amount_paise),0) n FROM mismatches m "
                                        "WHERE m.resolution LIKE 'auto-resolved: marked paid%%'"),
        }


@app.get("/api/mismatches")
def mismatches(limit: int = Query(100, le=1000)):
    return _rows("SELECT * FROM mismatches ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/manual-review")
def manual_review():
    return _rows("SELECT * FROM manual_review ORDER BY id DESC LIMIT 200")


@app.get("/api/runs")
def runs(limit: int = Query(20, le=200)):
    return _rows("SELECT * FROM recon_runs WHERE mismatches > 0 OR trigger='manual' OR errors > 0 "
                 "ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/audit")
def audit(txn_id: str | None = None, limit: int = Query(200, le=2000)):
    if txn_id:
        return Audit(S.db).history(txn_id)
    with S.db.connection() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
    return [_row(r) for r in rows]


@app.get("/api/transactions/{txn_id}/replay")
def replay(txn_id: str):
    return Audit(S.db).replay(txn_id)


@app.get("/api/gateway/orders/{order_id}")
def gateway_order(order_id: str):
    """Read-only: what the gateway (Razorpay or MockPay) currently says about an order."""
    from .gateway import PermanentGatewayError, TransientGatewayError
    try:
        return S.reconciler.gateway.order_snapshot(order_id)
    except (PermanentGatewayError, TransientGatewayError) as exc:
        raise HTTPException(502, f"gateway: {exc}")
