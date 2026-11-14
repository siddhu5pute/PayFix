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
