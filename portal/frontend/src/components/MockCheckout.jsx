import { useState } from 'react'
import { gateway, portal, rupees } from '../api.js'

const OPTIONS = [
  { key: 'success', icon: '✅', title: 'Pay successfully', sub: 'Normal flow: payment captured, webhook confirms it.' },
  { key: 'drop', icon: '📶', title: 'Pay, then lose connection', sub: 'Money is captured, but the browser never hears back. The incident.' },
  { key: 'fail', icon: '❌', title: 'Payment fails', sub: 'Bank declines. Gateway sends payment.failed.' },
  { key: 'twice', icon: '👯', title: 'Get charged twice', sub: 'Two captures on one order. PayFix refunds the extra one.' },
  { key: 'authorized', icon: '⏳', title: 'Authorized, not captured', sub: 'Ambiguous state. PayFix refuses to guess.' },
]

export default function MockCheckout({ order, onDone, onClose }) {
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  async function choose(key) {
    setBusy(key)
    setErr(null)
    const { razorpay_order_id: oid, txn_id } = order
    const email = order.prefill?.email
    try {
      if (key === 'success' || key === 'twice') {
        const r = await gateway.pay(oid, 'success', email)
        if (key === 'twice') await gateway.pay(oid, 'success', email)
        await portal.verify({ txn_id, ...r })
      } else if (key === 'drop') {
        await gateway.pay(oid, 'success', email) // captured at the gateway...
        await new Promise(res => setTimeout(res, 600)) // ...but the response never reaches the portal
        await portal.clientEvent(txn_id, { type: 'checkout_interrupted', detail: 'network dropped mid-checkout' })
      } else if (key === 'fail') {
        await gateway.pay(oid, 'fail', email)
        await portal.clientEvent(txn_id, { type: 'checkout_failed', detail: 'bank declined (test)' })
      } else if (key === 'authorized') {
        await gateway.pay(oid, 'authorized', email)
      }
      onDone(txn_id)
    } catch (e) {
      setErr(e.message)
      setBusy(null)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal checkout">
        <div className="checkout-head">
          <div>
            <div className="checkout-merchant">{order.name}</div>
            <div className="checkout-desc">{order.description}</div>
          </div>
          <div className="checkout-amount">{rupees(order.amount_paise)}</div>
        </div>
        <div className="checkout-banner">
          MockPay test checkout · Razorpay-compatible sandbox · <b>no real money</b>
        </div>
        <div className="checkout-body">
          <div className="checkout-label">Choose what happens to this test payment</div>
          {OPTIONS.map(o => (
            <button key={o.key} className="checkout-opt" disabled={!!busy} onClick={() => choose(o.key)}>
              <span className="co-icon">{o.icon}</span>
              <span className="co-text">
                <b>{o.title}</b>
                <small>{o.sub}</small>
              </span>
              {busy === o.key && <span className="spinner" />}
            </button>
          ))}
          {err && <div className="error">{err}</div>}
        </div>
        <div className="checkout-foot">
          <span className="mono">{order.razorpay_order_id}</span>
          <button className="link" onClick={onClose} disabled={!!busy}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
