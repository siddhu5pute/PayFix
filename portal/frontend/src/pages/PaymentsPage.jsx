import { Link } from 'react-router-dom'
import { portal, rupees, shortId } from '../api.js'
import { StatusChip, usePoll } from '../components/ui.jsx'

export default function PaymentsPage() {
  const [rows, err] = usePoll(() => portal.list(100), 2500)
  return (
    <section className="card">
      <div className="card-head">
        <h2>Payments (portal view)</h2>
        <span className="muted small">auto-refreshing</span>
      </div>
      {err && <div className="error">{err.message}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Txn</th><th>Payer</th><th>Purpose</th><th className="num">Amount</th><th>Status</th><th>Note</th><th>Created</th></tr>
          </thead>
          <tbody>
            {(rows || []).map(r => (
              <tr key={r.txn_id}>
                <td><Link className="mono" to={`/status/${r.txn_id}`}>{shortId(r.txn_id)}</Link></td>
                <td>{r.payer_name}</td>
                <td>{r.purpose}</td>
                <td className="num">{rupees(r.amount_paise)}</td>
                <td><StatusChip status={r.status} /></td>
                <td className="muted small clip">{r.status_note}</td>
                <td className="muted small">{new Date(r.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
            {rows && rows.length === 0 && <tr><td colSpan={7} className="muted">No payments yet. <Link to="/">Make one</Link>.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  )
}
