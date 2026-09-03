import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  Banner,
  CATEGORY_LABELS,
  STATUS_LABELS,
  Spinner,
  formatMoney,
} from '../components/ui.jsx'

/** Eight weeks of payments, drawn as plain SVG — a whole charting library would be a lot
 *  of weight for one bar chart. */
function WeeklyChart({ weeks }) {
  const highest = Math.max(...weeks.map((week) => Number(week.total)), 1)

  return (
    <div className="chart">
      <div className="chart__bars">
        {weeks.map((week) => {
          const value = Number(week.total)
          const height = (value / highest) * 100
          return (
            <div className="chart__column" key={week.week_start}>
              <div className="chart__value">{value > 0 ? formatMoney(value) : ''}</div>
              <div className="chart__track">
                {/* Zero weeks keep their column so the timeline reads honestly. */}
                <div
                  className="chart__bar"
                  style={{ height: `${Math.max(height, value > 0 ? 4 : 0)}%` }}
                />
              </div>
              <div className="chart__label">
                {new Date(week.week_start).toLocaleDateString('en-GB', {
                  day: '2-digit',
                  month: 'short',
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Breakdown({ title, rows, renderValue }) {
  const total = rows.reduce((sum, row) => sum + row.weight, 0)

  return (
    <section className="card">
      <h2 className="card__title">{title}</h2>
      <div className="breakdown">
        {rows.map((row) => (
          <div className="breakdown__row" key={row.key}>
            <span className="breakdown__label">{row.label}</span>
            <div className="breakdown__track">
              <div
                className="breakdown__fill"
                style={{ width: total > 0 ? `${(row.weight / total) * 100}%` : '0%' }}
              />
            </div>
            <span className="breakdown__value">{renderValue(row)}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Dashboard() {
  const { isApprover } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getDashboard().then(setData).catch((problem) => setError(problem.detail || problem.message))
  }, [])

  if (error) return <Banner>{error}</Banner>
  if (!data) return <Spinner />

  return (
    <div className="stack-lg">
      <div className="page__header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">
            {isApprover
              ? 'Everything across the company.'
              : 'Your own reports and reimbursements.'}
          </p>
        </div>
      </div>

      <div className="stats">
        <Link to="/reports?status=submitted" className="stat">
          <span className="stat__label">Awaiting approval</span>
          <span className="stat__value">{data.awaiting_approval}</span>
          <span className="stat__hint">reports needing a decision</span>
        </Link>

        <div className="stat stat--accent">
          <span className="stat__label">Reimbursements due</span>
          <span className="stat__value">{formatMoney(data.total_due)}</span>
          <span className="stat__hint">approved, not yet paid</span>
        </div>

        <div className="stat">
          <span className="stat__label">Approved this week</span>
          <span className="stat__value">{data.approved_this_week}</span>
          <span className="stat__hint">since Monday</span>
        </div>

        <div className="stat">
          <span className="stat__label">Paid this week</span>
          <span className="stat__value">{data.paid_this_week}</span>
          <span className="stat__hint">since Monday</span>
        </div>
      </div>

      <section className="card">
        <h2 className="card__title">Reimbursements paid — last 8 weeks</h2>
        <WeeklyChart weeks={data.weekly_paid} />
      </section>

      <div className="grid-2">
        <Breakdown
          title="Reports by status"
          rows={data.by_status.map((row) => ({
            key: row.status,
            label: STATUS_LABELS[row.status],
            weight: row.count,
            count: row.count,
          }))}
          renderValue={(row) => row.count}
        />
        <Breakdown
          title="Spend by category"
          rows={data.by_category.map((row) => ({
            key: row.category,
            label: CATEGORY_LABELS[row.category],
            weight: Number(row.total),
            total: row.total,
          }))}
          renderValue={(row) => formatMoney(row.total)}
        />
      </div>
    </div>
  )
}
