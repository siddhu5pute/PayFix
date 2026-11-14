# ⚠️ TEMPORARY SECTION: copy, then delete this whole section and push again

> This section holds our **test-mode** secrets and the walkthrough page so they can be copied to another laptop.
> The repo is public: delete this section right after copying, and regenerate the Razorpay test key and
> ngrok token after the project. Secrets stay in git history even after deletion.

## A. `.env` file

In the `PayFix` folder run `notepad .env`, click **Yes**, paste everything below, save.

```
GATEWAY_MODE=razorpay
RAZORPAY_API_BASE=https://api.razorpay.com/v1
RAZORPAY_KEY_ID=rzp_test_U00RVIPgPg8KGv
RAZORPAY_KEY_SECRET=5p5AXfb8ONMWK3z4yFeG8ecI
RAZORPAY_WEBHOOK_SECRET=ugj7WURRa3JRCKJvTRcKmQ5LGpvbeN8m
INTERNAL_API_KEY=iZF1p2WcbeHeTYuhpzhjW1pp5G9O45r7
PORTAL_DB_PASSWORD=portal
ENGINE_DB_PASSWORD=engine
DROP_WEBHOOKS=false
DELAY_WEBHOOK_SECONDS=0
DUPLICATE_WEBHOOKS=false
RECON_INTERVAL_SECONDS=10
MIN_AGE_SECONDS=20
ABANDON_AFTER_SECONDS=300
DRY_RUN=false
DEMO_MODE=true
NGROK_AUTHTOKEN=3M5mKyKOujNbPDLwAcQN89WHNmS_57kd5L2WbrxzvyRoSwQAD
```

Then start: `docker compose --profile razorpay up --build -d`

## B. Walkthrough page (`walkthrough.html`)

Copy everything inside the block below into a file named `walkthrough.html` and open it in a browser.
(PowerShell: `notepad walkthrough.html` → Yes → paste → save.)

