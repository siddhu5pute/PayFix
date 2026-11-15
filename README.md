# PayFix

#⚡**Live Demo:** https://payfix-frontend.onrender.com
# ⚡ PayFix: Payment Reconciliation & Auto-Resolution

> "Because 'contact MIS and wait 2–7 days' should never be the answer."

A student pays an exam fee, the connection drops, the portal says **"Payment failed, wait 2–7 days"**,
and the bank has already taken the money. The portal and the gateway disagree, and nothing is watching.

**PayFix** is an independent backend service that watches for exactly this. It finds payments where
the portal and the gateway disagree, **checks again with the gateway right before acting**, fixes each
one **exactly once**, and writes every step to an **append-only audit log**.

Sandbox only: Razorpay Test Mode or the bundled MockPay gateway. No real money moves.

---

## Run it (one command)

Prerequisite: **Docker Desktop** running. Nothing else (no Python/Node needed locally).

```bash
docker compose up --build -d
```

Open **http://localhost:3000**. First build takes a few minutes; later starts take seconds.

| Page | URL |
|---|---|
| Pay a fee (CampusPay portal) | http://localhost:3000/ |
| PayFix dashboard | http://localhost:3000/dashboard |
| Demo control room (break things on purpose) | http://localhost:3000/control |
| Portal API docs | http://localhost:8000/docs |
| Engine API docs | http://localhost:8100/docs |

```bash
docker compose --profile test run --rm -T e2e   # pre-demo check: runs every scenario, expects 9/9 PASS
docker compose logs -f engine                   # watch the engine's AUDIT lines live
docker compose down                             # stop (keeps data)
docker compose down -v                          # stop and wipe all data (clean slate)
```

Guides: **[docs/SETUP.md](docs/SETUP.md)** (new laptop, Razorpay, going live) · **[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)** (every part explained) · **[docs/DEMO.md](docs/DEMO.md)** (presenter walkthrough).

---

## Architecture

```
                 ┌──────────────────────────────┐
                 │  Gateway (Razorpay Test Mode  │
                 │  or MockPay, same REST API)   │
                 └──▲──────────┬─────────────▲───┘
       create order │          │ signed      │ fetch real status
                    │          │ webhook     │ (+ refund duplicates)
                    │          ▼ (can drop!) │
┌──────────┐  POST /pay ┌───────────────┐   │   ┌─────────────────────┐
│ Frontend │──────────▶│ Portal backend│◀──┼───│ PayFix engine       │
│ React    │           │ FastAPI       │ internal API (X-Internal-Key)│
└────┬─────┘           │ portal DB     │   │   │ FastAPI + worker    │
     │                 └───────────────┘   └───│ engine DB + audit   │
     │  dashboard reads engine API (read-only) ─▶└─────────────────────┘
```

* **Each service has its own Postgres database.** The engine never reads the portal's DB; it uses the
  portal's internal API (`/internal/transactions`, `mark-paid`, `mark-failed`) and the gateway API.
* **Failure injection** in the portal's webhook handler: `DROP_WEBHOOKS`, `DELAY_WEBHOOK_SECONDS`,
  `DUPLICATE_WEBHOOKS` (env defaults, switchable live in the Control Room).

### The engine loop (every `RECON_INTERVAL_SECONDS`)

1. **COLLECT**: pending/unknown payments older than `MIN_AGE_SECONDS` (never race the normal webhook), plus recently settled ones.
2. **DETECT**: compare portal status with `get_payment_status(order_id)` → `captured | failed | none | unclear`.
3. **VERIFY**: ask both sides again right before acting; if anything changed, do nothing.
4. **DECIDE** with the rule table:

| Portal | Gateway | Action |
|---|---|---|
| pending / unknown | captured | mark **PAID** (+ refund any extra captures) |
| pending / unknown | failed / none | mark **FAILED** |
| paid | captured ×2+ | keep first, **refund** the rest |
| paid | not captured | manual review |
| failed | captured | manual review |
| anything | unclear | manual review (never guess) |

5. **ACT exactly once**: `INSERT … ON CONFLICT DO NOTHING` on `UNIQUE (txn_id, action)`; only the winner acts, even with many workers.
6. **LOG**: every step goes to `audit_log`, where UPDATE/DELETE/TRUNCATE are blocked by a DB trigger. Any transaction can be replayed from the log alone.

Transient gateway errors are retried with exponential backoff and jitter; persistent ones go to manual review. `DRY_RUN=true` = detect and log only.

### Shared rules

* Money is **integer paise**, INR. Floats are rejected.
* Statuses: `created → pending → paid | failed | unknown`, `unknown → paid | failed`, `paid → refunded`.
  Enforced in code (`shared/contract.py`) **and** by a Postgres trigger. Rejected moves are logged.
* Webhooks: HMAC-SHA256 of the **raw body** checked against `X-Razorpay-Signature`, deduped on `X-Razorpay-Event-Id`.
* Checkout callback signature (`order_id|payment_id`) is verified but treated as a **hint only**.

---

## Using the real Razorpay sandbox (optional)

1. Razorpay Dashboard → **Test Mode** → Account & Settings → API Keys → Generate.
2. `copy .env.example .env` and set `GATEWAY_MODE=razorpay`, `RAZORPAY_API_BASE=https://api.razorpay.com/v1`,
   `RAZORPAY_KEY_ID=rzp_test_…`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` (any long random string).
3. Add `NGROK_AUTHTOKEN` to `.env` and run `docker compose --profile razorpay up --build -d`.
   ngrok runs as a container; your public address is shown at http://localhost:4040.
4. In Razorpay → Settings → Webhooks add `https://<your-ngrok-address>/webhooks/razorpay` with the same
   secret and events `payment.captured`, `payment.failed`, `order.paid`. The pay button now opens real
   Razorpay Checkout, and the whole site is public at the same address.

Never use `rzp_live_` keys. Never commit `.env`.

## Deploying

* **Frontend → Vercel**: set root to `portal/frontend`, and env vars `VITE_PORTAL_API`, `VITE_ENGINE_API`,
  `VITE_GATEWAY_API` to your public backend URLs (CORS is open by default via `CORS_ORIGINS`).
* **Backends** need a Docker host with Postgres (Render, Railway, Fly.io or any VM) because the engine runs
  a continuous worker loop. Vercel serverless can't host that.

## Repo layout

```
portal/frontend   React + Vite UI (pay form, status page, dashboard, control room)
portal/backend    Portal FastAPI service (orders, webhooks, internal API, failure flags)
engine/           PayFix reconciliation engine (FastAPI + worker loop, audit log)
mockpay/          Razorpay-compatible test gateway for offline demos
shared/           Shared contract: statuses, transitions, money rules
tests/            Proof tests (pytest) + live end-to-end demo check
docs/             Pitch, progress-review deck, setup guide, how-it-works guide, demo script
```

Proof tests (idempotency, state machine, audit replay, webhooks, load): `docker compose --profile test run --rm -T tests`. Logs are saved to `tests/logs/`.

Team: Siddharth (engine) · Arpit (portal backend) · Shubhant & Saurav (frontend, docs).
