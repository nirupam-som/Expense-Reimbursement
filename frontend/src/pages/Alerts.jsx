import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  Banner,
  EmptyState,
  Spinner,
  formatDate,
  formatMoney,
} from '../components/ui.jsx'

export default function Alerts() {
  const { isApprover } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    api.getStaleAlerts().then(setData).catch((problem) => setError(problem.detail || problem.message))
  }, [])

  useEffect(load, [load])

  async function dismiss(reportId) {
    try {
      await api.dismissAlert(reportId)
      load()
    } catch (problem) {
      setError(problem.detail || problem.message)
    }
  }

  if (!data) return <Spinner />

  return (
    <div className="stack-lg">
      <div className="page__header">
        <div>
          <h1>Stale approvals</h1>
          <p className="muted">
            Reports that have sat in Submitted for more than {data.threshold_days} days
            without a decision. Dismissing one hides it for you for{' '}
            {data.realert_after_days} days — if it is still undecided after that, it comes
            back.
          </p>
        </div>
      </div>

      <Banner onDismiss={() => setError(null)}>{error}</Banner>

      {data.items.length === 0 ? (
        <EmptyState
          title="Nothing is overdue."
          hint="Every submitted report has been decided within the threshold."
        />
      ) : (
        <section className="card card--flush">
          <table className="table">
            <thead>
              <tr>
                <th>Report</th>
                <th>Owner</th>
                <th>Submitted</th>
                <th>Waiting</th>
                <th className="right">Total</th>
                {isApprover && <th />}
              </tr>
            </thead>
            <tbody>
              {data.items.map((alert) => (
                <tr key={alert.report.id}>
                  <td>
                    <Link to={`/reports/${alert.report.id}`} className="link-strong">
                      {alert.report.title}
                    </Link>
                  </td>
                  <td>{alert.report.owner.full_name}</td>
                  <td className="muted">{formatDate(alert.report.submitted_at)}</td>
                  <td>
                    <span className="badge badge--warn">{alert.days_waiting} days</span>
                  </td>
                  <td className="right mono">{formatMoney(alert.report.total)}</td>
                  {isApprover && (
                    <td className="right">
                      {alert.can_dismiss ? (
                        <button
                          type="button"
                          className="button button--ghost button--small"
                          onClick={() => dismiss(alert.report.id)}
                        >
                          Dismiss
                        </button>
                      ) : (
                        <span className="muted">Not assigned to you</span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