````html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PayFix Walkthrough</title>
<style>
  :root { --bg:#F3F8FF; --card:#FFFFFF; --line:#D9E6F8; --text:#0F2341; --muted:#5B6F8E; --blue:#2563EB; --soft:#DCE8FF;
          --green:#047857; --gbg:#D1FAE5; --amber:#92400E; --abg:#FEF3C7; --red:#991B1B; --rbg:#FEE2E2; --violet:#5B21B6; --vbg:#EDE9FE; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15.5px/1.6 Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }
  header { background:linear-gradient(135deg,#0B1F3F,#1D4ED8); color:#fff; padding:44px 24px 36px; }
  header .wrap { max-width:1040px; margin:0 auto; }
  header h1 { margin:0 0 6px; font-size:36px; }
  header p { margin:0; color:#C7DBFF; max-width:720px; }
  nav.toc { position:sticky; top:0; z-index:5; background:rgba(255,255,255,.92); backdrop-filter:blur(8px); border-bottom:1px solid var(--line); }
  nav.toc .wrap { max-width:1040px; margin:0 auto; padding:10px 24px; display:flex; gap:6px; flex-wrap:wrap; }
  nav.toc a { font-size:13px; font-weight:600; color:var(--muted); text-decoration:none; padding:5px 11px; border-radius:999px; }
  nav.toc a:hover { background:var(--soft); color:var(--blue); }
  main { max-width:1040px; margin:0 auto; padding:28px 24px 64px; }
  section { margin-bottom:36px; }
  h2 { font-size:24px; margin:0 0 6px; color:#0B1F3F; }
  h2 small { font-size:13px; color:var(--muted); font-weight:600; margin-left:8px; }
  h3 { font-size:17px; margin:18px 0 6px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px 22px; box-shadow:0 8px 24px rgba(37,99,235,.06); margin-top:12px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }
  code, pre { font-family:"JetBrains Mono", Consolas, monospace; font-size:13.5px; }
  pre { background:#0B1F3F; color:#E2ECFF; padding:14px 16px; border-radius:12px; overflow-x:auto; margin:8px 0; }
  code { background:#EEF4FF; padding:1px 6px; border-radius:6px; }
  pre code { background:none; padding:0; }
  .btn { display:inline-block; background:var(--blue); color:#fff; font-weight:700; font-size:13px; padding:2px 10px; border-radius:8px; white-space:nowrap; }
  .tog { display:inline-block; background:#FFF1F2; color:#BE123C; border:1px solid #FECDD3; font-weight:700; font-size:12.5px; padding:1px 8px; border-radius:8px; font-family:"JetBrains Mono", Consolas, monospace; }
  .chip { display:inline-block; font-size:11.5px; font-weight:800; letter-spacing:.05em; padding:2px 10px; border-radius:999px; text-transform:uppercase; }
  .paid { background:var(--gbg); color:var(--green); } .pending { background:var(--abg); color:var(--amber); }
  .failed { background:var(--rbg); color:var(--red); } .unknown { background:var(--vbg); color:var(--violet); }
  .tag { font-size:11px; font-weight:800; padding:2px 8px; border-radius:6px; text-transform:uppercase; letter-spacing:.05em; }
  .both { background:var(--gbg); color:var(--green); } .mock { background:var(--abg); color:var(--amber); } .rzp { background:var(--soft); color:var(--blue); }
  ol.steps { padding-left:22px; margin:8px 0; } ol.steps li { margin:4px 0; }
  .see, .say, .why { border-radius:12px; padding:10px 14px; margin-top:10px; font-size:14.5px; }
  .see { background:#F0F9FF; border-left:4px solid #38BDF8; }
  .say { background:#EFF6FF; border-left:4px solid var(--blue); font-style:italic; }
  .why { background:#F8FAFC; border-left:4px solid #94A3B8; color:#334155; }
  .see b, .say b, .why b { font-style:normal; display:block; font-size:11.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-bottom:2px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:left; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; padding:8px 10px; border-bottom:1px solid var(--line); }
  td { padding:9px 10px; border-bottom:1px solid #EDF3FB; vertical-align:top; }
  .flow { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px; }
  .flow span { background:var(--soft); color:#1E3A8A; font-weight:700; padding:6px 12px; border-radius:10px; font-size:13.5px; }
  .flow i { color:var(--muted); font-style:normal; }
  .warn { background:#FFFBEB; border:1px solid #FDE68A; color:#78350F; border-radius:12px; padding:12px 14px; }
  footer { text-align:center; color:var(--muted); font-size:12.5px; padding:24px; }
</style>
</head>
<body>
<header><div class="wrap">
  <h1>⚡ PayFix Walkthrough</h1>
  <p>Every page, every button and every scenario: what to click, what you'll see, what to say, and what happens underneath.</p>
</div></header>

<nav class="toc"><div class="wrap">
  <a href="#start">Start</a><a href="#modes">Two modes</a><a href="#pages">Pages &amp; buttons</a>
  <a href="#scenarios">Scenarios</a><a href="#script">3-min script</a><a href="#qa">Q&amp;A</a><a href="#trouble">Troubleshooting</a>
</div></nav>

<main>

<section id="start">
  <h2>1. Start the project</h2>
  <div class="card">
    <h3>First time on a laptop</h3>
    <ol class="steps">
      <li>Install <b>Git</b> and <b>Docker Desktop</b>. Open Docker Desktop and wait for <i>Engine running</i>.</li>
      <li>Clone and enter the project:
<pre><code>git clone https://github.com/siddhu5pute/PayFix.git
cd PayFix</code></pre></li>
      <li>Create the <code>.env</code> file (values are in the README's temporary section). In PowerShell: <code>notepad .env</code> → <b>Yes</b> → paste → save.</li>
      <li>Start everything (first build takes a few minutes):
<pre><code>docker compose --profile razorpay up --build -d</code></pre></li>
      <li>Check all services are <b>Up</b>: <code>docker compose --profile razorpay ps</code></li>
    </ol>
    <h3>Addresses</h3>
    <table>
      <tr><th>What</th><th>Address</th></tr>
      <tr><td>Website (on this laptop)</td><td><code>http://localhost:3000</code></td></tr>
      <tr><td>Website (public, anyone)</td><td><code>https://barmaid-self-shakily.ngrok-free.dev</code></td></tr>
      <tr><td>ngrok inspector: every request incl. webhooks</td><td><code>http://localhost:4040</code></td></tr>
      <tr><td>Portal API docs</td><td><code>http://localhost:8000/docs</code></td></tr>
      <tr><td>Engine API docs</td><td><code>http://localhost:8100/docs</code></td></tr>
    </table>
    <h3>Stop / reset</h3>
<pre><code>docker compose --profile razorpay down      # stop, keep data (site goes offline)
docker compose --profile razorpay down -v   # stop and wipe all payments + audit log</code></pre>
    <div class="warn">Only one laptop at a time may run the <code>razorpay</code> profile: the public address and the Razorpay webhook follow whichever laptop is running ngrok.</div>
  </div>
</section>

<section id="modes">
  <h2>2. Two modes</h2>
  <div class="grid">
    <div class="card"><span class="tag rzp">Razorpay mode</span>
      <p>With the <code>.env</code> file. The Pay button opens the <b>real Razorpay Checkout</b> (Test Mode, no real money). Webhooks come from Razorpay through ngrok. This is the default on our laptops.</p>
      <p><b>Test payment:</b> Netbanking → any bank → <span class="btn">Success</span> or <span class="btn">Failure</span> on Razorpay's test bank page.</p></div>
    <div class="card"><span class="tag mock">MockPay mode</span>
      <p>No <code>.env</code> file (rename it to <code>.env.off</code>), then <code>docker compose down -v</code> and <code>docker compose up -d</code>. Works fully offline.</p>
      <p>The Pay button opens a <b>test bank page</b> where you pick the outcome. Extra scenarios: charged twice, authorized-only, flaky gateway.</p></div>
  </div>
  <p style="margin-top:10px">Scenarios below are tagged <span class="tag both">both</span> <span class="tag rzp">razorpay</span> <span class="tag mock">mockpay</span>.</p>
</section>

<section id="pages">
  <h2>3. Pages &amp; every button</h2>

  <div class="card">
    <h3>💳 Pay fee: <code>/</code></h3>
    <table>
      <tr><th>Element</th><th>What it does</th></tr>
      <tr><td>Rotating headline, blue blobs</td><td>Decoration. The headline cycles through the failures PayFix catches.</td></tr>
      <tr><td>Portal says PENDING ≠ Gateway says CAPTURED</td><td>The problem in one picture.</td></tr>
      <tr><td>Form: name, email, purpose, amount</td><td>Amount is typed in rupees and converted to integer <b>paise</b> without floats (shown under the button).</td></tr>
      <tr><td><span class="btn">Pay ₹1,000.00 securely</span></td><td>Calls <code>POST /pay</code>: creates the payment (<span class="chip pending">pending</span>) and a Razorpay order, then opens Checkout.</td></tr>
      <tr><td>Badge "Razorpay Test Mode" / "MockPay sandbox"</td><td>Which gateway is active.</td></tr>
      <tr><td>Live counter strip</td><td>From the engine: money un-stuck, mismatches caught, fixed automatically, audit entries. Counts up live.</td></tr>
      <tr><td>"How it works" strip</td><td>The 3-step story: pay once → something breaks → PayFix fixes it.</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>📄 Status: <code>/status/&lt;txn&gt;</code> (opens after paying)</h3>
    <table>
      <tr><th>Element</th><th>What it shows</th></tr>
      <tr><td>Big status chip</td><td><span class="chip pending">pending</span> <span class="chip unknown">unknown</span> <span class="chip paid">paid</span> <span class="chip failed">failed</span>. Refreshes every 2 s on its own.</td></tr>
      <tr><td>Blue banner "Fixed automatically by PayFix"</td><td>Appears only when PayFix (not the webhook) marked it paid.</td></tr>
      <tr><td>Two systems, two beliefs</td><td>Portal's status vs what Razorpay really says, side by side. Red ≠ when they disagree.</td></tr>
      <tr><td>Portal status history</td><td>Every status change attempt, including <b>rejected</b> ones.</td></tr>
      <tr><td>PayFix at work (6 steps)</td><td>Collect → Detect → Verify → Decide → Act → Log, lighting up from the audit log. First step pulses while PayFix is watching.</td></tr>
      <tr><td>Confetti 🎉</td><td>When the status flips to PAID while you watch.</td></tr>
      <tr><td>Audit trail</td><td>Every PayFix step for this payment, replayed from the append-only log.</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>📋 My payments: <code>/payments</code></h3>
    <p>Every payment as the <b>portal</b> sees it. Click a transaction id to open its status page.</p>
  </div>

  <div class="card">
    <h3>📊 PayFix dashboard: <code>/dashboard</code> (read-only)</h3>
    <table>
      <tr><th>Element</th><th>What it shows</th></tr>
      <tr><td>Engine pill (green dot)</td><td>Loop is running, how often, MIN_AGE, which gateway, DRY RUN tag if on.</td></tr>
      <tr><td>6 stat tiles</td><td>Mismatches detected, auto-resolved, marked paid/failed, duplicate refunds, manual review, money un-stuck.</td></tr>
      <tr><td>Mismatches table</td><td>Every disagreement found, its type (e.g. <code>PORTAL_PENDING_GATEWAY_CAPTURED</code>) and how it was resolved. <b>Click a row</b> → timeline replay on the right.</td></tr>
      <tr><td>Manual review queue</td><td>Cases PayFix refused to guess on.</td></tr>
      <tr><td>Recent runs</td><td>Each reconciliation cycle that found something: seen / mismatches / fixed / manual.</td></tr>
      <tr><td>Live audit feed</td><td>Every step as it happens. Click a row to replay that payment.</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>🎛️ Control room: <code>/control</code> (demo only)</h3>
    <table>
      <tr><th>Section</th><th>Control</th><th>Effect</th></tr>
      <tr><td>1 · Webhook flags</td><td><span class="tog">DROP_WEBHOOKS</span></td><td>Portal acknowledges Razorpay's webhook, then ignores it. Turns red when on.</td></tr>
      <tr><td></td><td><span class="tog">DUPLICATE_WEBHOOKS</span></td><td>Every webhook is processed a second time; dedupe must ignore it.</td></tr>
      <tr><td></td><td><span class="tog">DELAY_WEBHOOK_SECONDS</span></td><td>Process webhooks late (0 / 5 / 15 / 30 / 60 / 120 s).</td></tr>
      <tr><td>2 · Engine</td><td><span class="tog">DRY_RUN</span></td><td>PayFix detects and logs, but never fixes.</td></tr>
      <tr><td></td><td><span class="tog">MIN_AGE_SECONDS</span></td><td>PayFix ignores payments younger than this (default 20 s).</td></tr>
      <tr><td></td><td><span class="btn">⚡ Run reconciliation now</span></td><td>Run one cycle immediately instead of waiting for the 10 s loop.</td></tr>
      <tr><td>3 · Gateway chaos</td><td><span class="btn">Fail next 2 / 3 / 8</span></td><td>MockPay returns errors for the next N calls (MockPay mode only).</td></tr>
      <tr><td>4 · Webhooks received</td><td>table</td><td>Every webhook: event, id, order, outcome (processed / dropped / rejected). Rejected-signature count on top.</td></tr>
      <tr><td>5 · State machine check</td><td><span class="btn">→ pending</span> etc.</td><td>Tries a status change on a recent payment. Illegal ones → red toast "Rejected by state machine".</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>⚡ Pop-ups (every page)</h3>
    <p>Top-right card "PayFix just recovered ₹1,000" whenever PayFix fixes or refunds a payment. Click it to open that payment.</p>
  </div>
</section>

<section id="scenarios">
  <h2>4. Scenarios: what to click</h2>
  <p class="why" style="margin-top:4px"><b>Before each scenario</b> All flags off, DRY_RUN off, MIN_AGE 20 s, unless the scenario says otherwise. After a scenario, switch its flag back off.</p>

  <div class="card">
    <h3>S1 · Normal payment <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Pay fee → <span class="btn">Pay ₹1,000.00 securely</span>.</li>
      <li>Razorpay: Netbanking → any bank → <span class="btn">Success</span>. MockPay: <span class="btn">✅ Pay successfully</span>.</li>
    </ol>
    <div class="see"><b>You'll see</b> Status <span class="chip pending">pending</span> → <span class="chip paid">paid</span> within a few seconds, confetti. Control room → Webhooks: <code>payment.captured</code> and <code>order.paid</code>, "marked paid". PayFix steps stay grey: nothing to fix.</div>
    <div class="say"><b>Say</b> "Razorpay sends a signed webhook; the portal checks the signature before believing it. The browser's success callback is only a hint."</div>
    <div class="why"><b>Underneath</b> <code>POST /pay</code> → Razorpay order → Checkout → <code>/payments/verify</code> (signature checked, status NOT changed) → webhook with valid <code>X-Razorpay-Signature</code> → <span class="chip paid">paid</span>.</div>
  </div>

  <div class="card">
    <h3>S2 · Lost confirmation: the main demo <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Control room → turn <span class="tog">DROP_WEBHOOKS</span> on (red).</li>
      <li>Pay fee → Pay. Razorpay: Netbanking → <span class="btn">Success</span>. MockPay: <span class="btn">📶 Pay, then lose connection</span>.</li>
      <li>Point at the status page: Portal says PENDING (MockPay: UNKNOWN) ≠ Gateway says CAPTURED.</li>
      <li>Wait 20–30 s with hands off (or Control room → <span class="btn">⚡ Run reconciliation now</span>).</li>
    </ol>
    <div class="see"><b>You'll see</b> The 6 steps light up one by one, status flips to <span class="chip paid">paid</span>, confetti, blue "Fixed automatically by PayFix" banner, pop-up "PayFix just recovered ₹1,000". Control room → Webhooks shows them as "dropped by DROP_WEBHOOKS flag".</div>
    <div class="say"><b>Say</b> "The money left the bank but the confirmation was lost: exactly my incident. PayFix found it, asked Razorpay again right before acting, fixed it exactly once, and logged every step."</div>
    <div class="why"><b>Underneath</b> Engine loop: COLLECT (pending &gt; 20 s) → DETECT (Razorpay says captured) → VERIFY (asks both again) → DECIDE (rule: captured ⇒ paid) → ACT (<code>INSERT … ON CONFLICT DO NOTHING</code> on <code>UNIQUE(txn_id, action)</code>, then <code>mark-paid</code> on the portal's internal API) → LOG.</div>
  </div>

  <div class="card">
    <h3>S3 · Payment fails <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Pay. Razorpay: Netbanking → <span class="btn">Failure</span>. MockPay: <span class="btn">❌ Payment fails</span>.</li>
    </ol>
    <div class="see"><b>You'll see</b> <span class="chip failed">failed</span> via the <code>payment.failed</code> webhook.</div>
    <div class="say"><b>Say</b> "A failure is final: nothing leaves failed, so a late or forged 'paid' can never flip it."</div>
    <div class="why"><b>Variant</b> Turn DROP_WEBHOOKS on first: the portal stays pending, and PayFix marks it failed (rule: gateway failed ⇒ failed).</div>
  </div>

  <div class="card">
    <h3>S4 · Late webhook vs PayFix (race safety) <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Control room → <span class="tog">DELAY_WEBHOOK_SECONDS</span> = 60.</li>
      <li>Pay successfully. Wait.</li>
    </ol>
    <div class="see"><b>You'll see</b> PayFix fixes it at ~20–30 s. When the late webhook finally arrives (60 s), the portal answers "already paid" and changes nothing.</div>
    <div class="say"><b>Say</b> "Two fixers, one payment: whoever comes second finds it already done. Every step is idempotent."</div>
    <div class="why"><b>Try also</b> DELAY = 5 s: the webhook wins, and PayFix's VERIFY step sees it's already paid and does nothing ("changed before act").</div>
  </div>

  <div class="card">
    <h3>S5 · Duplicate webhooks <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Control room → <span class="tog">DUPLICATE_WEBHOOKS</span> on. Pay successfully.</li>
    </ol>
    <div class="see"><b>You'll see</b> Status page → Portal status history: exactly <b>one</b> "→ paid". Logs: <code>docker compose logs portal-backend | findstr DUPLICATE</code> shows the second delivery ignored.</div>
    <div class="say"><b>Say</b> "Razorpay may deliver the same event twice. We store each event id once (UNIQUE), so the second copy is ignored."</div>
  </div>

  <div class="card">
    <h3>S6 · Detect-only mode (DRY_RUN) <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Control room → <span class="tog">DRY_RUN</span> on and <span class="tog">DROP_WEBHOOKS</span> on. Pay successfully. Run reconciliation now.</li>
      <li>Then turn DRY_RUN off and run again.</li>
    </ol>
    <div class="see"><b>You'll see</b> First: dashboard shows the mismatch and an <code>ACT would_mark_paid</code> entry tagged "dry run"; the payment stays pending. After DRY_RUN off: fixed.</div>
    <div class="say"><b>Say</b> "A safe way to switch PayFix on for a real portal: watch what it would do before letting it act."</div>
  </div>

  <div class="card">
    <h3>S7 · Illegal status change <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Control room → section 5 → on a <span class="chip paid">paid</span> payment click <span class="btn">→ pending</span> (or <span class="btn">→ failed</span>).</li>
    </ol>
    <div class="see"><b>You'll see</b> Red toast "Rejected by state machine: paid → pending". The status page history shows the attempt marked <b>rejected</b>.</div>
    <div class="say"><b>Say</b> "Nothing leaves paid or failed. Enforced in code and again by a database trigger, so even a raw SQL update is refused."</div>
  </div>

  <div class="card">
    <h3>S8 · Abandoned payment <span class="tag both">both</span></h3>
    <ol class="steps">
      <li>Pay → close the Checkout without paying.</li>
      <li>Wait <code>ABANDON_AFTER_SECONDS</code> (300 s in our .env).</li>
    </ol>
    <div class="see"><b>You'll see</b> PayFix marks it <span class="chip failed">failed</span>: "no payment ever reached the gateway".</div>
    <div class="say"><b>Say</b> "Stuck orders don't sit as pending forever, but PayFix waits long enough that a slow student isn't cut off."</div>
  </div>

  <div class="card">
    <h3>S9 · Forged webhook <span class="tag both">both</span></h3>
    <p>In PowerShell:</p>
<pre><code>curl.exe -X POST http://localhost:3000/webhooks/razorpay -H "Content-Type: application/json" -H "X-Razorpay-Signature: forged" -d "{}"</code></pre>
    <div class="see"><b>You'll see</b> <code>{"status":"rejected","reason":"invalid signature"}</code> (HTTP 400). Control room → "Rejected (bad signature)" count goes up.</div>
    <div class="say"><b>Say</b> "Anyone can POST to a webhook URL. We check an HMAC of the raw body with a secret only Razorpay knows."</div>
  </div>

  <div class="card">
    <h3>S10 · Charged twice <span class="tag mock">mockpay</span></h3>
    <ol class="steps"><li>DROP_WEBHOOKS on → Pay → <span class="btn">👯 Get charged twice</span>.</li></ol>
    <div class="see"><b>You'll see</b> Paid; dashboard "Duplicate refunds 1"; audit shows a REFUND step: first payment kept, second refunded.</div>
    <div class="say"><b>Say</b> "The second half of my incident: paying twice. Refunded automatically, exactly once."</div>
  </div>

  <div class="card">
    <h3>S11 · Unclear gateway state <span class="tag mock">mockpay</span></h3>
    <ol class="steps"><li>Pay → <span class="btn">⏳ Authorized, not captured</span>. Wait ~30 s.</li></ol>
    <div class="see"><b>You'll see</b> Dashboard → Manual review queue gets the payment; status stays pending.</div>
    <div class="say"><b>Say</b> "When the gateway's answer isn't final, PayFix never guesses. A human decides."</div>
  </div>

  <div class="card">
    <h3>S12 · Flaky gateway <span class="tag mock">mockpay</span></h3>
    <ol class="steps"><li>Control room → <span class="btn">Fail next 3</span> → DROP on → pay (Pay, then lose connection) → Run reconciliation now.</li></ol>
    <div class="see"><b>You'll see</b> Audit feed: <code>RETRY gateway_transient_error</code> entries, then the fix. With <span class="btn">Fail next 8</span>: manual review instead.</div>
    <div class="say"><b>Say</b> "Temporary errors are retried with exponential backoff; if they don't clear, a human takes over."</div>
  </div>
</section>

<section id="script">
  <h2>5. The 3-minute demo script</h2>
  <div class="card">
    <div class="flow"><span>Incident story</span><i>→</i><span>S1 normal</span><i>→</i><span>DROP on</span><i>→</i><span>S2 lost confirmation</span><i>→</i><span>Dashboard replay</span><i>→</i><span>S7 illegal move</span></div>
    <ol class="steps">
      <li><b>20 s:</b> "Last semester my hotspot dropped mid-payment. The portal said <i>Payment failed, wait 2–7 days</i>. The bank had already taken ₹1,000."</li>
      <li><b>30 s:</b> S1. Show a normal payment turning paid.</li>
      <li><b>60 s:</b> Control room → DROP_WEBHOOKS on → S2. Point at Portal ≠ Gateway, wait for the steps, confetti and pop-up.</li>
      <li><b>30 s:</b> Dashboard → click the mismatch → timeline: "append-only, rebuilt from the log alone".</li>
      <li><b>20 s:</b> S7. Illegal move rejected.</li>
      <li><b>10 s:</b> "An independent referee: verifies before acting, acts once, keeps a permanent log."</li>
    </ol>
    <div class="why"><b>Before presenting</b> <code>docker compose --profile razorpay down -v</code> then <code>up -d</code> for a clean dashboard. Turn off laptop sleep. Open 3 tabs: Pay, Control room, Dashboard.</div>
  </div>
</section>

<section id="qa">
  <h2>6. Questions you'll get</h2>
  <div class="card"><table>
    <tr><th>Question</th><th>Answer</th></tr>
    <tr><td>Isn't the failure staged?</td><td>The failure is simulated because a sandbox can't fail on command. The detection and the fix are real code against the real Razorpay API.</td></tr>
    <tr><td>Why not just trust the webhook?</td><td>Webhooks can be lost, late or duplicated. Reconciliation is the last line of defence.</td></tr>
    <tr><td>What if two engines fix the same payment?</td><td><code>UNIQUE(txn_id, action)</code> + <code>INSERT … ON CONFLICT DO NOTHING</code>: one wins, the other logs SKIP. Tested with 5 racing workers and 100 payments × 4 workers.</td></tr>
    <tr><td>Why wait 20 s (MIN_AGE)?</td><td>So PayFix never races a webhook that is only slightly slow.</td></tr>
    <tr><td>Why check Razorpay twice?</td><td>The VERIFY step: state can change between detecting and acting. Never act on stale data.</td></tr>
    <tr><td>Why two databases?</td><td>An independent referee must not depend on the portal's internals, only its API.</td></tr>
    <tr><td>How is the log tamper-proof?</td><td>A Postgres trigger rejects UPDATE, DELETE and TRUNCATE on <code>audit_log</code>.</td></tr>
    <tr><td>Why paise, not rupees?</td><td>Floats can't represent money exactly (0.1 + 0.2 ≠ 0.3). Integers can.</td></tr>
    <tr><td>Known limitations?</td><td>Crash between claiming and acting isn't auto-recovered; Razorpay retries on the same order after a failure go to manual review; demo control room has no login; single machine.</td></tr>
  </table></div>
</section>

<section id="trouble">
  <h2>7. Troubleshooting</h2>
  <div class="card"><table>
    <tr><th>Problem</th><th>Fix</th></tr>
    <tr><td>Site doesn't open</td><td><code>docker compose --profile razorpay ps</code>: all Up? If not: <code>docker compose --profile razorpay up -d</code>.</td></tr>
    <tr><td>Public URL shows ngrok error</td><td>ngrok running on another laptop, or not started. <code>docker compose logs ngrok</code>.</td></tr>
    <tr><td>Payment never turns paid (DROP off)</td><td>Check http://localhost:4040 for the webhook. 400 = webhook secret in Razorpay ≠ <code>.env</code>. Nothing arrived = webhook URL wrong in Razorpay.</td></tr>
    <tr><td>Stays "authorized"</td><td>Razorpay → Account &amp; Settings → Payment Capture → Automatic.</td></tr>
    <tr><td>PayFix never fixes anything</td><td>DRY_RUN must be off; wait MIN_AGE + 10 s; dashboard engine pill must show a green dot.</td></tr>
    <tr><td>Old styles after an update</td><td>Ctrl + F5.</td></tr>
    <tr><td>Start completely fresh</td><td><code>docker compose --profile razorpay down -v</code> then <code>docker compose --profile razorpay up --build -d</code>.</td></tr>
  </table></div>
</section>

</main>
<footer>PayFix · Razorpay Test Mode only, no real money moves</footer>
</body>
</html>
````

<!-- END OF TEMPORARY SECTION: delete everything above this line -->

---

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
