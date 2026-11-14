// API bases. In Docker, nginx proxies these paths. On Vercel, set VITE_*_API to public backend URLs.
export const PORTAL = import.meta.env.VITE_PORTAL_API || '/api/portal'
export const ENGINE = import.meta.env.VITE_ENGINE_API || '/api/engine'
export const GATEWAY = import.meta.env.VITE_GATEWAY_API || '/api/gateway'

async function req(base, path, opts = {}) {
  const res = await fetch(base + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const msg = (data && (data.detail?.[0]?.msg || data.detail || data.error?.description)) || res.statusText
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const portal = {
  config: () => req(PORTAL, '/config/public'),
  pay: body => req(PORTAL, '/pay', { method: 'POST', body }),
  verify: body => req(PORTAL, '/payments/verify', { method: 'POST', body }),
  clientEvent: (txn, body) => req(PORTAL, `/payments/${txn}/client-event`, { method: 'POST', body }),
  get: txn => req(PORTAL, `/payments/${txn}`),
  list: (limit = 50) => req(PORTAL, `/payments?limit=${limit}`),
  flags: () => req(PORTAL, '/admin/flags'),
  setFlags: body => req(PORTAL, '/admin/flags', { method: 'PUT', body }),
  webhooks: () => req(PORTAL, '/webhooks/recent'),
  forceTransition: (txn, to_status) =>
    req(PORTAL, `/admin/payments/${txn}/force-transition`, { method: 'POST', body: { to_status } }),
}

export const engine = {
  config: () => req(ENGINE, '/api/config'),
  setConfig: body => req(ENGINE, '/api/config', { method: 'PUT', body }),
  run: () => req(ENGINE, '/api/recon/run', { method: 'POST' }),
  stats: () => req(ENGINE, '/api/stats'),
  mismatches: () => req(ENGINE, '/api/mismatches'),
  manual: () => req(ENGINE, '/api/manual-review'),
  runs: () => req(ENGINE, '/api/runs'),
  audit: (limit = 60) => req(ENGINE, `/api/audit?limit=${limit}`),
  replay: txn => req(ENGINE, `/api/transactions/${txn}/replay`),
}

export const gateway = {
  pay: (orderId, outcome, email) =>
    req(GATEWAY, `/checkout/${orderId}/pay`, { method: 'POST', body: { outcome, email } }),
  order: orderId => req(ENGINE, `/api/gateway/orders/${orderId}`),
  flaky: n => req(GATEWAY, '/admin/flaky', { method: 'POST', body: { fail_next_n: n } }),
  info: () => req(GATEWAY, '/admin/info'),
}

export const rupees = paise =>
  '₹' + (Number(paise) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const shortId = id => (id ? String(id).slice(0, 8) + '…' : '—')

export const timeOf = iso => (iso ? new Date(iso).toLocaleTimeString() : '')

export function loadRazorpayCheckout() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve(window.Razorpay)
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = () => resolve(window.Razorpay)
    s.onerror = () => reject(new Error('Could not load Razorpay Checkout'))
    document.body.appendChild(s)
  })
}
