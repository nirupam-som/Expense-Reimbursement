import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Send,
  Check,
  X,
  CreditCard,
  Archive,
  RotateCcw,
  Receipt,
  Plus,
  Users,
  History,
  MessageSquare,
  AlertTriangle,
  Lock,
  Trash2,
} from 'lucide-react'

import * as api from '../api/endpoints.js'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  Banner,
  CATEGORY_LABELS,
  STATUS_LABELS,
  Spinner,
  StatusBadge,
  formatDate,
  formatDateTime,
  formatMoney,
} from '../components/ui.jsx'

const BLANK_LINE = {
  expense_date: new Date().toISOString().slice(0, 10),
  amount: '',
  category: 'travel',
  description: '',
}

function LineEditor({ reportId, onChanged }) {
  const [line, setLine] = useState(BLANK_LINE)
  const [error, setError] = useState(null)
  const update = (field) => (event) => setLine({ ...line, [field]: event.target.value })

  async function add(event) {
    event.preventDefault()
    setError(null)
    try {
      await api.addLine(reportId, line)
      setLine(BLANK_LINE)
      onChanged()
    } catch (problem) {
      setError(problem.detail || problem.message)
    }
  }

  return (
    <>
      <Banner onDismiss={() => setError(null)}>{error}</Banner>
      <form className="form-row" onSubmit={add}>
        <label>
          Date
          <input type="date" value={line.expense_date} onChange={update('expense_date')} required />
        </label>
        <label>
          Amount (₹)
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={line.amount}
            onChange={update('amount')}
            placeholder="0.00"
            required
          />
        </label>
        <label>
          Category
          <select value={line.category} onChange={update('category')}>
            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="grow">
          Description
          <input
            value={line.description}
            onChange={update('description')}
            placeholder="What was this for?"
            required
          />
        </label>
        <div className="form-row__actions">
          <button type="submit" className="button button--primary">
            <Plus size={16} /> Add line
          </button>
        </div>
      </form>
    </>
  )
}

