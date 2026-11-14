import { useState } from 'react'
import { Link } from 'react-router-dom'
import { engine, rupees, shortId, timeOf } from '../api.js'
import { AuditTimeline, StatusChip, usePoll } from '../components/ui.jsx'

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone || ''}`}>
      <div className="stat-v">{value ?? '—'}</div>
      <div className="stat-k">{label}</div>
    </div>
  )
}

export default function DashboardPage() {
  const [stats] = usePoll(engine.stats, 2500)
  const [cfg] = usePoll(engine.config, 4000)
  const [mm] = usePoll(engine.mismatches, 2500)
  const [manual] = usePoll(engine.manual, 3000)
  const [runs] = usePoll(engine.runs, 4000)
  const [feed] = usePoll(() => engine.audit(40), 2500)
  const [sel, setSel] = useState(null)
  const [replay] = usePoll(async () => (sel ? engine.replay(sel) : null), 3000, [sel])

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <div className="eyebrow">Read-only · Reconciliation engine</div>
          <h1 className="serif">PayFix dashboard</h1>
        </div>
        {cfg && (
          <div className="engine-pill">
            <span className={`dot ${cfg.worker_running ? 'on' : ''}`} />
            loop every {cfg.recon_interval_seconds}s · MIN_AGE {cfg.min_age_seconds}s · {cfg.gateway}
            {cfg.dry_run && <span className="tag tag-amber">DRY RUN</span>}
          </div>
        )}
      </div>

      <div className="stats">
        <Stat label="Mismatches detected" value={stats?.mismatches_total} />
        <Stat label="Auto-resolved" value={stats?.auto_resolved} tone="mint" />
        <Stat label="Marked paid / failed" value={stats ? `${stats.marked_paid} / ${stats.marked_failed}` : null} />
        <Stat label="Duplicate refunds" value={stats?.refunds} />
        <Stat label="Manual review" value={stats?.manual_review_open} tone={stats?.manual_review_open ? 'amber' : ''} />
        <Stat label="Money un-stuck" value={stats ? rupees(stats.amount_recovered_paise) : null} tone="mint" />
      </div>

      <div className="dash-grid">
        <section className="card span2">
          <h3>Mismatches and how each was resolved</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Txn</th><th>Type</th><th>Portal</th><th>Gateway</th><th className="num">Amount</th><th>Detected</th><th>Resolution</th></tr></thead>
              <tbody>
                {(mm || []).map(m => (
                  <tr key={m.id} className={sel === m.txn_id ? 'selected' : ''} onClick={() => setSel(m.txn_id)}>
                    <td className="mono">{shortId(m.txn_id)}</td>
                    <td><span className="type">{m.mismatch_type}</span></td>
                    <td><StatusChip status={m.portal_status} /></td>
                    <td><span className="gw">{m.gateway_status}</span></td>
                    <td className="num">{m.amount_paise ? rupees(m.amount_paise) : '—'}</td>
                    <td className="muted small">{timeOf(m.detected_at)}</td>
                    <td>{m.resolved ? <span className="ok">✓ {m.resolution}</span> : <span className="warn">{m.resolution || 'open'}</span>}</td>
                  </tr>
                ))}
                {mm && mm.length === 0 && <tr><td colSpan={7} className="muted">No mismatches yet. Turn on DROP_WEBHOOKS in the <Link to="/control">control room</Link> and make a payment.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <h3>Transaction timeline {sel && <span className="mono small muted">{shortId(sel)}</span>}</h3>
          {!sel && <p className="muted">Click a mismatch to replay its full history from the audit log.</p>}
          {sel && replay && (
            <>
              <div className="replay-sum">
                <span>start <StatusChip status={replay.initial_status} /></span>
                <span>final <StatusChip status={replay.final_status} /></span>
                <span>actions <b>{replay.actions_taken}</b></span>
                {replay.refunds > 0 && <span>refunds <b>{replay.refunds}</b></span>}
              </div>
              <AuditTimeline events={replay.events} />
              <Link className="small" to={`/status/${sel}`}>Open student status page →</Link>
            </>
          )}
        </section>

        <section className="card">
          <h3>Manual review queue</h3>
          {(manual || []).length === 0 && <p className="muted">Empty. Nothing needed a human.</p>}
          <ul className="list">
            {(manual || []).map(m => (
              <li key={m.id} onClick={() => setSel(m.txn_id)}>
                <div className="row between"><span className="mono">{shortId(m.txn_id)}</span><span className="tag tag-amber">{m.status}</span></div>
                <div className="small">{m.reason}</div>
                <div className="muted small">portal {m.portal_status} · gateway {m.gateway_status}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <h3>Recent reconciliation runs</h3>
          <div className="table-wrap">
            <table className="tight">
              <thead><tr><th>#</th><th>When</th><th className="num">Seen</th><th className="num">Mismatch</th><th className="num">Fixed</th><th className="num">Manual</th></tr></thead>
              <tbody>
                {(runs || []).map(r => (
                  <tr key={r.id}>
                    <td>{r.id}{r.dry_run && <span className="tag tag-amber">dry</span>}</td>
                    <td className="muted small">{timeOf(r.started_at)} · {r.trigger}</td>
                    <td className="num">{r.collected}</td><td className="num">{r.mismatches}</td>
                    <td className="num">{r.resolved}</td><td className="num">{r.manual}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card span3">
          <h3>Live audit feed <span className="muted small">(append-only: UPDATE/DELETE blocked by a DB trigger)</span></h3>
          <div className="feed">
            {(feed || []).map(e => (
              <div key={e.id} className="feed-row" onClick={() => e.txn_id && setSel(e.txn_id)}>
                <span className="muted small">{timeOf(e.created_at)}</span>
                <span className={`tl-step s-${e.step}`}>{e.step}</span>
                <span className="mono small">{shortId(e.txn_id)}</span>
                <span className="small clip">{e.action}{e.reason ? ' · ' + e.reason : ''}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
