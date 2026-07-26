import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import {
  fetchMentorCellPhoneUpdate,
  putMentorCellPhoneUpdate,
} from '../api'

export default function MentorCellPhonePage() {
  const { token: pathToken } = useParams()
  const [searchParams] = useSearchParams()
  const token = pathToken || searchParams.get('token') || ''

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [doneMessage, setDoneMessage] = useState('')
  const [firstName, setFirstName] = useState('')
  const [cellPhone, setCellPhone] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (!token) {
      setLoading(false)
      setError('This link is missing a token.')
      return undefined
    }
    Promise.resolve().then(async () => {
      setLoading(true)
      setError('')
      try {
        const data = await fetchMentorCellPhoneUpdate(token)
        if (cancelled) return
        setFirstName(data.first_name || '')
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : String(e))
        if (e?.status === 410) {
          setDoneMessage(e.message)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [token])

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const result = await putMentorCellPhoneUpdate(token, {
        cell_phone: cellPhone.trim(),
      })
      setDoneMessage(
        result.detail ||
          'Thank you! We have saved your cell phone number.'
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="panel mentor-cell-phone-panel">
      <h1>TFK Mentors</h1>
      <h2>Cell phone needed</h2>

      {loading && <p className="muted">Loading…</p>}

      {!loading && doneMessage && (
        <p className="success" role="status">
          {doneMessage}
        </p>
      )}

      {!loading && !doneMessage && error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {!loading && !doneMessage && !error && (
        <form className="mentor-cell-phone-form" onSubmit={handleSubmit}>
          <p>
            {firstName ? `Hi ${firstName}, ` : ''}
            coaches need a cell phone number for mentors attending practice.
            Please enter yours below.
          </p>
          <label className="field-label" htmlFor="mentor-cell-phone">
            Cell phone
          </label>
          <input
            id="mentor-cell-phone"
            className="field-input"
            type="tel"
            autoComplete="tel"
            value={cellPhone}
            onChange={(e) => setCellPhone(e.target.value)}
            required
            maxLength={20}
            disabled={submitting}
          />
          <div className="modal-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !cellPhone.trim()}
            >
              {submitting ? 'Saving…' : 'Submit'}
            </button>
          </div>
        </form>
      )}
    </main>
  )
}
