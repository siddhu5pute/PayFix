import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { engine, gateway, portal, shortId, timeOf } from '../api.js'
import { StatusChip, Toast, usePoll } from '../components/ui.jsx'

function Switch({ on, onChange, label, sub }) {
  return (
    <div className="switch-row">
      <div><b>{label}</b><div className="muted small">{sub}</div></div>
      <button className={`switch ${on ? 'on' : ''}`} onClick={() => onChange(!on)} aria-pressed={on}><span /></button>
    </div>
  )
}

export default function ControlRoom() {
  const [flags, , setFlags] = usePoll(portal.flags, 4000)
  const [cfg, , setCfg] = usePoll(engine.config, 4000)
  const [hooks] = usePoll(portal.webhooks, 2000)
  const [payments] = usePoll(() => portal.list(15), 3000)
  const [toast, setToast] = useState(null)
  const [running, setRunning] = useState(false)
  const close = useCallback(() => setToast(null), [])

  const upd = async body => {
    try { setFlags(await portal.setFlags(body)); setToast({ msg: 'Portal failure flags updated', kind: 'info' }) }
    catch (e) { setToast({ msg: e.message, kind: 'error' }) }
  }
  const updEngine = async body => {
    try { setCfg(await engine.setConfig(body)); setToast({ msg: 'Engine config updated', kind: 'info' }) }
    catch (e) { setToast({ msg: e.message, kind: 'error' }) }
  }
  const runNow = async () => {
    setRunning(true)
    try {
      const r = await engine.run()
      setToast({ msg: `Run #${r.run_id}: saw ${r.collected}, mismatches ${r.mismatches}, fixed ${r.resolved}, manual ${r.manual}`, kind: 'ok' })
    } catch (e) { setToast({ msg: e.message, kind: 'error' }) }
    setRunning(false)
  }
  const force = async (txn, to) => {
    try {
      const r = await portal.forceTransition(txn, to)
      setToast({ msg: `Accepted: ${r.from_status} → ${r.to_status}`, kind: 'ok' })
    } catch (e) {
      if (e.status === 409) setToast({ msg: `Rejected by state machine: ${e.data.from_status} → ${e.data.to_status} (logged)`, kind: 'error' })
      else setToast({ msg: e.message, kind: 'error' })
    }
  }

  return (
    <div className="control">
      <div className="dash-head">
        <div>
          <div className="eyebrow">Demo only</div>
          <h1 className="serif">Control room</h1>
          <p className="muted">The sandbox can't fail on command, so we break things on purpose here.</p>
        </div>
      </div>

      <div className="control-grid">
        <section className="card">
          <h3>1 · Portal webhook failure flags</h3>
          {flags && (
            <>
              <Switch on={flags.drop_webhooks} onChange={v => upd({ drop_webhooks: v })}
                label="DROP_WEBHOOKS" sub="Receive the signed webhook, acknowledge it, then ignore it." />
              <Switch on={flags.duplicate_webhooks} onChange={v => upd({ duplicate_webhooks: v })}
                label="DUPLICATE_WEBHOOKS" sub="Re-deliver every webhook once more. Dedupe on event id must hold." />
              <div className="switch-row">
                <div><b>DELAY_WEBHOOK_SECONDS</b><div className="muted small">Process webhooks late (0 = off).</div></div>
                <select value={flags.delay_webhook_seconds} onChange={e => upd({ delay_webhook_seconds: Number(e.target.value) })}>
                  {[0, 5, 15, 30, 60, 120].map(s => <option key={s} value={s}>{s}s</option>)}
                </select>
              </div>
            </>
          )}
        </section>

        <section className="card">
          <h3>2 · Reconciliation engine</h3>
          {cfg && (
            <>
              <Switch on={cfg.dry_run} onChange={v => updEngine({ dry_run: v })}
                label="DRY_RUN" sub="Detect and log only. Never act." />
              <div className="switch-row">
                <div><b>MIN_AGE_SECONDS</b><div className="muted small">Ignore payments younger than this, so we never race the normal webhook.</div></div>
                <select value={cfg.min_age_seconds} onChange={e => updEngine({ min_age_seconds: Number(e.target.value) })}>
                  {[0, 10, 20, 30, 60, 120].map(s => <option key={s} value={s}>{s}s</option>)}
                </select>
              </div>
              <div className="muted small">Loop runs every {cfg.recon_interval_seconds}s. Gateway: {cfg.gateway}.</div>
              <button className="btn-primary" onClick={runNow} disabled={running}>{running ? 'Running…' : '⚡ Run reconciliation now'}</button>
            </>
          )}
        </section>

        <section className="card">
          <h3>3 · Gateway chaos (MockPay)</h3>
          <p className="muted small">Make the gateway API return HTTP 503 for the next N calls. PayFix retries with exponential backoff; if errors persist, the payment goes to manual review.</p>
          <div className="row gap">
            {[2, 3, 8].map(n => (
              <button key={n} className="btn-ghost" onClick={async () => {
                try { await gateway.flaky(n); setToast({ msg: `MockPay will fail the next ${n} API calls`, kind: 'info' }) }
                catch (e) { setToast({ msg: 'Only available with MockPay: ' + e.message, kind: 'error' }) }
              }}>Fail next {n}</button>
            ))}
          </div>
        </section>

        <section className="card span2">
          <h3>4 · Webhooks received by the portal</h3>
          <div className="muted small">Rejected (bad signature): <b>{hooks?.rejected_signature_count ?? 0}</b></div>
          <div className="table-wrap">
            <table className="tight">
              <thead><tr><th>Time</th><th>Event</th><th>Event id</th><th>Order</th><th>Outcome</th></tr></thead>
              <tbody>
                {(hooks?.events || []).map(h => (
                  <tr key={h.event_id}>
                    <td className="muted small">{timeOf(h.received_at)}</td>
                    <td>{h.event_type}</td>
                    <td className="mono small">{h.event_id.slice(0, 18)}</td>
                    <td className="mono small">{h.order_id}</td>
                    <td className={h.processed ? 'small' : 'small warn'}>{h.outcome || 'pending'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <h3>5 · State machine check</h3>
          <p className="muted small">Try an illegal move (e.g. paid → pending). The portal rejects it and logs the attempt; the DB trigger is the backstop.</p>
          <ul className="list">
            {(payments || []).slice(0, 6).map(p => (
              <li key={p.txn_id}>
                <div className="row between">
                  <Link className="mono" to={`/status/${p.txn_id}`}>{shortId(p.txn_id)}</Link>
                  <StatusChip status={p.status} />
                </div>
                <div className="row gap wrap">
                  {['pending', 'paid', 'failed', 'created'].filter(s => s !== p.status).map(s => (
                    <button key={s} className="btn-mini" onClick={() => force(p.txn_id, s)}>→ {s}</button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card span3 guide">
          <h3>Demo script (≈2 minutes)</h3>
          <ol>
            <li>Turn <b>DROP_WEBHOOKS</b> on (section 1).</li>
            <li>Go to <Link to="/">Pay fee</Link> → Pay → choose <b>“Pay, then lose connection”</b>. The status page shows <StatusChip status="unknown" /> while the gateway says <b>CAPTURED</b>.</li>
            <li>Wait ~{cfg ? cfg.min_age_seconds + cfg.recon_interval_seconds : 30}s (or hit <b>Run reconciliation now</b>). PayFix collects → detects → verifies → decides → acts once → logs. Status flips to <StatusChip status="paid" />.</li>
            <li>Open the <Link to="/dashboard">dashboard</Link> and click the mismatch to replay its timeline from the audit log.</li>
            <li>Bonus: “Get charged twice” → PayFix keeps the first capture and refunds the extra. “Authorized, not captured” → manual review (never guess).</li>
          </ol>
        </section>
      </div>
      <Toast msg={toast?.msg} kind={toast?.kind} onClose={close} />
    </div>
  )
}
