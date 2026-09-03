import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  Banner,
  EmptyState,
  Pagination,
  STATUS_LABELS,
  Spinner,
  StatusBadge,
  formatDate,
  formatMoney,
} from '../components/ui.jsx'

const PAGE_SIZE = 10

function NewReportForm({ onCreated, onCancel }) {
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({
    title: '',
    date_range_start: today,
    date_range_end: today,
  })
  const [error, setError] = useState(null)
  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value })

  async function submit(event) {
    event.preventDefault()
    try {
      onCreated(await api.createReport(form))
    } catch (problem) {
      setError(problem.detail || problem.message)
    }
  }

  return (
    <section className="card">
      <h2 className="card__title">New expense report</h2>
      <Banner onDismiss={() => setError(null)}>{error}</Banner>
      <form className="form-row" onSubmit={submit}>
        <label className="grow">
          Title
          <input
            value={form.title}
            onChange={update('title')}
            placeholder="e.g. Client visit — Berlin"
            required
          />
        </label>
        <label>
          From
          <input type="date" value={form.date_range_start} onChange={update('date_range_start')} required />
        </label>
        <label>
          To
          <input type="date" value={form.date_range_end} onChange={update('date_range_end')} required />
        </label>
        <div className="form-row__actions">
          <button type="submit" className="button button--primary">Create</button>
          <button type="button" className="button button--ghost" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </section>
  )
}

function BulkResult({ result, onClose }) {
  if (!result) return null
  return (
    <div className="banner banner--info">
      <div>
        <strong>
          {result.succeeded} succeeded, {result.refused} refused.
        </strong>
        {result.owned_by_you > 0 && (
          <p className="bulk__own">
            {result.owned_by_you}{' '}
            {result.owned_by_you === 1 ? 'report was' : 'reports were'} skipped because you
            own {result.owned_by_you === 1 ? 'it' : 'them'} — someone else has to decide.
          </p>
        )}
        <ul className="bulk__list">
          {result.results
            .filter((item) => item.outcome !== 'approved' && item.outcome !== 'rejected')
            .map((item) => (
              <li key={item.report_id}>
                <strong>#{item.report_id}</strong> — {item.message}
              </li>
            ))}
        </ul>
      </div>
      <button type="button" className="banner__close" onClick={onClose} aria-label="Dismiss">×</button>
    </div>
  )
}

