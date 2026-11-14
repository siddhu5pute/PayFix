import { NavLink, Route, Routes } from 'react-router-dom'
import PayPage from './pages/PayPage.jsx'
import StatusPage from './pages/StatusPage.jsx'
import PaymentsPage from './pages/PaymentsPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ControlRoom from './pages/ControlRoom.jsx'
import FixToasts from './components/FixToasts.jsx'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">⚡</span>
          <div>
            <div className="brand-name">CampusPay</div>
            <div className="brand-sub"><span className="live-dot" /> Exam Fee Portal · watched live by PayFix</div>
          </div>
        </div>
        <nav>
          <NavLink to="/" end>Pay fee</NavLink>
          <NavLink to="/payments">My payments</NavLink>
          <NavLink to="/dashboard">PayFix dashboard</NavLink>
          <NavLink to="/control">Demo control room</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<PayPage />} />
          <Route path="/status/:txnId" element={<StatusPage />} />
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/control" element={<ControlRoom />} />
        </Routes>
      </main>
      <FixToasts />
      <footer className="footer">
        PayFix · payment reconciliation & auto-resolution · Razorpay test mode only, no real money moves
      </footer>
    </div>
  )
}
