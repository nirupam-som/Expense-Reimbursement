import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout.jsx'
import { Spinner } from './components/ui.jsx'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import Alerts from './pages/Alerts.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'
import ReportDetail from './pages/ReportDetail.jsx'
import Reports from './pages/Reports.jsx'

/** Keeps unauthenticated visitors out of the app shell.
 *  This is convenience, not security — every endpoint enforces its own rules server-side. */
function RequireAuth({ children }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="page"><Spinner /></div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  const { user } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/:reportId" element={<ReportDetail />} />
        <Route path="/queue" element={<Reports queueMode />} />
        <Route path="/alerts" element={<Alerts />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
