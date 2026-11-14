# PayFix setup guide

From a fresh laptop to a running demo, then to Razorpay Test Mode, then to a public website.
Every step is a copy-paste command. Windows commands are shown; macOS/Linux are identical unless noted.

---

## 0. What you need installed

| Tool | Why | Get it |
|---|---|---|
| **Git** | clone the repo | https://git-scm.com/downloads |
| **Docker Desktop** | runs everything (databases included) | https://www.docker.com/products/docker-desktop/ |

That's all. No Python, Node or Postgres on your machine: each runs inside its own container.
Start Docker Desktop and wait until it says **Engine running**.

---

## 1. Offline demo (no keys, about 5 minutes)

```bash
git clone https://github.com/siddhu5pute/PayFix.git
cd PayFix
docker compose up --build -d
```

Open **http://localhost:3000**. With no `.env` file, payments go through **MockPay**, a built-in test
gateway that speaks Razorpay's API, so the full demo works offline.

Check that everything works (expect `RESULT: 9/9 checks passed`):
```bash
docker compose --profile test run --rm -T e2e
```

Wipe the test data it created, for a clean dashboard:
```bash
docker compose down -v
docker compose up -d
```

### Where the databases live
Both Postgres databases (portal and engine) run as Docker containers. Their data sits in Docker volumes
(`payfix_portal-db-data`, `payfix_engine-db-data`), so it survives `docker compose down` and restarts.
`docker compose down -v` deletes the volumes, which gives you a clean slate.

| Database | Inspect with |
|---|---|
| Portal | `docker compose exec portal-db psql -U portal -d portal` |
| Engine | `docker compose exec engine-db psql -U engine -d engine` |

Useful queries: `SELECT txn_id, status FROM payments;` (portal),
`SELECT step, action, reason FROM audit_log ORDER BY id;` (engine).

---

## 2. Real Razorpay Test Mode

### 2.1 Get the keys (one time)
1. Sign up at https://dashboard.razorpay.com/signup and switch the top toggle to **Test Mode**.
2. **Account & Settings → API Keys → Generate Test Key**. Copy the **Key ID** (`rzp_test_…`) and **Key Secret**.
3. **Account & Settings → Payment Capture**: make sure it is **Automatic**.
4. Make up a **webhook secret**: any long random string.

### 2.2 Get ngrok (one time)
Razorpay must reach your laptop to deliver webhooks. ngrok gives your laptop a public HTTPS address.
1. Sign up at https://dashboard.ngrok.com/signup.
2. Copy **Your Authtoken** from the dashboard.
3. Nothing to install: ngrok runs as a container in our stack.

### 2.3 Create `.env`
In the `PayFix` folder, copy `.env.example` to `.env` and fill in:

```
GATEWAY_MODE=razorpay
RAZORPAY_API_BASE=https://api.razorpay.com/v1
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...your webhook secret...
INTERNAL_API_KEY=...any long random string...
NGROK_AUTHTOKEN=...
```

`.env` is in `.gitignore`. **Never commit it, and never use `rzp_live_` keys.**

### 2.4 Start in Razorpay mode
```bash
docker compose down -v                        # old MockPay orders don't exist in Razorpay
docker compose --profile razorpay up --build -d
```

Find your public address at **http://localhost:4040** (ngrok's inspector page). It looks like
`https://something.ngrok-free.dev`. Free ngrok accounts get one fixed address, so it stays the same
across restarts.

### 2.5 Register the webhook (one time per address)
Razorpay Dashboard (Test Mode) → **Account & Settings → Webhooks → Add New Webhook**:

| Field | Value |
|---|---|
| Webhook URL | `https://<your-ngrok-address>/webhooks/razorpay` |
| Secret | the same webhook secret as in `.env` |
| Active events | `payment.captured`, `payment.failed`, `order.paid` |

### 2.6 Test it
Open **http://localhost:3000** → **Pay**. The real Razorpay Checkout opens. Easiest test method:
**Netbanking → any bank → click Success** on Razorpay's test bank page. The status page should turn
**PAID** within seconds via the real webhook.

