# Contributions

Ownership follows the team split from our progress review. Each row lists only what exists in this
repository and how it is verified. Nothing is listed here that isn't built.

| Member | Area | Owns | Verified by |
|---|---|---|---|
| **Siddharth** | Reconciliation engine | `engine/`: worker loop (collect → detect → verify → decide → act → log), gateway client interface with Razorpay and fake implementations, rule table, exactly-once resolution (`UNIQUE (txn_id, action)`), append-only audit log and replay, retries with exponential backoff, manual review queue, duplicate-capture refunds, DRY_RUN | `tests/test_idempotency.py`, `test_audit.py`, `test_resilience.py`, `test_rules.py`, `test_load.py` |
| **Arpit** | Portal backend | `portal/backend/`: order creation, Checkout signature check (hint only), webhook receiver with raw-body signature verification and event-id dedupe, failure flags (DROP / DELAY / DUPLICATE), internal API for the engine, payment state machine in code and as a DB trigger | `tests/test_webhooks.py`, `test_state_machine.py` |
| **Shubhant** | Frontend, docs | `portal/frontend/`: CampusPay pay form, test checkout, status page with portal-vs-gateway view; `README.md`, `docs/DEMO.md` | Live demo check `tests/e2e_demo.py` (9/9) |
| **Saurav** | Frontend, docs | `portal/frontend/`: PayFix dashboard (stats, mismatches, manual review, audit timeline replay), demo control room; walkthrough deck, `INCIDENTS.md` | Live demo check `tests/e2e_demo.py` (9/9) |

## Shared work (whole team)

| Item | Where |
|---|---|
| Shared contract: statuses, allowed transitions, integer-paise money rule | `shared/contract.py` |
| MockPay: Razorpay-compatible test gateway for offline demos | `mockpay/` |
| One-command stack: two Postgres databases and five services | `docker-compose.yml` |
| Proof-test runner with saved logs | `tests/run_all.sh`, `tests/logs/` |

## Use of AI tools

We used an AI coding assistant during development for exploring alternatives, implementation support,
testing and debugging. The problem, design and scope are the team's; each member reviewed and tested
their part.

## Not done yet

- End-to-end run against real Razorpay Test Mode (needs our test keys and an ngrok tunnel).
- GitHub Actions CI workflow.
- `docs/architecture.md` and `docs/api-contract.md` (the README covers architecture and the rule table for now).

_Update this file whenever a piece of work is finished, and only then._
