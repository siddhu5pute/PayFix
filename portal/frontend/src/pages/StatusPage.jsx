import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { engine, gateway, portal, rupees } from '../api.js'
import { AuditTimeline, Confetti, PipelineTracker, PortalHistory, StatusChip, usePoll } from '../components/ui.jsx'

const EXPLAIN = {
  created: 'Order is being created with the gateway.',
  pending: 'Waiting for the gateway to confirm. If the confirmation gets lost, PayFix will check the gateway directly and fix it. You do not need to pay again.',
  unknown: 'The connection dropped, so the portal does not know the outcome. Do NOT pay again: PayFix is verifying with the gateway.',
  paid: 'Payment confirmed. Your fee is recorded.',
  failed: 'The payment did not go through. No money was captured for this order.',
  refunded: 'This payment was refunded.',
}

export default function StatusPage() {
  const { txnId } = useParams()
  const [p, perr] = usePoll(() => portal.get(txnId), 2000, [txnId])
  const [g] = usePoll(async () => (p?.razorpay_order_id ? gateway.order(p.razorpay_order_id) : null), 2500,
    [p?.razorpay_order_id])
  const [replay] = usePoll(() => engine.replay(txnId), 3000, [txnId])
  const prevStatus = useRef(null)
  const [celebrate, setCelebrate] = useState(0)
  useEffect(() => {
    const s = p?.status
    if (s === 'paid' && prevStatus.current && prevStatus.current !== 'paid') setCelebrate(Date.now())
    if (s) prevStatus.current = s
  }, [p?.status])

  if (perr && !p) return <div className="card"><h2>Payment not found</h2><p className="muted">{perr.message}</p></div>
  if (!p) return <div className="card"><div className="spinner" /> Loading…</div>

  const capturedAtGateway = g?.payments?.filter(x => x.status === 'captured' || x.status === 'refunded') || []
  const gwStatus = g ? (g.payments.length === 0 ? 'no payment' : g.payments.map(x => x.status).join(' + ')) : '—'
  const disagree = g && ['pending', 'unknown'].includes(p.status) && capturedAtGateway.length > 0
  const fixedByPayFix = (replay?.events || []).some(e => e.step === 'ACT' && !e.dry_run)

  return (
    <div className="status-layout">
      <Confetti fire={celebrate} />
      <section className="card status-card">
        <div className="status-top">
          <div>
            <div className="muted small">Transaction</div>
            <div className="mono big">{p.txn_id}</div>
          </div>
          <StatusChip status={p.status} large />
        </div>
        <div className="status-amount">{rupees(p.amount_paise)} <span className="muted">· {p.purpose}</span></div>
        <p className="explain">{EXPLAIN[p.status]}</p>
        {fixedByPayFix && p.status === 'paid' && (
          <div className="banner banner-mint">⚡ Fixed automatically by PayFix: the gateway confirmation was lost, PayFix verified the money was captured and marked it paid.</div>
        )}
        <dl className="kv">
          <dt>Payer</dt><dd>{p.payer_name} · {p.payer_email}</dd>
          <dt>Gateway order</dt><dd className="mono">{p.razorpay_order_id || '—'}</dd>
          <dt>Payment id</dt><dd className="mono">{p.razorpay_payment_id || '—'}</dd>
          <dt>Last update</dt><dd>{new Date(p.updated_at).toLocaleString()}</dd>
        </dl>
        <div className="row gap">
          <Link className="btn-ghost" to="/">New payment</Link>
          <Link className="btn-ghost" to="/dashboard">Open PayFix dashboard</Link>
        </div>
      </section>

      <section className="card">
        <h3>Two systems, two beliefs</h3>
        <div className="versus">
          <div className={`side ${disagree ? 'side-amber' : ''}`}>
            <div className="muted small">PORTAL SAYS</div>
            <div className="side-v">{p.status.toUpperCase()}</div>
          </div>
          <div className={`neq ${disagree ? '' : 'eq'}`}>{disagree ? '≠' : '='}</div>
          <div className="side side-mint">
            <div className="muted small">GATEWAY SAYS</div>
            <div className="side-v">{gwStatus.toUpperCase()}</div>
          </div>
        </div>
        {disagree && <p className="muted small">Mismatch! PayFix will pick this up once it is older than MIN_AGE (so it never races the normal webhook).</p>}
        <h3>Portal status history</h3>
        <PortalHistory history={p.history} />
      </section>

      <section className="card span2">
        <h3>PayFix at work on this payment</h3>
        <PipelineTracker events={replay?.events} status={p.status} />
      </section>

      <section className="card span2">
        <h3>PayFix audit trail for this transaction <span className="muted small">(replayed from the append-only log)</span></h3>
        <AuditTimeline events={replay?.events} />
      </section>
    </div>
  )
}
