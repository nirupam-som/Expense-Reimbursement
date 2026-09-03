/** Small shared presentational pieces. */

const CURRENCY = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' })

/** Amounts arrive as strings (the API preserves decimal precision), so parse then format. */
export const formatMoney = (value) => CURRENCY.format(Number(value ?? 0))

export const formatDate = (value) =>
  value ? new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

export const formatDateTime = (value) =>
  value
    ? new Date(value).toLocaleString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'

export const STATUS_LABELS = {
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Approved',
  rejected: 'Rejected',
  paid: 'Paid',
}

export const CATEGORY_LABELS = {
  travel: 'Travel',
  lodging: 'Lodging',
  meals: 'Meals',
  transportation: 'Transportation',
  supplies: 'Supplies',
  other: 'Other',
}

export function StatusBadge({ status }) {
  return <span className={`badge badge--${status}`}>{STATUS_LABELS[status] ?? status}</span>
}

export function Banner({ kind = 'error', children, onDismiss }) {
  if (!children) return null
  return (
    <div className={`banner banner--${kind}`}>
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="banner__close" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, hint }) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {hint && <p className="empty__hint">{hint}</p>}
    </div>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return <p className="muted">{label}</p>
}

export function Pagination({ page, pageSize, total, onPage }) {
  const lastPage = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)

  return (
    <div className="pagination">
      {/* `total` is the count of every match on the server, not just this page. */}
      <span className="muted">
        {total === 0 ? 'No matches' : `${first}–${last} of ${total}`}
      </span>
      <div className="pagination__buttons">
        <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span className="muted">
          Page {page} of {lastPage}
        </span>
        <button type="button" disabled={page >= lastPage} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </div>
    </div>
  )
}
