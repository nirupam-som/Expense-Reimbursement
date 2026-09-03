/**
 * Every API call the app makes, in one place.
 *
 * Nothing here computes a total, decides whether a button is allowed, or filters a list —
 * the server owns all of that. These functions just carry requests and answers.
 */

import { apiFetch, getToken } from './client.js'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// --- auth -----------------------------------------------------------------------------

export const login = (email, password) =>
  apiFetch('/auth/login', { method: 'POST', body: { email, password } })

export const signup = (payload) =>
  apiFetch('/auth/signup', { method: 'POST', body: payload })

export const me = () => apiFetch('/auth/me')

export const listUsers = (role) =>
  apiFetch(`/users${role ? `?role=${role}` : ''}`)

// --- reports --------------------------------------------------------------------------

export function listReports(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined && value !== false) {
      query.set(key, value)
    }
  })
  return apiFetch(`/reports?${query.toString()}`)
}

export const getReport = (id) => apiFetch(`/reports/${id}`)

export const createReport = (body) => apiFetch('/reports', { method: 'POST', body })

export const updateReport = (id, body) =>
  apiFetch(`/reports/${id}`, { method: 'PATCH', body })

export const archiveReport = (id) => apiFetch(`/reports/${id}/archive`, { method: 'POST' })
export const restoreReport = (id) => apiFetch(`/reports/${id}/restore`, { method: 'POST' })

// --- lifecycle ------------------------------------------------------------------------

export const submitReport = (id) => apiFetch(`/reports/${id}/submit`, { method: 'POST' })
export const approveReport = (id) => apiFetch(`/reports/${id}/approve`, { method: 'POST' })
export const rejectReport = (id, reason) =>
  apiFetch(`/reports/${id}/reject`, { method: 'POST', body: { reason } })
export const markReportPaid = (id) => apiFetch(`/reports/${id}/mark-paid`, { method: 'POST' })

// --- lines ----------------------------------------------------------------------------

export const addLine = (reportId, body) =>
  apiFetch(`/reports/${reportId}/lines`, { method: 'POST', body })
export const updateLine = (reportId, lineId, body) =>
  apiFetch(`/reports/${reportId}/lines/${lineId}`, { method: 'PATCH', body })
export const deleteLine = (reportId, lineId) =>
  apiFetch(`/reports/${reportId}/lines/${lineId}`, { method: 'DELETE' })

// --- approvers ------------------------------------------------------------------------

export const assignApprover = (reportId, approverId) =>
  apiFetch(`/reports/${reportId}/approvers`, {
    method: 'POST',
    body: { approver_id: approverId },
  })
export const unassignApprover = (reportId, approverId) =>
  apiFetch(`/reports/${reportId}/approvers/${approverId}`, { method: 'DELETE' })

// --- timeline and comments ------------------------------------------------------------

export const getTimeline = (reportId) => apiFetch(`/reports/${reportId}/timeline`)
export const addComment = (reportId, body) =>
  apiFetch(`/reports/${reportId}/comments`, { method: 'POST', body: { body } })

// --- bulk -----------------------------------------------------------------------------

export const bulkApprove = (reportIds) =>
  apiFetch('/reports/bulk-approve', { method: 'POST', body: { report_ids: reportIds } })
export const bulkReject = (reportIds, reason) =>
  apiFetch('/reports/bulk-reject', {
    method: 'POST',
    body: { report_ids: reportIds, reason },
  })

/**
 * The CSV lives behind the same bearer auth as everything else, so it cannot be fetched
 * with a plain <a href> — the browser would not attach the header. Fetch it, then hand
 * the blob to a temporary link.
 */
export async function downloadUnpaidCsv() {
  const response = await fetch(`${BASE_URL}/reports/export/unpaid.csv`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (!response.ok) throw new Error('Could not export the CSV.')

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `reimbursements-due-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// --- dashboard and alerts -------------------------------------------------------------

export const getDashboard = () => apiFetch('/dashboard')
export const getStaleAlerts = () => apiFetch('/alerts/stale')
export const dismissAlert = (reportId) =>
  apiFetch(`/reports/${reportId}/alerts/dismiss`, { method: 'POST' })
