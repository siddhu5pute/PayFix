# How PayFix works, end to end

This is the guide for the team: what every part does, why it is built that way, and where in the code to
look. Read your own section closely before the review; skim the rest.

---

## 1. The big picture

```
 Student's browser
      │  (1) fill form, click Pay
      ▼
 ┌──────────────┐  (2) create order   ┌──────────────────────────┐
 │ Portal       │────────────────────▶│ Gateway                  │
 │ backend      │                     │ Razorpay Test Mode       │
 │ + portal DB  │◀────────────────────│ (or MockPay offline)     │
 └──────▲───────┘  (4) signed webhook └────────────▲─────────────┘
        │             (may be lost!)               │
        │ (6) internal API:                        │ (5) "what really happened
        │ list stuck payments, mark paid/failed    │      to this order?"
 ┌──────┴───────────────────────────────────────────┴──┐
 │ PayFix engine  + engine DB (mismatches, audit log)  │
 └──────────────────────────▲──────────────────────────┘
                            │ (7) read-only
                       Dashboard
```

Two independent systems each hold a belief about a payment:
* the **portal** (CampusPay) believes what its webhook told it;
* the **gateway** (Razorpay) knows what actually happened to the money.

Usually they agree. When the confirmation is lost (step 4), they disagree, and nothing in a normal portal
notices. **PayFix is the referee**: a separate service with its own database that keeps checking the two
against each other and fixes disagreements safely.

### Containers (`docker-compose.yml`)

| Container | Port | What it is |
|---|---|---|
| `frontend` | 3000 | React app served by nginx; nginx also forwards `/api/*` and `/webhooks/*` to the services |
| `portal-backend` | 8000 | FastAPI: orders, webhooks, internal API, failure flags |
| `portal-db` | 5434 | Postgres for the portal only |
| `engine` | 8100 | FastAPI + background worker: the reconciliation engine |
| `engine-db` | 5435 | Postgres for the engine only |
| `mockpay` | 9000 | Razorpay-compatible test gateway (used when no Razorpay keys are set) |
| `ngrok` | 4040 | Public HTTPS tunnel (only with `--profile razorpay`) |

**Why two databases?** The engine must be an *independent* referee. If it read the portal's tables
directly, a portal bug or schema change could silently break it. It only uses the portal's API, like any
outside service would.

---

## 2. Shared rules: `shared/contract.py`

Both services import this one file, so they can never disagree about the rules.

* **Money** is always an integer number of **paise** (`₹1,000 = 100000`). Floats are rejected
  (`validate_amount_paise`): `0.1 + 0.2 ≠ 0.3` in floating point, and money must be exact.
* **Statuses**: `created`, `pending`, `paid`, `failed`, `unknown`, `refunded`.
* **Allowed transitions** (`ALLOWED_TRANSITIONS`):

```
created ──▶ pending ──▶ paid ──▶ refunded
               │  ╲
               │   ╲──▶ failed
               ▼
            unknown ──▶ paid / failed
```

Nothing leaves `paid` or `failed` (except a documented refund). A payment that was confirmed can never
be "un-confirmed" by a late or forged message.

---

## 3. Portal backend: `portal/backend/portal_app/` (owner: Arpit)

| File | Job |
|---|---|
| `main.py` | All HTTP endpoints |
| `schema.sql` | Tables + the state-machine trigger |
| `payments.py` | `transition()`: the only way a status changes |
| `webhooks.py` | Webhook verification, dedupe, failure flags |
| `signatures.py` | HMAC checks |
| `gateway.py` | Creates orders on Razorpay/MockPay |
| `flags.py` | DROP / DELAY / DUPLICATE switches |

### 3.1 Life of a payment

1. **`POST /pay`**: validates the form, inserts the payment as `created`, asks the gateway to create an
   **order** (`POST /v1/orders`, amount in paise), stores `razorpay_order_id`, moves it to `pending`.
   Returns what the browser needs to open Checkout.
