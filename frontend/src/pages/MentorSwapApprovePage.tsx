import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { approvePublicMentorSwapRequest } from '../api'

export default function MentorSwapApprovePage() {
  const { token } = useParams()
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (!token) {
      setError('Missing swap token.')
      setLoading(false)
      return undefined
    }

    Promise.resolve().then(async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await approvePublicMentorSwapRequest(token)
        if (cancelled) return
        setMessage(
          result.message ||
            'The mentor swap was successful.  You both should receive an email with a confirmation.'
        )
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <main className="panel mentor-swap-public-panel">
      <h1>Mentor swap</h1>
      {loading ? <p className="muted">Approving swap…</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {!loading && !error ? (
        <p className="mentor-swap-public-success" role="status">
          {message}
        </p>
      ) : null}
    </main>
  )
}
