# PayFix demo: Razorpay walkthrough

## Before you present

Make sure Docker Desktop is running and your `.env` is configured for **Razorpay Test Mode**.

```bash
cd C:\PayFix\PayFix
docker compose down -v
docker compose --profile razorpay up --build -d
```

Open these browser tabs:

1. http://localhost:3000/control — Control Room
2. http://localhost:3000/ — Pay fee portal
3. http://localhost:3000/dashboard — PayFix dashboard
4. http://localhost:4040 — ngrok request inspector

Confirm in Razorpay Dashboard → Test Mode that:

- API keys are test keys beginning with `rzp_test_`
- Payment Capture is set to **Automatic**
- the webhook URL is `https://<ngrok-address>/webhooks/razorpay`
- the webhook secret matches `RAZORPAY_WEBHOOK_SECRET` in `.env`
- webhook events include `payment.captured`, `payment.failed`, and `order.paid`

At the beginning of the demo, reset the Control Room:

- `DROP_WEBHOOKS`: OFF
- `DUPLICATE_WEBHOOKS`: OFF
- `DELAY_WEBHOOK_SECONDS`: 0
- `DRY_RUN`: OFF
- `MIN_AGE_SECONDS`: 20

---

## Main walkthrough

### 1. Explain the problem

> “A student pays an exam fee, but the portal and the payment gateway can disagree because a webhook is dropped, delayed or duplicated. The bank or Razorpay has already captured the payment, while the portal still says pending or unknown.”

PayFix watches this mismatch independently, asks Razorpay again before acting, and updates the portal only when the reconciliation rules allow it.

### 2. Show the normal successful payment

1. Open http://localhost:3000/.
2. Enter a student name and email, keep the purpose, and enter ₹1000.
3. Click **Pay ₹1,000.00 securely**.
4. Complete the payment in Razorpay Checkout using a supported Test Mode method.
5. For the simplest demo, choose **Netbanking → any bank → Success**.

Show:

- the Razorpay Checkout success flow
- the portal status changing from `PENDING` to `PAID`
- the Control Room webhook table showing the received Razorpay events
- ngrok at http://localhost:4040 showing the webhook requests

> “The browser callback is only a hint. The portal is updated by the signed Razorpay webhook, and the webhook signature is verified before processing.”

### 3. Demonstrate a dropped webhook

This is the main PayFix reconciliation case.

1. In the Control Room, turn **DROP_WEBHOOKS** ON.
2. Reduce wait time if needed: set **MIN_AGE_SECONDS** to 10.
3. Return to the payment page and make another ₹1000 payment.
4. Complete it successfully in Razorpay Test Mode.
5. Open the status page and show that the portal cannot receive the normal webhook update.

The portal intentionally receives and acknowledges the webhook but ignores it when this flag is enabled. Razorpay still reports that the payment was captured.

Wait until `MIN_AGE_SECONDS +` the reconciliation interval has passed, or click **Run reconciliation now** in the Control Room.

Show:

- `PORTAL PENDING/UNKNOWN`
- `RAZORPAY CAPTURED`
- the status changing to `PAID`
- the banner: **Fixed automatically by PayFix**
- audit stages: `COLLECT → DETECT → VERIFY → DECIDE → ACT`

> “PayFix found the mismatch, asked Razorpay for the latest status right before acting, decided using its reconciliation rule table, applied the action exactly once, and added every step to the audit trail.”

Turn **DROP_WEBHOOKS** OFF after this scenario.

### 4. Demonstrate a delayed webhook

1. Set **DELAY_WEBHOOK_SECONDS** to 15.
2. Make another successful Razorpay payment.
3. Immediately open the status page and show the temporary mismatch or pending state.
4. After the delay, show Razorpay’s webhook arrive and the portal update.

This demonstrates that reconciliation must not race the normal, legitimate webhook path.

Reset **DELAY_WEBHOOK_SECONDS** to 0.

### 5. Demonstrate a duplicate webhook

1. Turn **DUPLICATE_WEBHOOKS** ON.
2. Make another successful Razorpay payment.
3. Inspect the webhook table and payment/audit history.