function Timeline({ entries }) {
  if (entries.length === 0) {
    return <p className="muted margin-top-sm">Nothing has happened to this report yet.</p>
  }

  return (
    <ol className="timeline">
      {entries.map((entry) => (
        <li className="timeline__item" key={`${entry.kind}-${entry.id}`}>
          <span className={`timeline__dot timeline__dot--${entry.to_status ?? 'comment'}`} />
          <div className="timeline__body">
            <div className="timeline__head">
              <strong>{entry.actor.full_name}</strong>
              <span className="muted">{formatDateTime(entry.at)}</span>
            </div>
            {entry.kind === 'status_change' ? (
              <p>
                Changed status from <StatusBadge status={entry.from_status} /> to{' '}
                <StatusBadge status={entry.to_status} />
              </p>
            ) : (
              <p className="timeline__comment">{entry.body}</p>
            )}
            {entry.reason && <p className="timeline__reason">"{entry.reason}"</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}

export default function ReportDetail() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const { user, isApprover } = useAuth()

  const [report, setReport] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [approverOptions, setApproverOptions] = useState([])
  const [comment, setComment] = useState('')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    Promise.all([api.getReport(reportId), api.getTimeline(reportId)])
      .then(([reportResponse, timelineResponse]) => {
        setReport(reportResponse)
        setTimeline(timelineResponse)
      })
      .catch((problem) => setError(problem.detail || problem.message))
  }, [reportId])

  useEffect(load, [load])

  useEffect(() => {
    api.listUsers('approver').then(setApproverOptions).catch(() => setApproverOptions([]))
  }, [])

  if (error && !report) return <Banner>{error}</Banner>
  if (!report) return <Spinner />

  const isOwner = report.owner.id === user.id
  const isDraft = report.status === 'draft'
  const canDecide = isApprover && !isOwner && report.status === 'submitted'
  const canMarkPaid = isApprover && !isOwner && report.status === 'approved'

  async function run(action, successMessage) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await action()
      setNotice(successMessage)
      load()
    } catch (problem) {
      setError(problem.detail || problem.message)
    } finally {
      setBusy(false)
    }
  }

  const reject = () => {
    const reason = window.prompt('Why is this report being rejected?')
    if (!reason || !reason.trim()) return
    run(() => api.rejectReport(report.id, reason), 'Rejected and returned to the owner as a draft.')
  }

  return (
    <div className="stack-lg">
      <div className="page__header">
        <div>
          <button type="button" className="link-back" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
          <h1>{report.title}</h1>
          <p className="muted">
            {report.owner.full_name} · {formatDate(report.date_range_start)} –{' '}
            {formatDate(report.date_range_end)}
            {report.is_archived && <span className="tag">Archived</span>}
          </p>
        </div>
        <div className="report__summary">
          <StatusBadge status={report.status} />
          <div className="report__total">
            <span className="report__total-label">Total</span>
            <strong>{formatMoney(report.total)}</strong>
          </div>
        </div>
      </div>

      <Banner onDismiss={() => setError(null)}>{error}</Banner>
      <Banner kind="success" onDismiss={() => setNotice(null)}>{notice}</Banner>

      <div className="actions">
        {isOwner && isDraft && (
          <button
            type="button"
            className="button button--primary"
            disabled={busy}
            onClick={() => run(() => api.submitReport(report.id), 'Submitted for approval.')}
          >
            <Send size={16} /> Submit for approval
          </button>
        )}
        {canDecide && (
          <>
            <button
              type="button"
              className="button button--primary"
              disabled={busy}
              onClick={() => run(() => api.approveReport(report.id), 'Approved.')}
            >
              <Check size={16} /> Approve
            </button>
            <button type="button" className="button button--danger" disabled={busy} onClick={reject}>
              <X size={16} /> Reject
            </button>
          </>
        )}
        {canMarkPaid && (
          <button
            type="button"
            className="button button--primary"
            disabled={busy}
            onClick={() => run(() => api.markReportPaid(report.id), 'Marked as paid.')}
          >
            <CreditCard size={16} /> Mark as paid
          </button>
        )}
        {isApprover && isOwner && report.status === 'submitted' && (
          <p className="notice">
            <AlertTriangle size={16} /> You own this report, so you cannot decide on it yourself — it has to wait for a
            different approver.
          </p>
        )}
        {isOwner && (
          <button
            type="button"
            className="button button--ghost"
            disabled={busy}
            onClick={() =>
              run(
                () =>
                  report.is_archived
                    ? api.restoreReport(report.id)
                    : api.archiveReport(report.id),
                report.is_archived ? 'Restored.' : 'Archived.',
              )
            }
          >
            {report.is_archived ? (
              <>
                <RotateCcw size={16} /> Restore
              </>
            ) : (
              <>
                <Archive size={16} /> Archive
              </>
            )}
          </button>
        )}
      </div>

      <section className="card card--flush">
        <div className="card__header">
          <div className="card__title-row">
            <Receipt size={18} className="card__title-icon" />
            <h2 className="card__title">Expense lines</h2>
          </div>
          {!isDraft && (
            <span className="badge badge--submitted">
              <Lock size={12} /> Locked — {STATUS_LABELS[report.status]}
            </span>
          )}
        </div>

        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Category</th>
              <th>Description</th>
              <th className="right">Amount</th>
              {isOwner && isDraft && <th />}
            </tr>
          </thead>
          <tbody>
            {report.lines.length === 0 && (
              <tr>
                <td colSpan={5} className="muted text-center padding-lg">
                  No expense lines yet. Add your first line below.
                </td>
              </tr>
            )}
            {report.lines.map((line) => (
              <tr key={line.id}>
                <td>{formatDate(line.expense_date)}</td>
                <td>
                  <span className="badge badge--submitted">
                    {CATEGORY_LABELS[line.category]}
                  </span>
                </td>
                <td className="text-secondary">{line.description}</td>
                <td className="right mono text-bold">
                  {formatMoney(line.amount)}
                </td>
                {isOwner && isDraft && (
                  <td className="right">
                    <button
                      type="button"
                      className="button button--ghost button--small text-danger"
                      onClick={() =>
                        run(() => api.deleteLine(report.id, line.id), 'Line removed.')
                      }
                    >
                      <Trash2 size={14} /> Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>
                <strong>Total</strong>
                <span className="muted margin-left-xs text-xs">
                  — calculated server-side from the lines above
                </span>
              </td>
              <td className="right mono text-bold text-lg">
                {formatMoney(report.total)}
              </td>
              {isOwner && isDraft && <td />}
            </tr>
          </tfoot>
        </table>

        {isOwner && isDraft && (
          <div className="card__section">
            <LineEditor reportId={report.id} onChanged={load} />
          </div>
        )}
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="card__title-row">
            <Users size={18} className="card__title-icon" />
            <h2 className="card__title">Assigned approvers</h2>
          </div>
          <p className="muted text-xs">
            Assignment decides whose queue this appears in. Any approver who does not own
            the report can still decide on it.
          </p>

          <ul className="chips">
            {report.approvers.length === 0 && (
              <li className="muted italic text-sm">Nobody assigned yet.</li>
            )}
            {report.approvers.map((person) => (
              <li className="chip" key={person.id}>
                {person.full_name}
                {(isOwner || isApprover) && (
                  <button
                    type="button"
                    onClick={() =>
                      run(
                        () => api.unassignApprover(report.id, person.id),
                        `${person.full_name} unassigned.`,
                      )
                    }
                    aria-label={`Unassign ${person.full_name}`}
                  >
                    ×
                  </button>
                )}
              </li>
            ))}
          </ul>

          {(isOwner || isApprover) && (
            <select
              className="select-block"
              value=""
              onChange={(event) =>
                event.target.value &&
                run(
                  () => api.assignApprover(report.id, Number(event.target.value)),
                  'Approver assigned.',
                )
              }
            >
              <option value="">Assign an approver…</option>
              {approverOptions
                .filter((person) => !report.approvers.some((a) => a.id === person.id))
                .map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}</option>
                ))}
            </select>
          )}
        </section>

        <section className="card">
          <div className="card__title-row">
            <History size={18} className="card__title-icon" />
            <h2 className="card__title">History</h2>
          </div>
          <p className="muted text-xs">
            Every status change and comment, permanently. Nothing here can be edited or
            deleted — by anyone.
          </p>
          <Timeline entries={timeline} />

          <form
            className="comment"
            onSubmit={(event) => {
              event.preventDefault()
              if (!comment.trim()) return
              run(() => api.addComment(report.id, comment), 'Comment added.').then(() =>
                setComment(''),
              )
            }}
          >
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Add a comment…"
              rows={2}
            />
            <button type="submit" className="button button--primary" disabled={busy || !comment.trim()}>
              <MessageSquare size={15} /> Post
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}
