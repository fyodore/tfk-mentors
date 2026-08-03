import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import {
  ApiError,
  fetchUnderfilledPaceReply,
  putUnderfilledPaceReply,
} from '../api'
import type { UnderfilledPaceReplyPractice } from '../types.js'

export default function UnderfilledPaceReplyPage() {
  const { token: pathToken } = useParams()
  const [searchParams] = useSearchParams()
  const token = pathToken || searchParams.get('token') || ''

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [messages, setMessages] = useState<string[]>([])
  const [firstName, setFirstName] = useState('')
  const [pace, setPace] = useState('')
  const [practices, setPractices] = useState<UnderfilledPaceReplyPractice[]>(
    []
  )
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [unavailable, setUnavailable] = useState(false)
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
        const data = await fetchUnderfilledPaceReply(token)
        if (cancelled) return
        setFirstName(data.first_name || '')
        setPace(data.pace || '')
        if (data.completed) {
          setMessages(
            Array.isArray(data.messages) && data.messages.length > 0
              ? data.messages
              : [data.detail || 'Thank you!']
          )
          setPractices([])
          return
        }
        setPractices(Array.isArray(data.practices) ? data.practices : [])
      } catch (e: unknown) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : String(e))
        if (e instanceof ApiError && e.body && typeof e.body === 'object') {
          const body = e.body as { messages?: string[]; detail?: string }
          if (Array.isArray(body.messages) && body.messages.length > 0) {
            setMessages(body.messages)
          } else if (body.detail) {
            setMessages([body.detail])
          }
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [token])

  const canSubmit = useMemo(() => {
    if (unavailable) return true
    return selectedIds.length > 0
  }, [unavailable, selectedIds])

  function togglePractice(practiceId: number, selectable: boolean) {
    if (!selectable || unavailable) return
    setSelectedIds((prev) =>
      prev.includes(practiceId)
        ? prev.filter((id) => id !== practiceId)
        : [...prev, practiceId]
    )
  }

  function toggleUnavailable() {
    setUnavailable((prev) => {
      const next = !prev
      if (next) setSelectedIds([])
      return next
    })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError('')
    try {
      const result = await putUnderfilledPaceReply(
        token,
        unavailable
          ? { unavailable: true }
          : { practice_ids: selectedIds }
      )
      setMessages(
        Array.isArray(result.messages) && result.messages.length > 0
          ? result.messages
          : [result.detail || 'Thank you!']
      )
      setPractices([])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const done = messages.length > 0

  return (
    <main className="panel underfilled-pace-reply-panel">
      <h1>TFK Mentors</h1>
      <h2>Practices needing mentors in your pace group</h2>

      {loading && <p className="muted">Loading…</p>}

      {!loading && done && (
        <div className="underfilled-pace-reply-done" role="status">
          {messages.map((message) => (
            <p key={message} className="success">
              {message}
            </p>
          ))}
        </div>
      )}

      {!loading && !done && error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {!loading && !done && !error && (
        <form className="underfilled-pace-reply-form" onSubmit={handleSubmit}>
          <p className="mentor-reply-greeting">
            {firstName ? `Hi ${firstName},` : 'Hi,'}
            {pace ? ` your pace group is ${pace}.` : ''}
          </p>
          <p>
            Select any practices you can attend so we can get closer to 3
            mentors in your pace group.
          </p>

          <ul className="practice-list underfilled-pace-reply-list">
            {practices.map((practice) => {
              const selectable = practice.selectable !== false
              const checked = selectedIds.includes(practice.practice_id)
              const filled = practice.slots_remaining <= 0
              return (
                <li
                  key={practice.practice_id}
                  className={`practice-row underfilled-pace-reply-row${
                    filled ? ' underfilled-pace-reply-row-filled' : ''
                  }`}
                >
                  <label
                    className={`underfilled-pace-reply-option${
                      !selectable || unavailable
                        ? ' underfilled-pace-reply-option-disabled'
                        : ''
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!selectable || unavailable || submitting}
                      onChange={() =>
                        togglePractice(practice.practice_id, selectable)
                      }
                    />
                    <span className="underfilled-pace-reply-option-text">
                      <span className="practice-date">{practice.label}</span>
                      <span className="muted">
                        {filled
                          ? 'Already filled (0 slots needed)'
                          : `I can attend this practice (${practice.slots_remaining} slot${
                              practice.slots_remaining === 1 ? '' : 's'
                            } needed)`}
                      </span>
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>

          <label className="underfilled-pace-reply-unavailable">
            <input
              type="checkbox"
              checked={unavailable}
              disabled={submitting}
              onChange={toggleUnavailable}
            />
            <span>Unfortunately I am not available.</span>
          </label>

          <div className="modal-actions mentor-reply-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !canSubmit}
            >
              {submitting ? 'Submitting…' : 'Submit'}
            </button>
          </div>
        </form>
      )}
    </main>
  )
}
