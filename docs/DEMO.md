# PayFix demo: presenter cheat sheet (about 3 minutes)

## Before you present (2 minutes)

```bash
cd C:\PayFix\PayFix
docker compose down -v                            # optional: wipe old demo data for a clean dashboard
docker compose up --build -d                      # start everything
docker compose --profile test run --rm -T e2e     # expect "RESULT: 9/9 checks passed"
docker compose down -v; docker compose up -d      # optional: clean slate again after the check
```

Open three browser tabs:
1. http://localhost:3000/control (Control room)
2. http://localhost:3000/ (Pay fee)
3. http://localhost:3000/dashboard (PayFix dashboard)

---

## The walkthrough

### 1. The problem (Pay fee page, 20s)
> "Last semester a student paid a ₹1,000 exam fee, the hotspot dropped, and the portal said
> *'Payment failed, wait 2–7 days'*. The bank had already taken the money. The portal and the gateway
> disagreed, and nothing was watching. PayFix is the thing that watches."

### 2. Happy path (30s)
* Click **Pay ₹1,000.00 securely** → choose **✅ Pay successfully**.
* Status page goes `PENDING → PAID` within a second.
> "Normal flow: the gateway sends a signed webhook, the portal verifies the signature and marks it paid.
> The browser's success callback is only a *hint*; we never trust the browser."

### 3. Break it: the incident (60s)
* Control room → turn **DROP_WEBHOOKS** ON.
> "Webhooks can be lost, late or duplicated. The sandbox can't fail on command, so we drop them on purpose."
* Pay fee → Pay. **Razorpay mode:** Netbanking → any bank → **Success** (the dropped webhook leaves the portal on PENDING). **MockPay mode:** choose **📶 Pay, then lose connection** (portal shows UNKNOWN).
* Status page: **PORTAL SAYS UNKNOWN ≠ GATEWAY SAYS CAPTURED**.
> "This is exactly the incident. Money is captured, but the portal doesn't know."
* Wait about 20–30 s (or Control room → **⚡ Run reconciliation now**).
* Status flips to **PAID** with the banner *"Fixed automatically by PayFix"*. The audit trail fills in:
  **COLLECT → DETECT → VERIFY → DECIDE → ACT**.
> "PayFix found the mismatch, *asked Razorpay again right before acting* so it never acts on stale
> data, decided using a rule table, fixed it exactly once, and logged every step."

### 4. Dashboard (30s)
* Dashboard: stat tiles (mismatches, auto-resolved, money un-stuck), mismatch table. **Click a row** to see the timeline replayed from the append-only audit log.
> "The audit log is append-only. UPDATE and DELETE are blocked by a database trigger. Any transaction's
> full story can be rebuilt from the log alone."

### 5. Edge cases (optional, 40s)
* **👯 Get charged twice** (with DROP on) → PayFix keeps the first capture and **refunds the extra** (dashboard: *Duplicate refunds = 1*).
* **⏳ Authorized, not captured** → goes to the **Manual review queue**. *"When it's unclear, PayFix never guesses."*
* Control room → **State machine check** → click `→ pending` on a PAID payment → red toast *"Rejected by state machine"*.
  *"Nothing leaves paid or failed. Enforced in code and in the database."*
* Control room → **Fail next 3** gateway calls, then pay with DROP on → the engine retries with exponential backoff (RETRY entries in the feed) and still fixes it.

### 6. Close (15s)
> "Two systems, two databases, one independent referee. Idempotency, webhook verification, a state machine,
> verify-before-act and an append-only audit trail: the same problems Razorpay's own backend teams solve."

---

## Likely questions

| Question | Answer |
|---|---|
| Why not just trust the webhook? | Webhooks can be dropped, delayed or duplicated. Reconciliation is the last line of defence. |
| What if two engine workers fix the same payment? | `UNIQUE (txn_id, action)` + `INSERT … ON CONFLICT DO NOTHING`: only one wins, the other logs SKIP. Covered by a concurrency test. |
| Why wait MIN_AGE before acting? | So PayFix never races the normal webhook for a payment that is still in flight. |
| Is the gateway real? | The demo uses MockPay, which speaks Razorpay's REST API and signs webhooks the same way. Point `RAZORPAY_API_BASE` at api.razorpay.com with test keys and the same code runs on Razorpay Test Mode. |
| Why separate databases? | The engine is an *independent* referee. It must not depend on the portal's internals, only its API. |
| Money as floats? | Never. Integer paise everywhere; floats are rejected by the API. |

## If something goes wrong live
* Page blank or errors → `docker compose ps` (all should be Up) → `docker compose restart`.
* Payment not getting fixed → check Control room: DRY_RUN must be **off**; MIN_AGE is 20 s by default.
* Start over → `docker compose down -v && docker compose up -d`.
