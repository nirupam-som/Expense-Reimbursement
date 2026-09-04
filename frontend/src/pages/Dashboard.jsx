import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Clock,
  Wallet,
  CheckCircle2,
  TrendingUp,
  BarChart3,
  PieChart,
  Tag as TagIcon,
  Sparkles,
  ArrowUpRight,
  Plus,
  CheckSquare,
  FileText,
  Activity,
  Layers,
} from 'lucide-react'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  Banner,
  CATEGORY_LABELS,
  STATUS_LABELS,
  Spinner,
  formatMoney,
} from '../components/ui.jsx'

/** Rich SVG & CSS Bar Chart with gridlines and summary statistics */
function WeeklyChart({ weeks }) {
  const totals = weeks.map((week) => Number(week.total))
  const highest = Math.max(...totals, 1)
  const grandTotal = totals.reduce((a, b) => a + b, 0)
  const average = weeks.length > 0 ? grandTotal / weeks.length : 0

  return (
    <div className="chart-container">
      {/* Chart Summary Metric Header */}
      <div className="chart-header">
        <div className="chart-metric">
          <span className="chart-metric__label">Total Paid (8 Weeks)</span>
          <span className="chart-metric__value">{formatMoney(grandTotal)}</span>
        </div>
        <div className="chart-metric">
          <span className="chart-metric__label">Weekly Average</span>
          <span className="chart-metric__value">{formatMoney(average)}</span>
        </div>
        <div className="chart-metric">
          <span className="chart-metric__label">Peak Weekly Spend</span>
          <span className="chart-metric__value">{formatMoney(highest)}</span>
        </div>
      </div>

      {/* Main Chart Body */}
      <div className="chart">
        {/* Background Gridlines */}
        <div className="chart__gridlines">
          <div className="chart__gridline">
            <span>{formatMoney(highest)}</span>
          </div>
          <div className="chart__gridline">
            <span>{formatMoney(highest / 2)}</span>
          </div>
          <div className="chart__gridline">
            <span>₹0</span>
          </div>
        </div>

        {/* Columns */}
        <div className="chart__bars">
          {weeks.map((week) => {
            const value = Number(week.total)
            const height = (value / highest) * 100
            const isHighest = value === highest && value > 0

            return (
              <div className="chart__column" key={week.week_start}>
                <div className="chart__value-bubble">
                  {value > 0 ? formatMoney(value) : '₹0'}
                </div>
                <div className="chart__track">
                  <div
                    className={`chart__bar ${isHighest ? 'chart__bar--peak' : ''}`}
                    style={{ height: `${Math.max(height, value > 0 ? 6 : 2)}%` }}
                  >
                    {isHighest && <span className="chart__peak-dot" />}
                  </div>
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
    </div>
  )
}

function Breakdown({ icon: Icon, title, rows, renderValue }) {
  const total = rows.reduce((sum, row) => sum + row.weight, 0)

  return (
    <section className="card card--breakdown">
      <div className="card__title-row">
        <div className="card__icon-box">
          <Icon size={18} />
        </div>
        <h2 className="card__title">{title}</h2>
      </div>
      <div className="breakdown">
        {rows.map((row) => {
          const percentage = total > 0 ? Math.round((row.weight / total) * 100) : 0
          return (
            <div className="breakdown__row" key={row.key}>
              <div className="breakdown__meta">
                <span className="breakdown__label">{row.label}</span>
                <span className="breakdown__percent">{percentage}%</span>
              </div>
              <div className="breakdown__track">
                <div
                  className={`breakdown__fill breakdown__fill--${row.key}`}
                  style={{ width: `${percentage}%` }}
                />
              </div>
              <span className="breakdown__value">{renderValue(row)}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export default function Dashboard() {
  const { isApprover, user } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getDashboard().then(setData).catch((problem) => setError(problem.detail || problem.message))
  }, [])

  if (error) return <Banner>{error}</Banner>
  if (!data) return <Spinner />

  const now = new Date()
  const hour = now.getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="dashboard-container">
      {/* Top Banner & Quick Actions */}
      <div className="page__header page__header--dashboard">
        <div>
          <div className="greeting-badge">
            <Sparkles size={14} />
            <span>Welcome back</span>
          </div>
          <h1>
            {greeting}, {user.full_name.split(' ')[0]}
          </h1>
          <p className="muted">
            {isApprover
              ? "Here's everything across the company at a glance."
              : 'Track your expense reports and reimbursements.'}
          </p>
        </div>
        <div className="page__actions">
          <Link to="/reports" className="button button--ghost">
            <FileText size={16} /> All reports
          </Link>
          {isApprover && (
            <Link to="/queue" className="button button--ghost">
              <CheckSquare size={16} /> Queue
            </Link>
          )}
          <Link to="/reports" className="button button--primary">
            <Plus size={16} /> New report
          </Link>
        </div>
      </div>

      {/* 4 Stat KPI Cards - Forced 4 Columns Grid */}
      <div className="stats-grid">
        <Link to="/reports?status=submitted" className="stat stat--coral">
          <div className="stat__top">
            <div className="stat__icon stat__icon--coral">
              <Clock size={20} />
            </div>
            <ArrowUpRight size={16} className="stat__arrow" />
          </div>
          <span className="stat__label">Awaiting approval</span>
          <span className="stat__value">{data.awaiting_approval}</span>
          <span className="stat__hint">reports needing a decision</span>
        </Link>

        <div className="stat stat--accent">
          <div className="stat__top">
            <div className="stat__icon stat__icon--teal">
              <Wallet size={20} />
            </div>
          </div>
          <span className="stat__label">Reimbursements due</span>
          <span className="stat__value">{formatMoney(data.total_due)}</span>
          <span className="stat__hint">approved, not yet paid</span>
        </div>

        <div className="stat stat--blue">
          <div className="stat__top">
            <div className="stat__icon stat__icon--blue">
              <CheckCircle2 size={20} />
            </div>
          </div>
          <span className="stat__label">Approved this week</span>
          <span className="stat__value">{data.approved_this_week}</span>
          <span className="stat__hint">since Monday</span>
        </div>

        <div className="stat stat--cream">
          <div className="stat__top">
            <div className="stat__icon stat__icon--cream">
              <TrendingUp size={20} />
            </div>
          </div>
          <span className="stat__label">Paid this week</span>
          <span className="stat__value">{data.paid_this_week}</span>
          <span className="stat__hint">since Monday</span>
        </div>
      </div>

      {/* Full Width Weekly Spend Chart */}
      <section className="card card--full-chart">
        <div className="card__title-row">
          <div className="card__icon-box">
            <BarChart3 size={18} />
          </div>
          <div>
            <h2 className="card__title">Reimbursements paid — last 8 weeks</h2>
            <p className="card__subtitle">Weekly disbursement trends across all departments</p>
          </div>
        </div>
        <WeeklyChart weeks={data.weekly_paid} />
      </section>

      {/* 2-Column Side by Side Breakdown */}
      <div className="dashboard-grid-2">
        <Breakdown
          icon={PieChart}
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
          icon={TagIcon}
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

      {/* Quick Summary Insights Row */}
      <section className="card card--insights">
        <div className="insights-row">
          <div className="insight-item">
            <Activity size={18} className="insight-icon" />
            <div>
              <span className="insight-label">System Status</span>
              <span className="insight-value text-sage">Active & Live</span>
            </div>
          </div>
          <div className="insight-item">
            <Layers size={18} className="insight-icon" />
            <div>
              <span className="insight-label">Tracked Categories</span>
              <span className="insight-value">{data.by_category.length} Active</span>
            </div>
          </div>
          <div className="insight-item">
            <CheckCircle2 size={18} className="insight-icon" />
            <div>
              <span className="insight-label">Compliance</span>
              <span className="insight-value">100% Verified</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
