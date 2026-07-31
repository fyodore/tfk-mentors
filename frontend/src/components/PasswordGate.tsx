import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { checkAuthSession, loginSitePassword } from '../api'

import './PasswordGate.css'

type PasswordGateProps = {
  children: ReactNode
}

export function PasswordGate({ children }: PasswordGateProps) {
  const [ready, setReady] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    checkAuthSession()
      .then((ok) => {
        if (!cancelled) {
          setAuthenticated(ok)
          setReady(true)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuthenticated(false)
          setReady(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await loginSitePassword(password)
      setAuthenticated(true)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (!ready) {
    return (
      <div className="password-gate">
        <p className="muted">Loading…</p>
      </div>
    )
  }

  if (!authenticated) {
    return (
      <div className="password-gate">
        <main className="panel password-gate-panel">
          <h1>TFK Mentors</h1>
          <p className="password-gate-intro">Enter the site password to continue.</p>
          <form className="password-gate-form" onSubmit={handleSubmit}>
            <label className="field-label" htmlFor="site-password">
              Password
            </label>
            <input
              id="site-password"
              className="field-input"
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={busy}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error ? (
              <p className="error" role="alert">
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={busy || !password.trim()}
            >
              {busy ? 'Checking…' : 'Continue'}
            </button>
          </form>
        </main>
      </div>
    )
  }

  return children
}
