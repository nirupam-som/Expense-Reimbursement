import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'

/**
 * Shell around every signed-in page: navigation, the stale-alert badge and who you are.
 *
 * The badge count is re-fetched on every navigation, since approving or dismissing
 * something elsewhere in the app changes it.
 */
export default function Layout() {
  const { user, signOut, isApprover } = useAuth()
  const location = useLocation()
  const [alertCount, setAlertCount] = useState(0)

  useEffect(() => {
    api
      .getStaleAlerts()
      .then((response) => setAlertCount(response.count))
      .catch(() => setAlertCount(0))
  }, [location.pathname])

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__inner">
          <div className="topbar__brand">
            <span className="topbar__mark">ER</span>
            <span>Expense Reimbursement</span>
          </div>

          <nav className="topbar__nav">
            <NavLink to="/" end>
              Dashboard
            </NavLink>
            <NavLink to="/reports">Reports</NavLink>
            {isApprover && <NavLink to="/queue">Approval queue</NavLink>}
            <NavLink to="/alerts" className="topbar__alerts">
              Alerts
              {alertCount > 0 && <span className="badge-count">{alertCount}</span>}
            </NavLink>
          </nav>

          <div className="topbar__user">
            <div className="topbar__identity">
              <strong>{user.full_name}</strong>
              <span className="muted">{isApprover ? 'Approver' : 'Employee'}</span>
            </div>
            <button type="button" className="button button--ghost" onClick={signOut}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
