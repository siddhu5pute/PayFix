import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { engine, rupees } from '../api.js'

// Site-wide pop-ups whenever PayFix fixes or refunds a payment.
export default function FixToasts() {
  const [toasts, setToasts] = useState([])
  const lastId = useRef(null)
  const nav = useNavigate()

  useEffect(() => {
    let alive = true
    let timer
    const tick = async () => {
      try {
        const feed = await engine.audit(25)
        const maxId = feed.reduce((m, e) => Math.max(m, e.id), 0)
        if (lastId.current === null) {
          lastId.current = maxId // don't replay history on first load
        } else {
          const fresh = feed
            .filter(e => e.id > lastId.current && !e.dry_run && (e.step === 'ACT' || e.step === 'REFUND'))
            .reverse()
          lastId.current = Math.max(lastId.current, maxId)
          if (fresh.length && alive) {
            const mismatches = await engine.mismatches().catch(() => [])
            const amountOf = txn => mismatches.find(m => m.txn_id === txn)?.amount_paise
            const items = fresh.map(e => {
              const amt = amountOf(e.txn_id)
              const refund = e.step === 'REFUND'
              return {
                key: e.id, txn: e.txn_id, refund,
                title: refund ? 'PayFix refunded a duplicate charge'
                  : e.to_status === 'paid' ? `PayFix just recovered ${amt ? rupees(amt) : 'a payment'}`
                  : `PayFix closed a stuck payment as ${e.to_status}`,
                sub: refund ? 'Kept the first payment, refunded the extra one' : `${e.from_status} → ${e.to_status}, verified with the gateway`,
              }
            })
            setToasts(t => [...items, ...t].slice(0, 4))
            items.forEach(it => setTimeout(() => setToasts(t => t.filter(x => x.key !== it.key)), 7000))
          }
        }
      } catch { /* engine not reachable: stay quiet */ }
      if (alive) timer = setTimeout(tick, 3000)
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [])

  if (!toasts.length) return null
  return (
    <div className="fix-toasts">
      {toasts.map(t => (
        <div key={t.key} className={`fix-toast ${t.refund ? 'refund' : ''}`} onClick={() => nav(`/status/${t.txn}`)}>
          <div className="ft-ic">⚡</div>
          <div><b>{t.title}</b><small>{t.sub}</small></div>
        </div>
      ))}
    </div>
  )
}
