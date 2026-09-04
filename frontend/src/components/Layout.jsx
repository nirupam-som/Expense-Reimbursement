import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  FileText,
  CheckSquare,
  Bell,
  LogOut,
  Receipt,
  UserCheck,
  Building2,
} from 'lucide-react'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'

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
            <div className="topbar__mark">
              <Receipt size={18} />
            </div>
            <span>ExpenseFlow</span>
          </div>

          <nav className="topbar__nav">
            <NavLink to="/" end>
              <LayoutDashboard size={16} />
              Dashboard
            </NavLink>
            <NavLink to="/reports">
              <FileText size={16} />
              Reports
            </NavLink>
            {isApprover && (
              <NavLink to="/queue">
                <CheckSquare size={16} />
                Approval Queue
              </NavLink>
            )}
            <NavLink to="/alerts" className="topbar__alerts">
              <Bell size={16} />
              Alerts
              {alertCount > 0 && <span className="badge-count">{alertCount}</span>}
            </NavLink>
          </nav>

          <div className="topbar__user">
            <div className="topbar__identity">
              <strong>{user.full_name}</strong>
              <span className="muted">
                {isApprover ? (
                  <span className="role-tag role-tag--approver">
                    <UserCheck size={12} /> Approver
                  </span>
                ) : (
                  <span className="role-tag">
                    <Building2 size={12} /> Employee
                  </span>
                )}
              </span>
            </div>
            <button type="button" className="button button--ghost button--small" onClick={signOut} title="Sign out">
              <LogOut size={15} />
              <span className="hide-mobile">Sign out</span>
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
