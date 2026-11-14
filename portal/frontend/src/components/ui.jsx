import { useEffect, useRef, useState } from 'react'
import { timeOf } from '../api.js'

export function StatusChip({ status, large }) {
  const s = (status || 'unknown').toLowerCase()
  return <span className={`chip chip-${s} ${large ? 'chip-lg' : ''}`}>{s.replace('_', ' ')}</span>
}

export function usePoll(fn, ms = 2000, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const fnRef = useRef(fn)
  fnRef.current = fn
  useEffect(() => {
    let alive = true
    let timer
    const tick = async () => {
      try {
        const d = await fnRef.current()
        if (alive) { setData(d); setError(null) }
      } catch (e) {
        if (alive) setError(e)
      }
      if (alive) timer = setTimeout(tick, ms)
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return [data, error, setData]
}

const STEP_CLASS = {
  COLLECT: 'st-collect', DETECT: 'st-detect', VERIFY: 'st-verify', DECIDE: 'st-decide', ACT: 'st-act',
  REFUND: 'st-act', SKIP: 'st-skip', MANUAL_REVIEW: 'st-manual', ERROR: 'st-error', RETRY: 'st-error',
}

export function AuditTimeline({ events }) {
  if (!events || events.length === 0) return <p className="muted">No audit entries yet.</p>
  return (
    <ol className="timeline">
      {events.map(e => (
        <li key={e.id} className={STEP_CLASS[e.step] || ''}>
          <div className="tl-head">
            <span className="tl-step">{e.step}</span>
            <span className="tl-action">{e.action}</span>
            {e.dry_run && <span className="tag">dry run</span>}
            {e.from_status && e.to_status && (
              <span className="tl-move"><StatusChip status={e.from_status} /> → <StatusChip status={e.to_status} /></span>
            )}
            <span className="tl-time">{timeOf(e.created_at)}</span>
          </div>
          {e.reason && <div className="tl-reason">{e.reason}</div>}
        </li>
      ))}
    </ol>
  )
}

export function PortalHistory({ history }) {
  if (!history?.length) return null
  return (
    <ol className="timeline compact">
      {history.map((h, i) => (
        <li key={i} className={h.accepted ? '' : 'st-error'}>
          <div className="tl-head">
            <span className="tl-step">{h.source}</span>
            {h.from_status !== h.to_status ? (
              <span className="tl-move">
                {h.from_status ? <StatusChip status={h.from_status} /> : null} → <StatusChip status={h.to_status} />
              </span>
            ) : <span className="tl-action">note</span>}
            {!h.accepted && <span className="tag tag-red">rejected</span>}
            <span className="tl-time">{timeOf(h.created_at)}</span>
          </div>
          <div className="tl-reason">{h.reason}</div>
        </li>
      ))}
    </ol>
  )
}

export function Toast({ msg, kind = 'info', onClose }) {
  useEffect(() => {
    if (!msg) return
    const t = setTimeout(onClose, 4500)
    return () => clearTimeout(t)
  }, [msg, onClose])
  if (!msg) return null
  return <div className={`toast toast-${kind}`} onClick={onClose}>{msg}</div>
}

// Smoothly animates a number from its previous value to the new one.
export function useCountUp(target, ms = 900) {
  const [val, setVal] = useState(0)
  const fromRef = useRef(0)
  useEffect(() => {
    const to = Number(target) || 0
    const from = fromRef.current
    if (from === to) return
    let raf
    const start = performance.now()
    const step = now => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 3)
      setVal(Math.round(from + (to - from) * eased))
      if (t < 1) raf = requestAnimationFrame(step)
      else fromRef.current = to
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return val
}

export function CountUp({ value, format = v => v.toLocaleString('en-IN') }) {
  const v = useCountUp(value)
  if (value === null || value === undefined) return '—'
  return format(v)
}

const CONFETTI_COLORS = ['#2563EB', '#38BDF8', '#10B981', '#F59E0B', '#7C5CFF', '#F472B6']

export function Confetti({ fire }) {
  const [pieces, setPieces] = useState([])
  useEffect(() => {
    if (!fire) return
    setPieces(Array.from({ length: 90 }, (_, i) => ({
      id: `${fire}-${i}`,
      left: Math.random() * 100,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      dur: 2.2 + Math.random() * 1.8,
      delay: Math.random() * 0.5,
      rot: Math.random() * 360,
    })))
    const t = setTimeout(() => setPieces([]), 4800)
    return () => clearTimeout(t)
  }, [fire])
  if (!pieces.length) return null
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map(p => (
        <i key={p.id} style={{ left: `${p.left}%`, background: p.color, animationDuration: `${p.dur}s`,
          animationDelay: `${p.delay}s`, transform: `rotate(${p.rot}deg)` }} />
      ))}
    </div>
  )
}

const PIPE = [
  ['COLLECT', '📥', 'Collect'], ['DETECT', '🔍', 'Detect'], ['VERIFY', '✅', 'Verify'],
  ['DECIDE', '⚖️', 'Decide'], ['ACT', '🛠️', 'Act'], ['LOG', '📜', 'Log'],
]

// Lights up PayFix's six steps as they appear in this payment's audit trail.
export function PipelineTracker({ events, status }) {
  const seen = new Set((events || []).filter(e => !e.dry_run || e.step !== 'ACT').map(e => e.step))
  if (seen.has('REFUND')) seen.add('ACT')
  if ((events || []).length) seen.add('LOG')
  const watching = !seen.size && ['pending', 'unknown'].includes(status)
  let note
  if (seen.has('ACT')) note = 'PayFix verified the money with the gateway and fixed this payment, exactly once.'
  else if (seen.has('DETECT')) note = 'PayFix found a mismatch and is working on it…'
  else if (watching) note = 'PayFix is watching this payment. If the confirmation gets lost, it steps in.'
  else note = 'Portal and gateway agree. Nothing for PayFix to fix.'
  return (
    <div>
      <div className={`tracker ${watching ? 'watching' : ''}`}>
        {PIPE.map(([key, icon, label]) => (
          <div key={key} className={`tstep ${seen.has(key) ? 'on' : ''} ${key === 'ACT' ? 'act' : ''}`}>
            <div className="tdot">{icon}</div>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <p className="tracker-note">{watching && <span className="live-dot" />}{note}</p>
    </div>
  )
}
