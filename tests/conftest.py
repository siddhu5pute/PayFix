"""Shared fixtures. Tests use real Postgres (separate *_test databases) and NEVER the real
Razorpay: the engine uses FakeGateway/FakePortal, the portal's order creation is stubbed."""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "shared", ROOT / "portal" / "backend", ROOT / "engine"):
    sys.path.insert(0, str(p))

PORTAL_ADMIN = os.environ.get("TEST_PORTAL_DB_ADMIN_URL", "postgresql://portal:portal@localhost:5434/portal")
ENGINE_ADMIN = os.environ.get("TEST_ENGINE_DB_ADMIN_URL", "postgresql://engine:engine@localhost:5435/engine")


def _fresh_db(admin_url: str, name: str) -> str:
    for attempt in range(5):
        try:
            with psycopg.connect(admin_url, autocommit=True) as conn:
                conn.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
                conn.execute(f"CREATE DATABASE {name}")
            break
        except psycopg.errors.UniqueViolation:
            time.sleep(0.5 * (attempt + 1))
    base, _, _ = admin_url.rpartition("/")
    return f"{base}/{name}"


PORTAL_TEST_URL = _fresh_db(PORTAL_ADMIN, "portal_test")
ENGINE_TEST_URL = _fresh_db(ENGINE_ADMIN, "engine_test")

# Portal settings are read at import time, so set the env first.
os.environ.update({
    "PORTAL_DATABASE_URL": PORTAL_TEST_URL,
    "RAZORPAY_KEY_ID": "rzp_test_unit",
    "RAZORPAY_KEY_SECRET": "unit_key_secret",
    "RAZORPAY_WEBHOOK_SECRET": "unit_webhook_secret",
    "RAZORPAY_API_BASE": "http://gateway.invalid/v1",
    "INTERNAL_API_KEY": "unit-internal-key",
    "DEMO_MODE": "true",
    "GATEWAY_MODE": "mock",
})


@pytest.fixture(scope="session")
def portal_client():
    from fastapi.testclient import TestClient

    from portal_app import gateway as portal_gateway
    from portal_app.main import app

    def fake_create_order(amount_paise, receipt, notes):
        return {"id": "order_" + uuid.uuid4().hex[:14], "amount": amount_paise, "currency": "INR", "status": "created"}

    portal_gateway.create_order = fake_create_order
    with TestClient(app) as client:
        yield client


@pytest.fixture
def portal_flags():
    from portal_app.flags import flags
    before = flags.snapshot()
    yield flags
    flags.update(**before)


@pytest.fixture(scope="session")
def engine_db():
    from engine_app.db import Database
    db = Database(ENGINE_TEST_URL, max_size=40)
    db.apply_schema()
    yield db
    db.close()


@pytest.fixture
def fakes():
    from engine_app.gateway import FakeGateway
    from engine_app.portal_client import FakePortal
    return FakePortal(), FakeGateway()


@pytest.fixture
def make_reconciler(engine_db):
    from engine_app.reconciler import EngineConfig, Reconciler

    def make(portal, gateway, worker_id="w1", **cfg):
        cfg.setdefault("min_age_seconds", 0)
        cfg.setdefault("retry_base_seconds", 0.001)
        return Reconciler(engine_db, portal, gateway, EngineConfig(**cfg), worker_id=worker_id,
                          sleep=lambda s: None)
    return make

