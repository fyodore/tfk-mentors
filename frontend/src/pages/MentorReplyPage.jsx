import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { fetchMentorEmailReply, putMentorEmailReply } from '../api'
import { Modal } from '../components/Modal'
import { formatPracticeWhen } from '../datetime.js'

const AT_PRACTICE = 'At Practice'
const REMOTE = 'Remote'
const ATTENDING = new Set(['attending', 'first_half', 'second_half'])
const SUBMIT_SUCCESS_AT_PRACTICE =
  'Thank you for taking the time to indicate which practices you can attend!'
const SUBMIT_SUCCESS_REMOTE =
  'Thank you for taking the time to indicate you can read and selecting any practices you can attend!'
const PARTIAL_MONTH_NOTE =
  'This email may not include a full month of practices. Please remember what ' +
  'you selected when you receive the next reply request.'

/** @typedef {{ id: number, date: string, nyrr_race: string, full_practice: boolean, season_id: number, attendance?: string|null, pace?: string }} PracticeReplyRow */

function formatPaceLabel(pace) {
  const trimmed = pace?.trim()
  if (!trimmed) return ''
  if (/min\/mile/i.test(trimmed)) return trimmed
  return `${trimmed} min/mile`
}

function isAttending(attendance) {
  return ATTENDING.has(attendance ?? '')
}

/** @param {PracticeReplyRow[]} practices */
function initialAttendanceMap(practices) {
  /** @type {Record<number, string>} */
  const m = {}
  for (const p of practices) {
    m[p.id] = p.attendance || 'not_attending'
  }
  return m
}

/** @param {PracticeReplyRow[]} practices */
function initialPaceMap(practices, defaultPace) {
  /** @type {Record<number, string>} */
  const m = {}
  for (const p of practices) {
    m[p.id] = p.pace?.trim() || defaultPace || ''
  }
  return m
}

function resolveToken(pathToken, searchParams) {
  const fromPath = typeof pathToken === 'string' ? pathToken.trim() : ''
  if (fromPath) return fromPath
  return (searchParams.get('token') ?? '').trim()
}