2. The browser opens **Razorpay Checkout** (or MockPay's test checkout) and the student pays.
3. **`POST /payments/verify`**: Checkout hands the browser `payment_id`, `order_id` and a `signature` =
   `HMAC_SHA256(order_id + "|" + payment_id, key_secret)`. We check it, record the payment id, and
   **do not mark it paid**. The browser is a *hint*, never the source of truth: in a real outage this
   is exactly the message that never arrives.
4. **`POST /webhooks/razorpay`**: Razorpay's server tells our server what happened. This is what marks it
   `paid` (or `failed`).

### 3.2 Webhook handling, in order (`webhooks.py → ingest`)

1. **Verify the signature first.** `X-Razorpay-Signature` must equal
   `HMAC_SHA256(raw_request_body, webhook_secret)`. It must be the **raw bytes**: re-serialising the JSON
   changes spacing and breaks the signature. A forged or tampered webhook gets `400` and is logged in
   `rejected_webhooks`.
2. **Event id**: from the `X-Razorpay-Event-Id` header (fallback: hash of the body).
3. **DROP_WEBHOOKS** on? Store it as "dropped", answer `200 OK`, do nothing else. Razorpay thinks it was
   delivered, which is exactly what makes lost webhooks dangerous.
4. **Dedupe**: `INSERT … ON CONFLICT (event_id) DO NOTHING`. If the row already existed, it's a duplicate
   delivery: answer `200`, change nothing. (Razorpay may deliver the same event more than once.)
5. **DELAY_WEBHOOK_SECONDS** > 0? Process it later in a background thread.
6. **Process**: `payment.captured` / `order.paid` → `paid`; `payment.failed` → `failed`.
7. **DUPLICATE_WEBHOOKS** on? Re-deliver the same signed event once more, to prove step 4 holds.

### 3.3 The state machine, twice (`payments.py → transition`)

1. `SELECT … FOR UPDATE` locks the payment row, so two requests can't change it at the same time.
2. Same status already? Do nothing (idempotent).
3. Not allowed by the contract? **Reject**, write an `accepted=false` row to `status_history`, return 409.
4. Otherwise update, and write an `accepted=true` row to `status_history`.

Backstop: a Postgres **trigger** (`enforce_payment_transition` in `schema.sql`) checks every UPDATE
against the `allowed_transitions` table. Even a raw SQL `UPDATE payments SET status='paid'` on a failed
payment is refused by the database itself.

### 3.4 Internal API (only the engine uses it)
Protected by the `X-Internal-Key` header (compared in constant time):
* `GET /internal/transactions?status=pending,unknown&older_than=20`
* `POST /internal/transactions/{txn_id}/mark-paid` and `/mark-failed`. These go through the same
  `transition()`, so the engine can't break the state machine either.

---

## 4. Reconciliation engine: `engine/engine_app/` (owner: Siddharth)

| File | Job |
|---|---|
| `main.py` | Starts the worker loop; read-only API for the dashboard |
| `reconciler.py` | The loop: collect → detect → verify → decide → act → log |
| `gateway.py` | `get_payment_status(order_id)`: Razorpay + Fake implementations |
| `portal_client.py` | Talks to the portal's internal API (HTTP + Fake) |
| `rules.py` | The rule table (`decide`), pure function |
| `audit.py` | Append-only audit log and replay |
| `retry.py` | Exponential backoff with jitter |
| `schema.sql` | `mismatches`, `resolutions`, `manual_review`, `audit_log`, `recon_runs` |

### 4.1 The loop (every `RECON_INTERVAL_SECONDS`, default 10)

**COLLECT.** Ask the portal for `pending`/`unknown` payments **older than `MIN_AGE_SECONDS`** (20), plus
recently settled ones. MIN_AGE stops us racing a webhook that is just a little slow.

**DETECT.** For each, ask the gateway `GET /v1/orders/{id}/payments` and reduce it to one word
(`gateway.classify`):

| Gateway payments on the order | Verdict |
|---|---|
| at least one `captured` | `captured` |
| none at all | `none` |
| all `failed` | `failed` |
| `authorized` / `created` / only `refunded` | `unclear` |

Compare with the portal's status. No disagreement → move on (and log nothing, to keep the log readable).

**VERIFY.** Ask **both** sides again immediately before acting. If anything changed (e.g. the webhook
arrived a second ago), don't act on stale data: log "changed before act" and stop.

**DECIDE** (`rules.decide`):

| Portal | Gateway | Action |
|---|---|---|
| pending / unknown | captured | mark **paid** (+ refund any extra captures) |
| pending / unknown | failed / none | mark **failed** (`none` only after `ABANDON_AFTER_SECONDS`) |
| paid | captured twice or more | keep the first, **refund** the rest |
| paid | anything else | **manual review** |
| failed | captured | **manual review** (money taken, portal says failed) |
| anything | unclear | **manual review**: never guess |

**ACT, exactly once.**
```sql
INSERT INTO resolutions (txn_id, action, worker) VALUES (…)
ON CONFLICT ON CONSTRAINT resolutions_once DO NOTHING RETURNING id;
```
`resolutions_once` is `UNIQUE (txn_id, action)`. If two workers (or two cycles) try at the same instant,
Postgres lets exactly one insert succeed. The winner gets an id back and calls the portal; the loser gets
nothing back, logs `SKIP already_claimed` and stops. The test suite races 5 workers on one payment, and
4 workers on 100 payments, and checks this.

**LOG.** Every step is a row in `audit_log`. A trigger (`audit_log_append_only`) raises an error on any
UPDATE, DELETE or TRUNCATE, so history can't be rewritten, even by us.

### 4.2 Replay
`GET /api/transactions/{txn_id}/replay` rebuilds a payment's story **only from the audit log**: starting
status, every step, every action, final status. The dashboard timeline is this.

### 4.3 When things go wrong
* **Gateway hiccup** (timeout, 5xx, 429): retried with exponential backoff + jitter (`retry.py`), each
  retry logged as `RETRY`. Still failing after `GATEWAY_MAX_RETRIES` → **manual review**.
* **Permanent gateway error** (e.g. unknown order) → manual review.
* **Portal rejects the change** (409) → manual review.
* A payment with an open manual-review item is skipped by later cycles, so it isn't processed again
  while it waits for a human.
* **DRY_RUN=true**: does everything except ACT, and logs `would_mark_paid` etc.

### 4.4 Duplicate payments
If an order has two captured payments, PayFix keeps the earliest and refunds the others via
`POST /v1/payments/{id}/refund`, each guarded by its own `UNIQUE (txn_id, "refund:<payment_id>")` claim,
so a refund can never happen twice.

---

## 5. MockPay: `mockpay/app.py`

A small server that copies the parts of Razorpay's API we use: orders, order payments, payments, refunds,
with the same JSON shapes, Basic auth, Checkout signature and signed webhooks (`X-Razorpay-Signature`,
`X-Razorpay-Event-Id`). Its test checkout lets the demo choose an outcome (success / fail / authorized),
like Razorpay's own test bank page does.

Because the shapes match, the portal and engine code is **identical** in both modes; only
`RAZORPAY_API_BASE` changes (`http://mockpay:9000/v1` vs `https://api.razorpay.com/v1`).

`POST /admin/flaky` makes MockPay return 503 for the next N calls, to show the engine's retries.

---

## 6. Frontend: `portal/frontend/src/` (owners: Shubhant, Saurav)

| Page | File | Shows |
|---|---|---|
| Pay fee `/` | `pages/PayPage.jsx` | Form → `POST /pay` → Razorpay Checkout (or `components/MockCheckout.jsx`) |
| Status `/status/:id` | `pages/StatusPage.jsx` | Live status chip, **portal vs gateway** side by side, portal history, PayFix audit trail |
| My payments `/payments` | `pages/PaymentsPage.jsx` | All payments, portal's view |
| Dashboard `/dashboard` | `pages/DashboardPage.jsx` | Engine stats, mismatches and resolutions, manual review queue, runs, live audit feed, timeline replay |
| Control room `/control` | `pages/ControlRoom.jsx` | Failure flags, DRY_RUN, MIN_AGE, "run now", gateway chaos, webhooks received, state-machine test |

`api.js` holds every call. Pages poll every 2–4 seconds (`usePoll` in `components/ui.jsx`), which is why
the status flips by itself. Amounts typed in rupees are converted to paise with string maths, not floats
(`toPaise` in `PayPage.jsx`).

nginx (`nginx.conf`) serves the built app and forwards `/api/portal/*`, `/api/engine/*`, `/api/gateway/*`
and `/webhooks/*` to the right container, so the browser (and Razorpay) only ever see one address.

---

## 7. Tests: `tests/`

Run all: `docker compose --profile test run --rm -T tests` (logs saved in `tests/logs/`).
Unit tests never call real Razorpay: the engine uses `FakeGateway` and `FakePortal`, and the portal's
order creation is stubbed. They use real Postgres (temporary `*_test` databases), because the
exactly-once guarantee lives in the database.

| File | Proves |
|---|---|
| `test_idempotency.py` | Same fix fired concurrently by 2 (and 5) workers → exactly one action |
| `test_state_machine.py` | Illegal moves rejected and logged; DB trigger blocks raw SQL; floats rejected |
| `test_audit.py` | Audit log can't be updated/deleted/truncated; replay rebuilds history; DRY_RUN never acts |
| `test_webhooks.py` | Forged/tampered signatures → 400; duplicates ignored; DROP/DELAY/DUPLICATE flags work |
| `test_resilience.py` | Retries, manual review on stubborn errors, verify-before-act, duplicate refunds |
| `test_load.py` | 100 payments × 4 concurrent workers: no duplicates, all final statuses correct |
| `test_rules.py` | Every row of the rule table and gateway classification |
| `e2e_demo.py` | The live demo, against the running stack (MockPay mode): 9 checks |

---

## 8. Settings (`.env` / `docker-compose.yml`)

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_MODE` | `mock` | `razorpay` makes the frontend open real Razorpay Checkout |
| `RAZORPAY_API_BASE` | MockPay | `https://api.razorpay.com/v1` for real Razorpay |
| `RAZORPAY_KEY_ID` / `_SECRET` | MockPay test values | Razorpay **test** keys |
| `RAZORPAY_WEBHOOK_SECRET` | MockPay value | Must match the secret in Razorpay's webhook settings |
| `INTERNAL_API_KEY` | dev value | Shared secret between engine and portal |
| `RECON_INTERVAL_SECONDS` | 10 | How often the engine runs |
| `MIN_AGE_SECONDS` | 20 | Ignore payments younger than this |
| `ABANDON_AFTER_SECONDS` | 120 | A pending order with no payment at all is marked failed after this |
| `DRY_RUN` | false | Detect and log only |
| `DROP_WEBHOOKS` / `DELAY_WEBHOOK_SECONDS` / `DUPLICATE_WEBHOOKS` | off | Failure injection (also live in the Control room) |
| `DEMO_MODE` | true | Allows the Control room to change flags without an admin key |
| `NGROK_AUTHTOKEN` | (none) | Public tunnel for Razorpay webhooks |

---

## 9. Known limitations (say them before you're asked)

1. If the engine crashes between claiming a fix and calling the portal, that claim isn't retried
   automatically. Fix would be: a sweeper that sends old unfinished claims to manual review.
2. Razorpay allows a second attempt on the same order; our portal treats the first `payment.failed` as
   final. PayFix still catches a later capture (failed + captured → manual review), so no money is lost.
3. The Control room has no login in demo mode.
4. Single machine, no monitoring or alerting: a demo, not production.
