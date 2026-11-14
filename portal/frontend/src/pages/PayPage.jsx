import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { loadRazorpayCheckout, portal, rupees } from '../api.js'
import MockCheckout from '../components/MockCheckout.jsx'

const PURPOSES = ['Review exam fee', 'Semester exam fee', 'Supplementary exam fee', 'Transcript fee', 'Hostel fee']

// Parse a rupee string into integer paise without floating point ("1000.5" -> 100050)
function toPaise(str) {
  const m = String(str).trim().match(/^(\d{1,7})(?:\.(\d{0,2}))?$/)
  if (!m) return null
  return parseInt(m[1], 10) * 100 + parseInt((m[2] || '').padEnd(2, '0') || '0', 10)
}

export default function PayPage() {
  const nav = useNavigate()
  const [form, setForm] = useState({
    payer_name: 'Sample Student', payer_email: 'student@example.com', purpose: PURPOSES[0], amount: '1000.00',
  })
  const [cfg, setCfg] = useState(null)
  const [order, setOrder] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => { portal.config().then(setCfg).catch(() => {}) }, [])

  const paise = toPaise(form.amount)
  const set = k => e => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    if (!paise || paise < 100) return setErr('Enter an amount of at least ₹1.00 (max two decimals).')
    setBusy(true)
    try {
      const o = await portal.pay({
        payer_name: form.payer_name, payer_email: form.payer_email, purpose: form.purpose, amount_paise: paise,
      })
      if (o.gateway_mode === 'razorpay') await openRazorpay(o)
      else setOrder(o)
    } catch (e2) {
      setErr(e2.message)
    } finally {
      setBusy(false)
    }
  }

  async function openRazorpay(o) {
    const Razorpay = await loadRazorpayCheckout()
    const rzp = new Razorpay({
      key: o.key_id, order_id: o.razorpay_order_id, amount: o.amount_paise, currency: o.currency,
      name: o.name, description: o.description, prefill: o.prefill, theme: { color: '#0f3d31' },
      handler: async resp => {
        try { await portal.verify({ txn_id: o.txn_id, ...resp }) } catch { /* hint only */ }
        nav(`/status/${o.txn_id}`)
      },
      modal: { ondismiss: () => nav(`/status/${o.txn_id}`) },
    })
    rzp.on('payment.failed', () => {
      portal.clientEvent(o.txn_id, { type: 'checkout_failed' }).catch(() => {})
    })
    rzp.open()
  }

  return (
    <div className="pay-layout">
      <section className="hero">
        <div className="eyebrow">Exam Fee Portal</div>
        <h1>Pay your fee.<br /><span className="mint">Never wait 2–7 days again.</span></h1>
        <p className="lead">
          If the connection drops mid-payment, you don't have to guess or pay twice. PayFix, an independent
          referee, checks every pending payment against the gateway, fixes it safely and exactly once,
          and logs every step.
        </p>
        <div className="hero-cards">
          <div className="mini-card"><div className="mini-k">Portal says</div><div className="mini-v amber">PENDING</div></div>
          <div className="neq">≠</div>
          <div className="mini-card mint-border"><div className="mini-k">Gateway says</div><div className="mini-v mint">CAPTURED {rupees(paise || 0)}</div></div>
        </div>
        <div className="hero-note">PayFix detects it, verifies it, then fixes it.</div>
      </section>

      <section className="card pay-card">
        <div className="card-head">
          <h2>Fee payment</h2>
          {cfg && (
            <span className={`mode-badge ${cfg.gateway_mode}`}>
              {cfg.gateway_mode === 'razorpay' ? 'Razorpay Test Mode' : 'MockPay sandbox'}
            </span>
          )}
        </div>
        <form onSubmit={submit} className="form">
          <label>Student name<input value={form.payer_name} onChange={set('payer_name')} required minLength={2} /></label>
          <label>Email<input type="email" value={form.payer_email} onChange={set('payer_email')} required /></label>
          <label>Purpose
            <select value={form.purpose} onChange={set('purpose')}>
              {PURPOSES.map(p => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label>Amount (₹)
            <div className="amount-input"><span>₹</span><input value={form.amount} onChange={set('amount')} inputMode="decimal" /></div>
          </label>
          {err && <div className="error">{err}</div>}
          <button className="btn-primary" disabled={busy}>
            {busy ? 'Creating order…' : `Pay ${paise ? rupees(paise) : ''} securely`}
          </button>
          <p className="fine">Stored as integer paise ({paise ?? '—'}). Test mode only, no real money moves.</p>
        </form>
      </section>

      {order && (
        <MockCheckout order={order} onClose={() => { setOrder(null); nav(`/status/${order.txn_id}`) }}
          onDone={txn => { setOrder(null); nav(`/status/${txn}`) }} />
      )}
    </div>
  )
}
