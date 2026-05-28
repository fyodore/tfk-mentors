import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  createCoachPracticeAssignment,
  createMentorPracticeAssignment,
  deleteCoachPracticeAssignment,
  deleteMentorPracticeAssignment,
  fetchCoachPracticeAssignments,
  fetchCoaches,
  fetchMentorPracticeAssignments,
  fetchMentors,
  fetchPractice,
  fetchSeasons,
  patchPractice,
} from '../api'

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
  const [mentors, setMentors] = useState([])
  const [coachAssignments, setCoachAssignments] = useState([])
  const [mentorAssignments, setMentorAssignments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [coachIdToAdd, setCoachIdToAdd] = useState('')
  const [coachPaceToAdd, setCoachPaceToAdd] = useState('8-9')
  const [mentorIdToAdd, setMentorIdToAdd] = useState('')
  const [mentorPaceToAdd, setMentorPaceToAdd] = useState('8-9')
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

  const mentorById = useMemo(() => {
    const m = new Map()
    for (const mtr of mentors) m.set(mtr.id, mtr)
    return m
  }, [mentors])

  async function loadAll() {
    if (Number.isNaN(practiceId)) {
      setError('Invalid practice id.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [p, sList, cList, mList, caList, maList] = await Promise.all([
        fetchPractice(practiceId),
        fetchSeasons(),
        fetchCoaches(),
        fetchMentors(),
        fetchCoachPracticeAssignments(),
        fetchMentorPracticeAssignments(),
      ])
      setPractice(p)
      setSeasons(sList)
      setCoaches([...cList].sort(byName))
      setMentors([...mList].sort(byName))
      setCoachAssignments(caList.filter((a) => a.practice === practiceId))
      setMentorAssignments(maList.filter((a) => a.practice === practiceId))
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
        const [p, sList, cList, mList, caList, maList] = await Promise.all([
          fetchPractice(practiceId),
          fetchSeasons(),
          fetchCoaches(),
          fetchMentors(),
          fetchCoachPracticeAssignments(),
          fetchMentorPracticeAssignments(),
        ])
        if (!cancelled) {
          setPractice(p)
          setSeasons(sList)
          setCoaches([...cList].sort(byName))
          setMentors([...mList].sort(byName))
          setCoachAssignments(caList.filter((a) => a.practice === practiceId))
          setMentorAssignments(maList.filter((a) => a.practice === practiceId))
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

  const assignedMentorIds = useMemo(
    () => new Set(mentorAssignments.map((a) => a.mentor)),
    [mentorAssignments]
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

  const availableMentors = useMemo(() => {
    if (!practiceSeasonId) return []
    return mentors.filter(
      (m) =>
        Array.isArray(m.seasons) &&
        m.seasons.includes(practiceSeasonId) &&
        !assignedMentorIds.has(m.id)
    )
  }, [mentors, practiceSeasonId, assignedMentorIds])

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

  async function handleAddMentor(e) {
    e.preventDefault()
    const mentorId = Number.parseInt(mentorIdToAdd, 10)
    if (Number.isNaN(mentorId) || !practice) return
    setSaving(true)
    setError(null)
    try {
      await createMentorPracticeAssignment({
        mentor: mentorId,
        practice: practiceId,
        pace: mentorPaceToAdd,
      })
      const mentorsNext = [...(practice.mentors || []), mentorId]
      const updated = await patchPractice(practiceId, { mentors: mentorsNext })
      setPractice(updated)
      setMentorIdToAdd('')
      setMentorPaceToAdd('8-9')
      await loadAll()
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : String(e2))
    } finally {
      setSaving(false)
    }
  }

  async function handleRemoveMentor(assignmentId, mentorId) {
    if (!practice) return
    setSaving(true)
    setError(null)
    try {
      await deleteMentorPracticeAssignment(assignmentId)
      const mentorsNext = (practice.mentors || []).filter((m) => m !== mentorId)
      const updated = await patchPractice(practiceId, { mentors: mentorsNext })
      setPractice(updated)
      await loadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  function handleMentorSelectChange(nextId) {
    setMentorIdToAdd(nextId)
    const mentorId = Number.parseInt(nextId, 10)
    if (Number.isNaN(mentorId)) return
    const mentor = mentorById.get(mentorId)
    if (mentor?.pace) setMentorPaceToAdd(mentor.pace)
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

            <h2>Mentors + Pace Group</h2>
            <ul className="practice-list">
              {mentorAssignments.map((a) => {
                const m = mentorById.get(a.mentor)
                return (
                  <li key={a.id} className="practice-row">
                    <div className="practice-row-main">
                      <span className="practice-date">
                        {m ? `${m.first_name} ${m.last_name}` : `Mentor #${a.mentor}`}
                      </span>
                      <span className="muted">Pace group {a.pace}</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-text btn-text-danger"
                      disabled={saving}
                      onClick={() => handleRemoveMentor(a.id, a.mentor)}
                    >
                      Remove
                    </button>
                  </li>
                )
              })}
              {mentorAssignments.length === 0 && <li className="muted">No mentors assigned.</li>}
            </ul>

            <form className="modal-form-stack" onSubmit={handleAddMentor}>
              <label className="field-label" htmlFor="add-mentor">Add mentor</label>
              <select
                id="add-mentor"
                className="field-input field-select"
                value={mentorIdToAdd}
                onChange={(e) => handleMentorSelectChange(e.target.value)}
                required
              >
                <option value="" disabled>Select mentor</option>
                {availableMentors.map((m) => (
                  <option key={m.id} value={String(m.id)}>
                    {m.first_name} {m.last_name} ({m.pace})
                  </option>
                ))}
              </select>
              <label className="field-label" htmlFor="add-mentor-pace">Pace group</label>
              <select
                id="add-mentor-pace"
                className="field-input field-select"
                value={mentorPaceToAdd}
                onChange={(e) => setMentorPaceToAdd(e.target.value)}
                required
              >
                <option value="8-9">8-9</option>
                <option value="9-10">9-10</option>
                <option value="10-11">10-11</option>
                <option value="11-12">11-12</option>
                <option value="12-13">12-13</option>
                <option value="13+">13+</option>
              </select>
              <button type="submit" className="btn btn-primary" disabled={saving || availableMentors.length === 0}>
                Add Mentor
              </button>
            </form>
          </>
        )}
      </main>
    </>
  )
}