Razorpay delivery may cause two copies of the event to reach the portal. The portal must deduplicate them using the webhook event ID, so the payment is not processed twice.

Turn **DUPLICATE_WEBHOOKS** OFF after this scenario.

### 6. Show the dashboard and audit replay

Open http://localhost:3000/dashboard.

Show:

- mismatch count
- automatically resolved count
- money recovered or un-stuck
- the mismatch table
- the audit timeline for a resolved payment

Explain that the audit log is append-only and `UPDATE`, `DELETE` and `TRUNCATE` are blocked at the database level.

### 7. Test a failed payment

Complete another Razorpay Checkout payment using a failure option available in Razorpay Test Mode.

Check:

- the portal does not mark the payment as PAID
- the status and reason are recorded correctly
- reconciliation does not treat a failed payment as captured

Do not describe this as an internet-disconnection test. It is a Razorpay payment failure test.

### 8. Test a signature failure

Send a webhook with an incorrect signature in a controlled test environment, or compare one in ngrok:

- the portal should reject it
- `Rejected (bad signature)` should increase in the Control Room
- the payment status should not change because of the rejected event

### 9. Test repeat reconciliation and idempotency

After a payment has been fixed automatically:

1. Click **Run reconciliation now** again.
2. Show that it is not resolved a second time.
3. Inspect the audit log and payment status.

> “The system uses a unique transaction/action constraint so multiple reconciliation runs or engine workers cannot perform the same resolution twice.”

### 10. Test the state machine

In the Control Room → **State machine check**:

1. Select a PAID payment.
2. Click **→ pending** or another invalid transition.
3. Show the red toast: **Rejected by state machine**.

Explain that state transitions are enforced both in application code and by database triggers.

---

## Optional edge cases

These are useful for checking behavior, but should be run only if the Razorpay test setup makes the scenario reliable:

- **Dry run:** turn `DRY_RUN` ON, run reconciliation, and confirm mismatches are detected and logged but no state-changing action is taken. Turn it OFF before continuing.
- **Authorized, not captured:** only test if Payment Capture is deliberately changed from automatic to manual. The payment should go to manual review rather than being guessed as paid.
- **Unauthorized transition:** try an illegal portal status move in the State machine section.
- **Webhook with wrong secret:** verify that the portal rejects the event and records a signature failure.
- **Repeat engine run:** verify idempotency and `SKIP`/duplicate protection.

Do not include MockPay-only controls such as gateway 503 injection or the MockPay checkout in the Razorpay walkthrough.

---

## Likely questions

| Question | Answer |
|---|---|
| Why not just trust the webhook? | Razorpay webhooks can be dropped, delayed or duplicated. Reconciliation is an independent last line of defence. |
| What if Razorpay and the portal disagree? | PayFix compares both sides, verifies Razorpay again immediately before acting, and follows the rule table. |
| What if reconciliation runs twice? | `UNIQUE (txn_id, action)` and conflict handling ensure the action is applied only once. |
| Why wait MIN_AGE? | It prevents PayFix from racing a normal webhook while a payment is still in flight. |
| Is this real Razorpay? | It uses a Razorpay Test Mode account. No live or real-money payments are used. |
| Why separate databases? | The engine is an independent referee. It reads the portal through an internal API and never trusts only the portal database. |
| Can the browser callback mark a payment paid? | No. The browser callback is only a hint; gateway status and signed webhook verification are used. |
| Why integer paise? | Money is stored as integer paise everywhere; float currency values are rejected. |

## If something goes wrong

- **Page is blank:** run `docker compose ps` and confirm all required services are running.
- **Payment does not become paid:** confirm the webhook URL and secret in Razorpay match `.env`, check ngrok, and inspect http://localhost:4040 for 400 responses.
- **Payment is not reconciled:** confirm `DRY_RUN` is OFF and wait beyond `MIN_AGE_SECONDS +` the reconciliation interval, or click **Run reconciliation now**.
- **ngrok has no public address:** confirm `NGROK_AUTHTOKEN` is set and inspect `docker compose logs ngrok`.
- **Start over:** `docker compose down -v && docker compose --profile razorpay up --build -d`.