export default function Reports({ queueMode = false }) {
  const { user, isApprover } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const [filters, setFilters] = useState({
    search: searchParams.get('search') ?? '',
    status: searchParams.get('status') ?? (queueMode ? 'submitted' : ''),
    owner_id: '',
    approver_id: '',
    assigned_to_me: queueMode && searchParams.get('assigned') === 'me',
    archived_only: false,
    sort: 'created_at',
    direction: 'desc',
  })
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [people, setPeople] = useState([])
  const [selected, setSelected] = useState([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [bulkResult, setBulkResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api
      .listReports({ ...filters, page, page_size: PAGE_SIZE })
      .then(setData)
      .catch((problem) => setError(problem.detail || problem.message))
  }, [filters, page])

  useEffect(load, [load])

  useEffect(() => {
    if (isApprover) api.listUsers().then(setPeople).catch(() => setPeople([]))
  }, [isApprover])

  const setFilter = (field) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value
    setFilters((current) => ({ ...current, [field]: value }))
    setPage(1)
    setSelected([])
    if (field === 'status') {
      searchParams.set('status', value)
      setSearchParams(searchParams, { replace: true })
    }
  }

  const toggle = (id) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    )

  // Only Submitted reports can be decided, so only those are selectable.
  const selectable = (data?.items ?? []).filter((item) => item.status === 'submitted')
  const allSelected = selectable.length > 0 && selected.length === selectable.length

  async function runBulk(kind) {
    setBusy(true)
    setError(null)
    try {
      let reason = null
      if (kind === 'reject') {
        reason = window.prompt('Why are these reports being rejected?')
        if (!reason || !reason.trim()) {
          setBusy(false)
          return
        }
      }
      const result =
        kind === 'approve'
          ? await api.bulkApprove(selected)
          : await api.bulkReject(selected, reason)
      setBulkResult(result)
      setSelected([])
      load()
    } catch (problem) {
      setError(problem.detail || problem.message)
    } finally {
      setBusy(false)
    }
  }

  async function exportCsv() {
    try {
      await api.downloadUnpaidCsv()
    } catch (problem) {
      setError(problem.message)
    }
  }

  return (
    <div className="stack-lg">
      <div className="page__header">
        <div>
          <h1>{queueMode ? 'Approval queue' : 'Expense reports'}</h1>
          <p className="muted">
            {queueMode
              ? 'Reports submitted and awaiting a decision.'
              : isApprover
                ? 'Every report across the company.'
                : 'Your expense reports.'}
          </p>
        </div>
        <div className="page__actions">
          {isApprover && (
            <button type="button" className="button" onClick={exportCsv}>
              Export reimbursements due (CSV)
            </button>
          )}
          {!queueMode && (
            <button
              type="button"
              className="button button--primary"
              onClick={() => setCreating((value) => !value)}
            >
              New report
            </button>
          )}
        </div>
      </div>

      <Banner onDismiss={() => setError(null)}>{error}</Banner>
      <BulkResult result={bulkResult} onClose={() => setBulkResult(null)} />

      {creating && (
        <NewReportForm
          onCreated={() => {
            setCreating(false)
            load()
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      <section className="card">
        {/* Every one of these controls is a server-side query parameter — nothing here
            filters an already-loaded list in the browser. */}
        <div className="filters">
          <label className="grow">
            Search titles
            <input
              value={filters.search}
              onChange={setFilter('search')}
              placeholder="Search by report title…"
            />
          </label>

          <label>
            Status
            <select value={filters.status} onChange={setFilter('status')}>
              <option value="">All statuses</option>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>

          {isApprover && (
            <>
              <label>
                Owner
                <select value={filters.owner_id} onChange={setFilter('owner_id')}>
                  <option value="">Anyone</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>{person.full_name}</option>
                  ))}
                </select>
              </label>
              <label>
                Approver
                <select value={filters.approver_id} onChange={setFilter('approver_id')}>
                  <option value="">Anyone</option>
                  {people
                    .filter((person) => person.role === 'approver')
                    .map((person) => (
                      <option key={person.id} value={person.id}>{person.full_name}</option>
                    ))}
                </select>
              </label>
            </>
          )}

          <label>
            Sort by
            <select value={filters.sort} onChange={setFilter('sort')}>
              <option value="created_at">Created</option>
              <option value="submitted_at">Submitted date</option>
              <option value="status">Status</option>
              <option value="total">Total amount</option>
              <option value="title">Title</option>
            </select>
          </label>

          <label>
            Order
            <select value={filters.direction} onChange={setFilter('direction')}>
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </div>

        <div className="filters__toggles">
          {isApprover && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={filters.assigned_to_me}
                onChange={setFilter('assigned_to_me')}
              />
              Only reports assigned to me
            </label>
          )}
          <label className="checkbox">
            <input
              type="checkbox"
              checked={filters.archived_only}
              onChange={setFilter('archived_only')}
            />
            Show archived instead
          </label>
        </div>
      </section>

      {isApprover && selected.length > 0 && (
        <div className="bulkbar">
          <span>
            <strong>{selected.length}</strong> selected
          </span>
          <div className="bulkbar__actions">
            <button
              type="button"
              className="button button--primary"
              disabled={busy}
              onClick={() => runBulk('approve')}
            >
              Approve selected
            </button>
            <button
              type="button"
              className="button button--danger"
              disabled={busy}
              onClick={() => runBulk('reject')}
            >
              Reject selected
            </button>
            <button type="button" className="button button--ghost" onClick={() => setSelected([])}>
              Clear
            </button>
          </div>
        </div>
      )}

      {!data ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No reports match."
          hint="Try clearing the search or changing the filters."
        />
      ) : (
        <section className="card card--flush">
          <table className="table">
            <thead>
              <tr>
                {isApprover && (
                  <th className="table__check">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      disabled={selectable.length === 0}
                      onChange={() =>
                        setSelected(allSelected ? [] : selectable.map((item) => item.id))
                      }
                      aria-label="Select all submitted reports"
                    />
                  </th>
                )}
                <th>Report</th>
                <th>Owner</th>
                <th>Period</th>
                <th>Status</th>
                <th className="right">Total</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((report) => (
                <tr key={report.id}>
                  {isApprover && (
                    <td className="table__check">
                      <input
                        type="checkbox"
                        checked={selected.includes(report.id)}
                        disabled={report.status !== 'submitted'}
                        onChange={() => toggle(report.id)}
                        aria-label={`Select ${report.title}`}
                      />
                    </td>
                  )}
                  <td>
                    <Link to={`/reports/${report.id}`} className="link-strong">
                      {report.title}
                    </Link>
                    {report.is_archived && <span className="tag">Archived</span>}
                    {report.owner.id === user.id && isApprover && (
                      <span className="tag tag--warn">Yours</span>
                    )}
                  </td>
                  <td>{report.owner.full_name}</td>
                  <td className="muted">
                    {formatDate(report.date_range_start)} – {formatDate(report.date_range_end)}
                  </td>
                  <td><StatusBadge status={report.status} /></td>
                  <td className="right mono">{formatMoney(report.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPage={setPage}
          />
        </section>
      )}
    </div>
  )
}