To see webhooks arriving: http://localhost:4040 (every request through the tunnel) or the
Control room's "Webhooks received" table.

---

## 3. Making the website live

### Option A: your laptop + ngrok (free, ready now)
With step 2 done, the whole website is already public at your ngrok address:
`https://<your-ngrok-address>/`. Pages, APIs and Razorpay webhooks all go through that one address.

* It is live only while your laptop is on and Docker is running.
* Visitors see a one-time ngrok warning page first; they click **Visit Site**.
* Good for: showing the project to anyone, anywhere, on demo day.

### Option B: a cloud VM (always on)
Same `docker compose`, on a small Linux server instead of your laptop.

1. Get a VM: Ubuntu 22.04+, 2 GB RAM or more. Free/credit options for students:
   **Azure for Students** (free credit, no card), **GitHub Student Developer Pack** (DigitalOcean credit),
   **Oracle Cloud Always Free**.
2. Open ports **22** and **80** (and **443** for HTTPS) in the VM's firewall/network settings.
3. SSH in and run:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER && newgrp docker
   git clone https://github.com/siddhu5pute/PayFix.git && cd PayFix
   nano .env        # same values as section 2.3; NGROK_AUTHTOKEN is optional here
   docker compose up --build -d
   ```
4. The site is now on port 3000 of the VM. To serve it on normal port 80, change `"3000:80"`
   to `"80:80"` under `frontend:` in `docker-compose.yml`, then `docker compose up -d`.
5. HTTPS (Razorpay webhooks need HTTPS). Easiest: keep the ngrok service (`--profile razorpay`) on the
   VM too, so the ngrok address works exactly like Option A. With a domain, put Caddy in front of port 80
   instead; it gets certificates automatically.
6. In Razorpay, update the webhook URL to the VM's HTTPS address.

### Why not Vercel?
Vercel hosts static sites and short serverless functions. PayFix needs two Postgres databases and an
engine that runs **continuously** in the background. Vercel can host only the React frontend
(`portal/frontend`, with `VITE_PORTAL_API`, `VITE_ENGINE_API`, `VITE_GATEWAY_API` pointing at backends
hosted elsewhere), so you would still need Option B for everything else. One VM is simpler.

### Before making it public
* The Control room can flip failure flags and engine settings while `DEMO_MODE=true`. Fine for a demo,
  but anyone with the URL can use it. For a long-running public site set `DEMO_MODE=false` and an `ADMIN_KEY`.
* Test keys only. After the project, regenerate the Razorpay test key and the ngrok token.

---

## 4. Everyday commands

| Task | Command |
|---|---|
| Start (offline / MockPay) | `docker compose up -d` |
| Start (Razorpay + public URL) | `docker compose --profile razorpay up -d` |
| Stop (keep data) | `docker compose down` |
| Stop and wipe data | `docker compose down -v` |
| Status of services | `docker compose ps` |
| Engine's live audit lines | `docker compose logs -f engine` |
| Pre-demo check (MockPay mode) | `docker compose --profile test run --rm -T e2e` |
| All proof tests (63) | `docker compose --profile test run --rm -T tests` |
| Rebuild after pulling changes | `git pull && docker compose up --build -d` |

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` / cannot connect | Start Docker Desktop and wait for "Engine running". |
| Port 3000/8000/5434 already in use | Stop the other program, or change the left number in `ports:` in `docker-compose.yml`. |
| Payments never become PAID in Razorpay mode | Check the webhook URL and secret in Razorpay match `.env`; look at http://localhost:4040 for 400 responses (400 = wrong secret). |
| Payments stay "authorized" | Razorpay → Payment Capture must be Automatic. Until then PayFix sends them to manual review, by design. |
| PayFix never fixes anything | Control room: DRY_RUN must be off. Payments are only checked once older than MIN_AGE (20 s). |
| Lots of manual-review items after switching modes | Old MockPay orders were left in the DB. `docker compose down -v`, then start again. |
| ngrok container exits | Check `NGROK_AUTHTOKEN` in `.env`; `docker compose logs ngrok`. |
