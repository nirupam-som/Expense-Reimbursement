import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Receipt, ArrowRight, ShieldCheck, User } from 'lucide-react'

import { useAuth } from '../auth/AuthContext.jsx'
import { Banner } from '../components/ui.jsx'

const DEMO_ACCOUNTS = [
  { email: 'priya@acme.com',  label: 'Priya Sharma',  role: 'Approver' },
  { email: 'daniel@acme.com', label: 'Daniel Okafor', role: 'Approver' },
  { email: 'aisha@acme.com',  label: 'Aisha Khan',    role: 'Employee' },
  { email: 'tom@acme.com',    label: 'Tom Becker',    role: 'Employee' },
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
        <div className="auth__logo">
          <div className="auth__logo-mark">
            <Receipt size={22} />
          </div>
          <div>
            <div className="auth__logo-name">ExpenseFlow</div>
            <div className="auth__logo-tag">Reimbursement Platform</div>
          </div>
        </div>

        <h1 className="auth__title">
          {mode === 'signin' ? 'Welcome back' : 'Create account'}
        </h1>
        <p className="muted margin-bottom-xs">
          {mode === 'signin'
            ? 'Sign in to manage your expense reports.'
            : 'Join your team on ExpenseFlow.'}
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
              <input
                value={form.full_name}
                onChange={update('full_name')}
                placeholder="Your full name"
                required
                autoComplete="name"
              />
            </label>
          )}

          <label>
            Email address
            <input
              type="email"
              value={form.email}
              onChange={update('email')}
              placeholder="you@company.com"
              required
              autoComplete="email"
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={form.password}
              onChange={update('password')}
              placeholder={mode === 'signup' ? 'At least 8 characters' : '••••••••'}
              required
              minLength={mode === 'signup' ? 8 : 1}
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
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

          <button
            type="submit"
            className="button button--primary button--lg"
            disabled={busy}
          >
            {busy ? (
              'Please wait…'
            ) : mode === 'signin' ? (
              <>
                Sign in <ArrowRight size={16} />
              </>
            ) : (
              <>
                Create account <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {mode === 'signin' && (
          <div className="auth__demo">
            <p className="muted">
              Demo accounts — password <code>password123</code>
            </p>
            <div className="auth__demo-list">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.email}
                  type="button"
                  className="auth__demo-btn"
                  onClick={() =>
                    setForm({ ...form, email: account.email, password: 'password123' })
                  }
                >
                  <span className="text-bold">{account.label}</span>
                  <span className="auth__demo-role">
                    {account.role === 'Approver' ? <ShieldCheck size={12} /> : <User size={12} />}
                    {account.role}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
