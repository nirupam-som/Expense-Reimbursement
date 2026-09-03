import { useEffect, useState } from 'react'

import { apiFetch } from '../api/client.js'

/**
 * Temporary. Confirms the three pieces are wired together — browser reaches the API, the
 * API reaches Postgres. Replaced by the dashboard once real screens exist.
 */
export default function ScaffoldCheck() {
  const [api, setApi] = useState('checking...')
  const [database, setDatabase] = useState('checking...')

  useEffect(() => {
    apiFetch('/health')
      .then(() => setApi('reachable'))
      .catch((error) => setApi(`unreachable — ${error.message}`))

    apiFetch('/health/db')
      .then(() => setDatabase('reachable'))
      .catch((error) => setDatabase(`unreachable — ${error.message}`))
  }, [])

  return (
    <main>
      <h1>Expense Reimbursement</h1>
      <p>Scaffold is up. Nothing is built yet — this page only checks the wiring.</p>
      <dl>
        <dt>Frontend</dt>
        <dd>running</dd>
        <dt>API</dt>
        <dd>{api}</dd>
        <dt>Database</dt>
        <dd>{database}</dd>
      </dl>
    </main>
  )
}
