import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  fetchPublicMentorSwapRequest,
  rejectPublicMentorSwapRequest,
} from '../api'
import { formatMentorDirectoryPracticeDate } from '../datetime.js'

function personName(row) {
  return `${row?.first_name ?? ''} ${row?.last_name ?? ''}`.trim() || '—'
}

export default function MentorSwapRejectPage() {
  const { token } = useParams()
  const [loading, setLoading] = useState(true)
  const [requestRow, setRequestRow] = useState(null)
  const [error, setError] = useState(null)
  const [comments, setComments] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [doneMessage, setDoneMessage] = useState(null)

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
        const row = await fetchPublicMentorSwapRequest(token)
        if (cancelled) return
        setRequestRow(row)
        if (row.status === 'rejected') {
          setDoneMessage('This swap request was already rejected.')
        } else if (row.status === 'approved') {
          setError('This swap request was already approved.')
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [token])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!token || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const result = await rejectPublicMentorSwapRequest(token, comments)
      setDoneMessage(result.message || 'Your rejection was submitted. Thank you.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="panel mentor-swap-public-panel">
      <h1>Reject mentor swap</h1>
      {loading ? <p className="muted">Loading…</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && requestRow && !doneMessage && requestRow.status === 'pending' ? (
        <>
          <p>
            Practice:{' '}
            {requestRow.practice_date
              ? formatMentorDirectoryPracticeDate(requestRow.practice_date)
              : '—'}
            {requestRow.nyrr_race ? ` · ${requestRow.nyrr_race}` : ''}
          </p>
          <p>Original mentor: {personName(requestRow.outgoing_mentor)}</p>
          <p>Requested replacement: {personName(requestRow.incoming_mentor)}</p>

          <form className="mentor-swap-reject-form" onSubmit={handleSubmit}>
            <label className="field-label" htmlFor="swap-reject-comments">
              Comments
            </label>
            <textarea
              id="swap-reject-comments"
              className="field-input"
              rows={5}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Optional comments about why you are rejecting this swap"
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
            >
              {submitting ? 'Submitting…' : 'Reject Swap'}
            </button>
          </form>
        </>
      ) : null}

      {doneMessage ? (
        <p className="mentor-swap-public-success" role="status">
          {doneMessage}
        </p>
      ) : null}
    </main>
  )
}
