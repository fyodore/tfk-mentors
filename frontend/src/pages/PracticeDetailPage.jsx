import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  createCoachPracticeAssignment,
  deleteCoachPracticeAssignment,
  fetchCoachPracticeAssignments,
  fetchCoaches,
  fetchPractice,
  fetchPracticeMentorReplies,
  fetchSeasons,
} from '../api'

const ATTENDANCE_LABELS = {
  attending: 'Attending',
  first_half: 'First half',
  second_half: 'Second half',
}

function formatAttendanceLabel(attendance) {
  return ATTENDANCE_LABELS[attendance] ?? attendance
}

function formatPaceLabel(pace) {
  const trimmed = pace?.trim()
  if (!trimmed) return ''
  if (/min\/mile/i.test(trimmed)) return trimmed
  return `${trimmed} min/mile`
}

function byName(a, b) {
  const ln = (a.last_name || '').localeCompare(b.last_name || '')
  if (ln !== 0) return ln
  return (a.first_name || '').localeCompare(b.first_name || '')
}

export default function PracticeDetailPage() {
  const { id } = useParams()
  const practiceId = Number.parseInt(String(id), 10)

  const [practice, setPractice] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [coaches, setCoaches] = useState([])
  const [coachAssignments, setCoachAssignments] = useState([])
  const [mentorReplies, setMentorReplies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [coachIdToAdd, setCoachIdToAdd] = useState('')
  const [coachPaceToAdd, setCoachPaceToAdd] = useState('8-9')
  const [saving, setSaving] = useState(false)

  const seasonById = useMemo(() => {
    const m = new Map()
    for (const s of seasons) m.set(s.id, s)
    return m
  }, [seasons])

  const coachById = useMemo(() => {
    const m = new Map()
    for (const c of coaches) m.set(c.id, c)
    return m
  }, [coaches])

  async function loadAll() {
    if (Number.isNaN(practiceId)) {
      setError('Invalid practice id.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [p, sList, cList, caList, replyList] = await Promise.all([
        fetchPractice(practiceId),
        fetchSeasons(),
        fetchCoaches(),
        fetchCoachPracticeAssignments(),
        fetchPracticeMentorReplies(practiceId),
      ])
      setPractice(p)
      setSeasons(sList)
      setCoaches([...cList].sort(byName))
      setCoachAssignments(caList.filter((a) => a.practice === practiceId))
      setMentorReplies(Array.isArray(replyList) ? replyList : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      if (Number.isNaN(practiceId)) {
        if (!cancelled) {
          setError('Invalid practice id.')
          setLoading(false)
        }
        return
      }
      setLoading(true)
      setError(null)
      try {
        const [p, sList, cList, caList, replyList] = await Promise.all([
          fetchPractice(practiceId),
          fetchSeasons(),
          fetchCoaches(),
          fetchCoachPracticeAssignments(),
          fetchPracticeMentorReplies(practiceId),
        ])
        if (!cancelled) {
          setPractice(p)
          setSeasons(sList)
          setCoaches([...cList].sort(byName))
          setCoachAssignments(caList.filter((a) => a.practice === practiceId))
          setMentorReplies(Array.isArray(replyList) ? replyList : [])
        }
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
  }, [practiceId])

  const assignedCoachIds = useMemo(
    () => new Set(coachAssignments.map((a) => a.coach)),
    [coachAssignments]
  )

  const practiceSeasonId = practice?.season

  const availableCoaches = useMemo(() => {
    if (!practiceSeasonId) return []
    return coaches.filter(
      (c) =>
        Array.isArray(c.seasons) &&
        c.seasons.includes(practiceSeasonId) &&
        !assignedCoachIds.has(c.id)
    )
  }, [coaches, practiceSeasonId, assignedCoachIds])

  async function handleAddCoach(e) {
    e.preventDefault()
    const coach = Number.parseInt(coachIdToAdd, 10)
    if (Number.isNaN(coach)) return
    setSaving(true)
    setError(null)
    try {
      await createCoachPracticeAssignment({
        coach,
        practice: practiceId,
        pace: coachPaceToAdd,
      })
      setCoachIdToAdd('')
      setCoachPaceToAdd('8-9')
      await loadAll()
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : String(e2))
    } finally {
      setSaving(false)
    }
  }

  async function handleRemoveCoach(assignmentId) {
    setSaving(true)
    setError(null)
    try {
      await deleteCoachPracticeAssignment(assignmentId)
      await loadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1>Practice View</h1>
        <p className="tagline">
          <Link to="/" className="nav-back">Home</Link>
          <span aria-hidden> · </span>
          <Link to="/mentors" className="nav-back">Mentors</Link>
          <span aria-hidden> · </span>
          <Link to="/practices" className="nav-back">Practices</Link>
          <span aria-hidden> · </span>
          <Link to="/emails" className="nav-back">Emails</Link>
        </p>
      </header>

      <main className="panel">
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {!loading && practice && (
          <>
            <p className="muted">
              {new Date(practice.date).toLocaleString(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
              {' · '}
              Season {seasonById.get(practice.season)?.year ?? practice.season}
            </p>

            <h2>Mentors + Pace Group</h2>
            <p className="muted practice-detail-hint">
              Mentors who confirmed they can attend this practice via email
              reply.
            </p>
            <ul className="practice-list">
              {mentorReplies.map((r) => (
                <li key={r.id} className="practice-row">
                  <div className="practice-row-main">
                    <span className="practice-date">
                      {r.first_name} {r.last_name}
                    </span>
                    <span className="muted">
                      {formatAttendanceLabel(r.attendance)}
                      {r.pace ? ` · Pace group ${formatPaceLabel(r.pace)}` : ''}
                    </span>
                  </div>
                </li>
              ))}
              {mentorReplies.length === 0 && (
                <li className="muted">No mentors assigned yet.</li>
              )}
            </ul>

            <h2>Coaches + Pace</h2>
            <ul className="practice-list">
              {coachAssignments.map((a) => {
                const c = coachById.get(a.coach)
                return (
                  <li key={a.id} className="practice-row">
                    <div className="practice-row-main">
                      <span className="practice-date">
                        {c ? `${c.first_name} ${c.last_name}` : `Coach #${a.coach}`}
                      </span>
                      <span className="muted">Pace {a.pace}</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-text btn-text-danger"
                      disabled={saving}
                      onClick={() => handleRemoveCoach(a.id)}
                    >
                      Remove
                    </button>
                  </li>
                )
              })}
              {coachAssignments.length === 0 && <li className="muted">No coaches assigned.</li>}
            </ul>

            <form className="modal-form-stack" onSubmit={handleAddCoach}>
              <label className="field-label" htmlFor="add-coach">Add coach</label>
              <select
                id="add-coach"
                className="field-input field-select"
                value={coachIdToAdd}
                onChange={(e) => setCoachIdToAdd(e.target.value)}
                required
              >
                <option value="" disabled>Select coach</option>
                {availableCoaches.map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.first_name} {c.last_name}
                  </option>
                ))}
              </select>
              <label className="field-label" htmlFor="add-coach-pace">Pace</label>
              <select
                id="add-coach-pace"
                className="field-input field-select"
                value={coachPaceToAdd}
                onChange={(e) => setCoachPaceToAdd(e.target.value)}
                required
              >
                <option value="8-9">8-9</option>
                <option value="9-10">9-10</option>
                <option value="10-11">10-11</option>
                <option value="11-12">11-12</option>
                <option value="12-13">12-13</option>
                <option value="13+">13+</option>
              </select>
              <button type="submit" className="btn btn-primary" disabled={saving || availableCoaches.length === 0}>
                Add Coach
              </button>
            </form>
          </>
        )}
      </main>
    </>
  )
}
