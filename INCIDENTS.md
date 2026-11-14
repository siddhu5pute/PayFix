# Incidents log

Real surprises we hit while building and testing PayFix: what happened, why, and what we changed.
We only log things that actually happened to us, not hypothetical risks. Known limitations we chose
not to fix are listed separately at the end.

---

## INC-001: `docker compose run` for the test suite hung with no output

**What happened.** We started the proof-test container with `docker compose --profile test run --rm tests`
from a non-interactive shell. The image built, but no test container ever appeared, and the command sat
there for over ten minutes.

**Why.** `compose run` allocates a pseudo-terminal by default. Without a real terminal attached, it waited
on the TTY instead of starting the container.

**Fix.** Always pass `-T` (no TTY) for scripted runs:
`docker compose --profile test run --rm -T tests`. The README and demo guide use this form everywhere.

---

## INC-002: Test run failed before any test ran: `duplicate key … pg_database_datname_index`

**What happened.** The first full test run stopped at conftest import with
`UniqueViolation: Key (datname)=(portal_test) already exists`, even though the code drops the database
right before creating it.

**Why (most likely).** A leftover run from INC-001 was still talking to Postgres, so two processes did
`DROP DATABASE IF EXISTS` → `CREATE DATABASE` at the same moment, and the second `CREATE` lost the race.
Separately, test modules imported helpers with `from conftest import …`, which risks loading the conftest
module (and its database setup) a second time.

**Fix.** The test-database setup now retries the drop/create a few times with a short back-off, and
the shared helpers moved to `tests/helpers.py` so `conftest.py` is only loaded by pytest itself.
Result: 63/63 tests pass.

---

## INC-003: End-to-end demo check reported a failure that wasn't a bug

**What happened.** The live demo script failed the check "dropped webhook → PayFix marks paid".
The audit log showed the full COLLECT → DETECT → VERIFY → DECIDE → ACT sequence, so PayFix *had* fixed it.

**Why.** The script set `MIN_AGE_SECONDS=0` at the start so it wouldn't have to wait. The engine's own
background loop (every 10 s) then picked up the payment and fixed it during the script's 2-second pause,
before the script could observe the "stuck" state. The script then saw `paid` where it expected `unknown`.

**Fix.** The script now holds the loop off (`MIN_AGE_SECONDS=600`) while it creates and observes the stuck
payment, then drops MIN_AGE to 0 and triggers a run. It also restores the original settings at the end.
Result: 9/9 live checks pass.

**What it taught us.** This is the exact race that `MIN_AGE_SECONDS` exists to prevent in production:
the reconciler and the normal confirmation path must not compete for a fresh payment.

---

## Razorpay sandbox

_To be filled in during real Razorpay Test Mode testing._ Template:

```
## INC-0xx: <short title>
**What happened.**
**Why.**
**Fix.**
```

---

## Known limitations (accepted, not fixed)

| Limitation | Effect | Why we accepted it |
|---|---|---|
| Engine crash between claiming a fix and calling the portal | That payment's claim stays in `claimed` state and is not retried automatically. | Out of scope for a single-node demo. The fix would be a sweeper that moves claims older than N minutes to manual review. |
| `payment.failed` webhook marks the portal payment `failed` immediately | Razorpay allows a second attempt on the same order. If that attempt succeeds, the portal can't move `failed → paid`. | PayFix still catches it: portal `failed` + gateway `captured` goes to manual review, so the money is never silently lost. |
| Demo control room has no login | Anyone with access to the demo URL can flip failure flags. | Only enabled with `DEMO_MODE=true`. Production would set an `ADMIN_KEY`. |
| MockPay state lives in a JSON file | Restarting with `down -v` wipes gateway history. | It's a test gateway; real Razorpay keeps its own state. |
