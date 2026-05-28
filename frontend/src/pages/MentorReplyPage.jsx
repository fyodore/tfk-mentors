import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { fetchMentorEmailReply, putMentorEmailReply } from '../api'

const AT_PRACTICE = 'At Practice'

/** @typedef {{ id: number, date: string, nyrr_race: string, full_practice: boolean, season_id: number, attendance?: string|null }} PracticeReplyRow */

function formatPracticeWhen(iso, nyrrRace) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const when = d.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
  const race = nyrrRace?.trim()
  return race ? `${when} · NYRR: ${race}` : when
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

export default function MentorReplyPage() {
  const { token } = useParams()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mentor, setMentor] = useState(null)
  const [scheduledSendAt, setScheduledSendAt] = useState('')
  /** @type {PracticeReplyRow[]} */
  const [practices, setPractices] = useState([])
  const [canSubmit, setCanSubmit] = useState(false)
  /** @type {Record<number, string>} */
  const [attendanceByPractice, setAttendanceByPractice] = useState({})
  const [busy, setBusy] = useState(false)
  const [saveOk, setSaveOk] = useState(null)

  const rawToken = typeof token === 'string' ? token : ''

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      if (!rawToken.trim()) {
        if (!cancelled) {
          setLoading(false)
          setError('Missing link token.')
        }
        return
      }
      setLoading(true)
      setError(null)
      setSaveOk(null)
      try {
        const data = await fetchMentorEmailReply(rawToken)
        if (cancelled) return
        setMentor(data.mentor)
        setScheduledSendAt(data.scheduled_send_at ?? '')
        const plist = Array.isArray(data.practices) ? data.practices : []
        setPractices(plist)
        setCanSubmit(Boolean(data.can_submit))
        setAttendanceByPractice(initialAttendanceMap(plist))
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

  const mentorLabel = useMemo(() => {
    if (!mentor) return ''
    return `${mentor.first_name} ${mentor.last_name}`.trim()
  }, [mentor])

  function setAttendance(practiceId, attendance) {
    setAttendanceByPractice((prev) => ({ ...prev, [practiceId]: attendance }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit || !rawToken.trim()) return
    setBusy(true)
    setError(null)
    setSaveOk(null)
    try {
      const replies = practices.map((p) => ({
        practice: p.id,
        attendance: attendanceByPractice[p.id] ?? 'not_attending',
      }))
      await putMentorEmailReply(rawToken, replies)
      setSaveOk('Your availability was saved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1>Practice availability</h1>
        <p className="tagline">
          <Link to="/" className="nav-back">
            Site home
          </Link>
        </p>
      </header>

      <main className="panel mentor-reply-panel">
        {loading && <p className="muted">Loading…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {saveOk && (
          <p className="muted" role="status">
            {saveOk}
          </p>
        )}

        {!loading && mentor && (
          <>
            <p>
              <strong>{mentorLabel}</strong>
              {mentor.type !== AT_PRACTICE ? (
                <span className="muted"> · {mentor.type}</span>
              ) : null}
            </p>
            {scheduledSendAt ? (
              <p className="muted">
                Related message scheduled{' '}
                {new Date(scheduledSendAt).toLocaleString(undefined, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}
              </p>
            ) : null}

            {!canSubmit ? (
              <p className="muted">
                This scheduling form is only for mentors marked{' '}
                <strong>At Practice</strong>. If you believe this is a mistake,
                contact your coordinator.
              </p>
            ) : practices.length === 0 ? (
              <p className="muted">
                No practices were attached to this message.
              </p>
            ) : (
              <form className="mentor-reply-form" onSubmit={handleSubmit}>
                <p className="muted mentor-reply-intro">
                  For each practice below, indicate whether you can attend. Split
                  practices may ask which half you can cover when your mentor profile
                  uses split practice.
                </p>
                <ul className="practice-list mentor-reply-list">
                  {practices.map((p) => (
                    <li key={p.id} className="practice-row mentor-reply-row">
                      <div className="practice-row-main">
                        <span className="practice-date">
                          {formatPracticeWhen(p.date, p.nyrr_race)}
                        </span>
                        {!p.full_practice ? (
                          <span className="muted">Split practice session</span>
                        ) : (
                          <span className="muted">Full practice</span>
                        )}
                        {p.full_practice || !mentor.split_practice ? (
                          <label className="checkbox-label mentor-reply-checkbox">
                            <input
                              type="checkbox"
                              checked={
                                (attendanceByPractice[p.id] ?? 'not_attending') ===
                                'attending'
                              }
                              disabled={busy}
                              onChange={(ev) =>
                                setAttendance(
                                  p.id,
                                  ev.target.checked ? 'attending' : 'not_attending'
                                )
                              }
                            />
                            I can attend this practice
                          </label>
                        ) : (
                          <fieldset className="mentor-reply-split-fieldset">
                            <legend className="muted">
                              Which half can you cover?
                            </legend>
                            <label className="radio-row">
                              <input
                                type="radio"
                                name={`half-${p.id}`}
                                value="first_half"
                                checked={
                                  attendanceByPractice[p.id] === 'first_half'
                                }
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
                                checked={
                                  attendanceByPractice[p.id] === 'second_half'
                                }
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
                                checked={
                                  attendanceByPractice[p.id] === 'not_attending'
                                }
                                disabled={busy}
                                onChange={() =>
                                  setAttendance(p.id, 'not_attending')
                                }
                              />
                              Not attending
                            </label>
                          </fieldset>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
                <div className="mentor-reply-actions">
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={busy || practices.length === 0}
                  >
                    {busy ? 'Saving…' : 'Save availability'}
                  </button>
                </div>
              </form>
            )}
          </>
        )}
      </main>
    </>
  )
}