export default function MentorReplyPage() {
  const { token: pathToken } = useParams()
  const [searchParams] = useSearchParams()
  const rawToken = resolveToken(pathToken, searchParams)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mentor, setMentor] = useState(null)
  const [seasonYear, setSeasonYear] = useState(null)
  const [assignedPace, setAssignedPace] = useState('')
  /** @type {PracticeReplyRow[]} */
  const [practices, setPractices] = useState([])
  /** @type {string[]} */
  const [paceChoices, setPaceChoices] = useState([])
  const [showsPartialMonth, setShowsPartialMonth] = useState(false)
  const [emailReceivedConfirmed, setEmailReceivedConfirmed] = useState(false)
  /** @type {Record<number, string>} */
  const [attendanceByPractice, setAttendanceByPractice] = useState({})
  /** @type {Record<number, string>} */
  const [paceByPractice, setPaceByPractice] = useState({})
  const [busy, setBusy] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      if (!rawToken) {
        if (!cancelled) {
          setLoading(false)
          setError('Missing link token.')
        }
        return
      }
      setLoading(true)
      setError(null)
      setSubmitted(false)
      setConfirmOpen(false)
      try {
        const data = await fetchMentorEmailReply(rawToken)
        if (cancelled) return
        const m = data.mentor ?? null
        setMentor(m)
        setSeasonYear(data.season_year ?? null)
        setAssignedPace(data.assigned_pace ?? data.mentor?.pace ?? '')
        const plist = Array.isArray(data.practices) ? data.practices : []
        setPractices(plist)
        setPaceChoices(
          Array.isArray(data.pace_choices) ? data.pace_choices : []
        )
        setShowsPartialMonth(Boolean(data.shows_partial_month))
        setEmailReceivedConfirmed(Boolean(data.email_received_confirmed))
        const defaultPace = m?.pace ?? ''
        setAttendanceByPractice(initialAttendanceMap(plist))
        setPaceByPractice(initialPaceMap(plist, defaultPace))
        setSubmitted(plist.some((p) => p.attendance != null))
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setMentor(null)
          setPractices([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [rawToken])

  const isAtPractice = mentor?.type === AT_PRACTICE
  const isRemote = mentor?.type === REMOTE

  const introMessage = useMemo(() => {
    if (!mentor) return ''
    if (isAtPractice) {
      return 'Please select the practices you can attend.'
    }
    if (isRemote) {
      return (
        'As a non practice mentor please confirm that you received the email. ' +
        'If you would like to attend a practice please select which practice and pace below.'
      )
    }
    return ''
  }, [mentor, isAtPractice, isRemote])

  function setAttendance(practiceId, attendance) {
    setAttendanceByPractice((prev) => ({ ...prev, [practiceId]: attendance }))
    if (!isAttending(attendance)) {
      setPaceByPractice((prev) => ({ ...prev, [practiceId]: '' }))
    } else if (isRemote && !paceByPractice[practiceId]) {
      setPaceByPractice((prev) => ({
        ...prev,
        [practiceId]: mentor?.pace ?? paceChoices[0] ?? '',
      }))
    }
  }

  function setPace(practiceId, pace) {
    setPaceByPractice((prev) => ({ ...prev, [practiceId]: pace }))
  }

  function validateBeforeSubmit() {
    if (isRemote && !emailReceivedConfirmed) {
      return 'Please confirm that you received the email.'
    }
    if (isRemote) {
      for (const p of practices) {
        if (
          isAttending(attendanceByPractice[p.id]) &&
          !(paceByPractice[p.id] ?? '').trim()
        ) {
          return 'Select a pace for each practice you plan to attend.'
        }
      }
    }
    return null
  }

  async function submitReply() {
    if (!rawToken) return
    setBusy(true)
    setError(null)
    try {
      const replies = practices.map((p) => {
        const attendance = attendanceByPractice[p.id] ?? 'not_attending'
        const pace = isAttending(attendance) ? paceByPractice[p.id] ?? '' : ''
        return { practice: p.id, attendance, pace }
      })
      await putMentorEmailReply(rawToken, {
        replies,
        ...(isRemote ? { email_received_confirmed: true } : {}),
      })
      setSubmitted(true)
      setConfirmOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!rawToken || submitted) return
    const validationError = validateBeforeSubmit()
    if (validationError) {
      setError(validationError)
      return
    }
    setError(null)
    setConfirmOpen(true)
  }

  function handleConfirmSubmit() {
    if (busy) return
    submitReply()
  }

  if (loading) {
    return (
      <main className="panel mentor-reply-panel">
        <p className="muted">Loading…</p>
      </main>
    )
  }

  if (!mentor) {
    return (
      <main className="panel mentor-reply-panel">
        <p className="error" role="alert">
          {error || 'This link is invalid or has expired.'}
        </p>
      </main>
    )
  }

  return (
    <>
      <header className="app-header">
        <h1>Mentor confirmation</h1>
      </header>

      <main className="panel mentor-reply-panel">
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {submitted ? (
          <p className="mentor-reply-success" role="status">
            {isRemote ? SUBMIT_SUCCESS_REMOTE : SUBMIT_SUCCESS_AT_PRACTICE}
          </p>
        ) : null}

            <p className="mentor-reply-greeting">
              Hello <strong>{mentor.first_name}</strong>
            </p>
            {seasonYear != null ? (
              <p className="mentor-reply-thanks">
                Thank you for mentoring for the{' '}
                <strong>{seasonYear}</strong> season.
              </p>
            ) : null}
            {(assignedPace || mentor.pace) ? (
              <p className="mentor-reply-pace-assigned">
                Your assigned pace group is{' '}
                <strong>{formatPaceLabel(assignedPace || mentor.pace)}</strong>.
              </p>
            ) : null}

            {practices.length === 0 ? (
              <p className="muted">
                No practices were attached to this message.
              </p>
            ) : submitted ? null : (
              <form className="mentor-reply-form" onSubmit={handleSubmit}>
                {introMessage ? (
                  <p className="mentor-reply-intro">{introMessage}</p>
                ) : null}

                {isRemote ? (
                  <label className="checkbox-label mentor-reply-email-confirm">
                    <input
                      type="checkbox"
                      checked={emailReceivedConfirmed}
                      disabled={busy}
                      onChange={(ev) =>
                        setEmailReceivedConfirmed(ev.target.checked)
                      }
                    />
                    I received the mentoring email
                  </label>
                ) : null}

                {isAtPractice && showsPartialMonth ? (
                  <p className="muted mentor-reply-partial-month">
                    {PARTIAL_MONTH_NOTE}
                  </p>
                ) : null}

                <ul className="practice-list mentor-reply-list">
                  {practices.map((p) => {
                    const attendance =
                      attendanceByPractice[p.id] ?? 'not_attending'
                    const attending = isAttending(attendance)
                    const showSplit =
                      isAtPractice &&
                      !p.full_practice &&
                      mentor.split_practice

                    return (
                      <li key={p.id} className="practice-row mentor-reply-row">
                        <div className="practice-row-main">
                          <span className="practice-date">
                            {formatPracticeWhen(p.date, p.nyrr_race)}
                          </span>
                          {!p.full_practice && isAtPractice ? (
                            <span className="muted">Split practice session</span>
                          ) : null}

                          {showSplit ? (
                            <fieldset className="mentor-reply-split-fieldset">
                              <legend className="muted">
                                Which half can you cover?
                              </legend>
                              <label className="radio-row">
                                <input
                                  type="radio"
                                  name={`half-${p.id}`}
                                  value="first_half"
                                  checked={attendance === 'first_half'}
                                  disabled={busy}
                                  onChange={() =>
                                    setAttendance(p.id, 'first_half')
                                  }
                                />
                                First half
                              </label>
                              <label className="radio-row">
                                <input
                                  type="radio"
                                  name={`half-${p.id}`}
                                  value="second_half"
                                  checked={attendance === 'second_half'}
                                  disabled={busy}
                                  onChange={() =>
                                    setAttendance(p.id, 'second_half')
                                  }
                                />
                                Second half
                              </label>
                              <label className="radio-row">
                                <input
                                  type="radio"
                                  name={`half-${p.id}`}
                                  value="not_attending"
                                  checked={attendance === 'not_attending'}
                                  disabled={busy}
                                  onChange={() =>
                                    setAttendance(p.id, 'not_attending')
                                  }
                                />
                                Not attending
                              </label>
                            </fieldset>
                          ) : (
                            <label className="checkbox-label mentor-reply-checkbox">
                              <input
                                type="checkbox"
                                checked={attending}
                                disabled={busy}
                                onChange={(ev) =>
                                  setAttendance(
                                    p.id,
                                    ev.target.checked
                                      ? 'attending'
                                      : 'not_attending'
                                  )
                                }
                              />
                              I can attend this practice
                            </label>
                          )}

                          {isRemote && attending ? (
                            <label className="mentor-reply-pace-label">
                              <span className="muted">Pace</span>
                              <select
                                className="mentor-reply-pace-select"
                                value={paceByPractice[p.id] ?? ''}
                                disabled={busy}
                                onChange={(ev) =>
                                  setPace(p.id, ev.target.value)
                                }
                              >
                                <option value="">Select pace…</option>
                                {(paceChoices.length
                                  ? paceChoices
                                  : [mentor.pace]
                                )
                                  .filter(Boolean)
                                  .map((pace) => (
                                    <option key={pace} value={pace}>
                                      {formatPaceLabel(pace)}
                                    </option>
                                  ))}
                              </select>
                            </label>
                          ) : null}
                        </div>
                      </li>
                    )
                  })}
                </ul>
                <div className="mentor-reply-actions">
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={busy || practices.length === 0}
                  >
                    {busy ? 'Submitting…' : 'Submit'}
                  </button>
                </div>
              </form>
            )}

        <Modal
          open={confirmOpen}
          title="Submit your response?"
          closeDisabled={busy}
          onClose={() => {
            if (!busy) setConfirmOpen(false)
          }}
          footer={
            <>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => setConfirmOpen(false)}
              >
                Go back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={handleConfirmSubmit}
              >
                {busy ? 'Submitting…' : 'Submit'}
              </button>
            </>
          }
        >
          <p>
            Once you submit, any updates to your availability will need to be
            sent to Ted.
          </p>
        </Modal>
      </main>
    </>
  )
}
