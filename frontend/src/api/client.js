/**
 * Single place every API call goes through.
 *
 * Attaches the JWT as an Authorization header (not a cookie — the API is on a different
 * origin, see docs/architecture.md) and turns non-2xx responses into thrown errors
 * carrying the server's explanation, since the server is the only thing that decides
 * whether an action was allowed.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const TOKEN_KEY = 'expense_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function apiFetch(path, { method = 'GET', body, ...rest } = {}) {
  const token = getToken()

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...rest.headers,
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
    ...rest,
  })

  if (!response.ok) {
    // FastAPI puts human-readable refusals in `detail`; surface them rather than a
    // generic message, because the "why" matters (illegal transition, self-approval, ...).
    let detail
    try {
      detail = (await response.json())?.detail
    } catch {
      detail = await response.text()
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return null
  return response.json()
}
