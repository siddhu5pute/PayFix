"""Live end-to-end demo check against the running stack (MockPay mode).

    docker compose --profile test run --rm -T e2e

Runs every demo scenario once and prints PASS/FAIL. Restores the flags it changes.
Log saved to tests/logs/e2e_demo_latest.log.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

PORTAL = os.environ.get("PORTAL_URL", "http://localhost:8000")
ENGINE = os.environ.get("ENGINE_URL", "http://localhost:8100")
GATEWAY = os.environ.get("MOCKPAY_URL", "http://localhost:9000")
LOG = Path(__file__).parent / "logs" / "e2e_demo_latest.log"

c = httpx.Client(timeout=30)
lines: list[str] = []
results: list[tuple[str, bool, str]] = []


def say(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {msg}"
    print(line, flush=True)
    lines.append(line)


def pay(purpose: str) -> dict:
    r = c.post(f"{PORTAL}/pay", json={"payer_name": "Sample Student", "payer_email": "student@example.com",
                                      "purpose": purpose, "amount_paise": 100000})
    r.raise_for_status()
    return r.json()


def checkout(order: dict, outcome: str) -> dict:
    return c.post(f"{GATEWAY}/checkout/{order['razorpay_order_id']}/pay", json={"outcome": outcome}).json()


def verify(order: dict, resp: dict) -> None:
    c.post(f"{PORTAL}/payments/verify", json={"txn_id": order["txn_id"], **resp})


def status(txn: str) -> str:
    return c.get(f"{PORTAL}/payments/{txn}").json()["status"]


def wait_status(txn: str, want: str, seconds: float = 8) -> str:
    end = time.time() + seconds
    s = status(txn)
    while s != want and time.time() < end:
        time.sleep(0.5)
        s = status(txn)
    return s


def run_engine() -> dict:
    for _ in range(10):
        r = c.post(f"{ENGINE}/api/recon/run")
        if r.status_code == 200:
            return r.json()
        time.sleep(1)  # the loop is mid-cycle; try again
    raise RuntimeError("engine busy")


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    say(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def main() -> int:
    for name, url in (("portal", PORTAL), ("engine", ENGINE), ("mockpay", GATEWAY)):
        c.get(f"{url}/health").raise_for_status()
    say("all services healthy")

    flags_before = c.get(f"{PORTAL}/admin/flags").json()
    cfg_before = c.get(f"{ENGINE}/api/config").json()
    try:
        c.put(f"{ENGINE}/api/config", json={"min_age_seconds": 600, "dry_run": False})  # hold the loop off

        # 1. Normal payment: webhook confirms it
        c.put(f"{PORTAL}/admin/flags", json={"drop_webhooks": False, "delay_webhook_seconds": 0, "duplicate_webhooks": False})
        o = pay("Scenario 1 - normal")
        verify(o, checkout(o, "success"))
        check("normal payment -> paid by webhook", wait_status(o["txn_id"], "paid") == "paid")

        # 2. THE incident: webhook dropped + connection lost -> PayFix fixes it
        c.put(f"{PORTAL}/admin/flags", json={"drop_webhooks": True})
        o = pay("Scenario 2 - dropped webhook")
        checkout(o, "success")
        c.post(f"{PORTAL}/payments/{o['txn_id']}/client-event", json={"type": "checkout_interrupted"})
        time.sleep(2)
        stuck = status(o["txn_id"])
        gw = c.get(f"{GATEWAY}/admin/orders/{o['razorpay_order_id']}").json()["payments"][0]["status"]
        say(f"      portal says {stuck.upper()}  !=  gateway says {gw.upper()}")
        c.put(f"{ENGINE}/api/config", json={"min_age_seconds": 0})
        run_engine()
        replay = c.get(f"{ENGINE}/api/transactions/{o['txn_id']}/replay").json()
        steps = [e["step"] for e in replay["events"]]
        check("dropped webhook -> PayFix marks paid", status(o["txn_id"]) == "paid" and stuck == "unknown",
              f"steps={steps}")
        check("exactly one ACT in audit log", replay["actions_taken"] == 1)
        run_engine()
        replay2 = c.get(f"{ENGINE}/api/transactions/{o['txn_id']}/replay").json()
        check("second engine run does nothing more", replay2["actions_taken"] == 1)

        # 3. Payment fails
        c.put(f"{PORTAL}/admin/flags", json={"drop_webhooks": False})
        o = pay("Scenario 3 - failure")
        checkout(o, "fail")
        check("failed payment -> failed", wait_status(o["txn_id"], "failed") == "failed")

        # 4. Charged twice -> keep first, refund the extra
        c.put(f"{PORTAL}/admin/flags", json={"drop_webhooks": True})
        o = pay("Scenario 4 - double charge")
        verify(o, checkout(o, "success"))
        checkout(o, "success")
        time.sleep(1.5)
        run_engine()
        pays = c.get(f"{GATEWAY}/admin/orders/{o['razorpay_order_id']}").json()["payments"]
        check("double charge -> paid + 1 refund", status(o["txn_id"]) == "paid"
              and sorted(p["status"] for p in pays) == ["captured", "refunded"], str([p["status"] for p in pays]))

        # 5. Authorized only -> manual review, never guess
        o = pay("Scenario 5 - unclear")
        checkout(o, "authorized")
        time.sleep(1)
        run_engine()
        manual = [m for m in c.get(f"{ENGINE}/api/manual-review").json() if m["txn_id"] == o["txn_id"]]
        check("unclear gateway state -> manual review", len(manual) == 1 and status(o["txn_id"]) == "pending")

        # 6. Illegal transition rejected
        paid_txn = replay["txn_id"]
        r = c.post(f"{PORTAL}/admin/payments/{paid_txn}/force-transition", json={"to_status": "pending"})
        check("paid -> pending rejected by state machine", r.status_code == 409 and status(paid_txn) == "paid")

        # 7. Forged webhook rejected
        r = c.post(f"{PORTAL}/webhooks/razorpay", content=b'{"event":"payment.captured"}',
                   headers={"X-Razorpay-Signature": "forged", "Content-Type": "application/json"})
        check("forged webhook signature rejected", r.status_code == 400)
    finally:
        c.put(f"{PORTAL}/admin/flags", json={k: flags_before[k] for k in flags_before})
        c.put(f"{ENGINE}/api/config", json={"min_age_seconds": cfg_before["min_age_seconds"],
                                            "dry_run": cfg_before["dry_run"]})
        say("flags and engine config restored")

    passed = sum(ok for _, ok, _ in results)
    say(f"RESULT: {passed}/{len(results)} checks passed")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
