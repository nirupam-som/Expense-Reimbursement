import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext.jsx'
import { Banner } from '../components/ui.jsx'

const DEMO_ACCOUNTS = [
  { email: 'priya@acme.com', label: 'Priya Sharma — approver' },
  { email: 'daniel@acme.com', label: 'Daniel Okafor — approver' },
  { email: 'aisha@acme.com', label: 'Aisha Khan — employee' },
  { email: 'tom@acme.com', label: 'Tom Becker — employee' },
]

export default function Login() {
  const { signIn, register } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState('signin')
  const [form, setForm] = useState({
    email: '',
    password: '',
    full_name: '',
    role: 'employee',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value })

  async function handleSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'signin') {
        await signIn(form.email, form.password)
      } else {
        await register(form)
      }
      navigate('/')
    } catch (problem) {
      setError(problem.detail || problem.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <h1 className="auth__title">Expense Reimbursement</h1>
        <p className="muted">
          Submit expenses, get them approved by someone other than yourself, and see what
          the company owes.
        </p>

        <div className="tabs">
          <button
            type="button"
            className={mode === 'signin' ? 'tab tab--active' : 'tab'}
            onClick={() => setMode('signin')}
          >
            Sign in
          </button>
          <button
            type="button"
            className={mode === 'signup' ? 'tab tab--active' : 'tab'}
            onClick={() => setMode('signup')}
          >
            Create account
          </button>
        </div>

        <Banner onDismiss={() => setError(null)}>{error}</Banner>

        <form onSubmit={handleSubmit} className="stack">
          {mode === 'signup' && (
            <label>
              Full name
              <input value={form.full_name} onChange={update('full_name')} required />
            </label>
          )}

          <label>
            Email
            <input type="email" value={form.email} onChange={update('email')} required />
          </label>

          <label>
            Password
            <input
              type="password"
              value={form.password}
              onChange={update('password')}
              required
              minLength={mode === 'signup' ? 8 : 1}
            />
          </label>

          {mode === 'signup' && (
            <label>
              Role
              <select value={form.role} onChange={update('role')}>
                <option value="employee">Employee</option>
                <option value="approver">Approver</option>
              </select>
            </label>
          )}

          <button type="submit" className="button button--primary" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        {mode === 'signin' && (
          <div className="auth__demo">
            <p className="muted">Demo accounts — password <code>password123</code></p>
            <div className="auth__demo-list">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.email}
                  type="button"
                  className="button button--ghost"
                  onClick={() => setForm({ ...form, email: account.email, password: 'password123' })}
                >
                  {account.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
