import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  createCoachPracticeAssignment,
  createPracticeMentorReply,
  deleteCoachPracticeAssignment,
  deletePracticeMentorReply,
  fetchCoachPracticeAssignments,
  fetchCoaches,
  fetchMentors,
  fetchPractice,
  fetchSeasons,
  makePracticeMentorAvailable,
} from '../api'
import { AppHeader } from '../components/AppHeader.jsx'
import { formatDateTime } from '../datetime.js'
import { sortByPaceThenName } from '../paceHelpers.js'

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
  const [mentorReplies, setMentorReplies] = useState([])
  const [availableMentorReplies, setAvailableMentorReplies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [coachIdsToAdd, setCoachIdsToAdd] = useState([])
  const [coachPaceToAdd, setCoachPaceToAdd] = useState('')
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
      const [p, sList, cList, mList, caList] = await Promise.all([
        fetchPractice(practiceId),
        fetchSeasons(),
        fetchCoaches(),
        fetchMentors(),
        fetchCoachPracticeAssignments(),
      ])
      setPractice(p)
      setSeasons(sList)
      setCoaches([...cList].sort(byName))
      setMentors([...mList].sort(byName))
      setCoachAssignments(caList.filter((a) => a.practice === practiceId))
      setMentorReplies(
        Array.isArray(p.mentor_replies) ? p.mentor_replies : []
      )
      setAvailableMentorReplies(
        Array.isArray(p.available_mentor_replies) ? p.available_mentor_replies : []
      )
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
        const [p, sList, cList, mList, caList] = await Promise.all([
          fetchPractice(practiceId),
          fetchSeasons(),
          fetchCoaches(),
          fetchMentors(),
          fetchCoachPracticeAssignments(),
        ])
        if (!cancelled) {
          setPractice(p)
          setSeasons(sList)
          setCoaches([...cList].sort(byName))
          setMentors([...mList].sort(byName))
          setCoachAssignments(caList.filter((a) => a.practice === practiceId))
          setMentorReplies(
            Array.isArray(p.mentor_replies) ? p.mentor_replies : []
          )
          setAvailableMentorReplies(
            Array.isArray(p.available_mentor_replies)
              ? p.available_mentor_replies
              : []
          )
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
    () =>
      new Set([
        ...mentorReplies.map((r) => r.mentor_id),
        ...availableMentorReplies.map((r) => r.mentor_id),
      ]),
    [mentorReplies, availableMentorReplies]
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
    return sortByPaceThenName(
      mentors.filter(
        (m) =>
          Array.isArray(m.seasons) &&
          m.seasons.includes(practiceSeasonId) &&
          !assignedMentorIds.has(m.id)
      )
    )
  }, [mentors, practiceSeasonId, assignedMentorIds])

  const assignedMentorReplies = useMemo(
    () => sortByPaceThenName(mentorReplies),
    [mentorReplies]
  )

  const sortedAvailableMentorReplies = useMemo(
    () => sortByPaceThenName(availableMentorReplies),
    [availableMentorReplies]
  )

  function renderMentorReplyRow(r, isAvailable) {
    const m = mentorById.get(r.mentor_id)
    return (
      <li
        key={r.id}
        className={
          isAvailable ? 'practice-row practice-row-available' : 'practice-row'
        }
      >
        <div className="practice-row-main">
          <span className="practice-date">
            {r.first_name && r.last_name
              ? `${r.first_name} ${r.last_name}`
              : m
                ? `${m.first_name} ${m.last_name}`
                : `Mentor #${r.mentor_id}`}
          </span>
          <span className="muted">Pace group {r.pace}</span>
        </div>
        <div className="practice-row-actions">
          {isAvailable ? (
            <button
              type="button"
              className="btn btn-text"
              disabled={saving}
              onClick={() => handleAddMentorToPractice(r.mentor_id, r.pace)}
            >
              Add to Practice
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-text"
              disabled={saving}
              onClick={() => handleMakeMentorAvailable(r.mentor_id)}
            >
              Make available
            </button>
          )}
          <button
            type="button"
            className="btn btn-text btn-text-danger"
            disabled={saving}
            onClick={() => handleRemoveMentor(r.mentor_id)}
          >
            Remove
          </button>
        </div>
      </li>
    )
  }

  async function handleAddCoach(e) {
    e.preventDefault()
    const coachIds = coachIdsToAdd
      .map((id) => Number.parseInt(String(id), 10))
      .filter((id) => !Number.isNaN(id))
    if (coachIds.length === 0) return
    setSaving(true)
    setError(null)
    try {
      await Promise.all(
        coachIds.map((coach) =>
          createCoachPracticeAssignment({
            coach,
            practice: practiceId,
            pace: coachPaceToAdd,
          })
        )
      )
      setCoachIdsToAdd([])
      setCoachPaceToAdd('')
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
    if (Number.isNaN(mentorId)) return
    setSaving(true)
    setError(null)
    try {
      await createPracticeMentorReply(practiceId, {
        mentor: mentorId,
        pace: mentorPaceToAdd,
      })
      setMentorIdToAdd('')
      setMentorPaceToAdd('8-9')
      await loadAll()
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : String(e2))
    } finally {
      setSaving(false)
    }
  }

  async function handleRemoveMentor(mentorId) {
    setSaving(true)
    setError(null)
    try {
      await deletePracticeMentorReply(practiceId, mentorId)
      await loadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleAddMentorToPractice(mentorId, pace) {
    setSaving(true)
    setError(null)
    try {
      await createPracticeMentorReply(practiceId, {
        mentor: mentorId,
        pace: pace || '8-9',
      })
      await loadAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleMakeMentorAvailable(mentorId) {
    setSaving(true)
    setError(null)
    try {
      await makePracticeMentorAvailable(practiceId, mentorId)
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
      <AppHeader title="Practice View" />

      <main className="panel">
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {!loading && practice && (
          <>
            <p className="muted">
              {formatDateTime(practice.date)}
              {' · '}
              Season {seasonById.get(practice.season)?.year ?? practice.season}
            </p>
            {practice.description?.trim() ? (
              <p className="practice-description">{practice.description.trim()}</p>
            ) : null}

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
                      <span className="muted">
                        {a.pace ? `Pace ${a.pace}` : 'No pace assigned'}
                      </span>
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
              <label className="field-label" htmlFor="add-coach">
                Add coaches
              </label>
              <select
                id="add-coach"
                className="field-input field-select email-mentor-multiselect"
                value={coachIdsToAdd}
                onChange={(e) =>
                  setCoachIdsToAdd(
                    Array.from(e.target.selectedOptions).map((o) => o.value)
                  )
                }
                multiple
                size={Math.min(Math.max(availableCoaches.length, 3), 8)}
              >
                {availableCoaches.map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.first_name} {c.last_name}
                  </option>
                ))}
              </select>
              <p className="muted">
                Hold Ctrl (Windows) or ⌘ (Mac) to select multiple coaches.
              </p>
              <label className="field-label" htmlFor="add-coach-pace">
                Pace <span className="muted">(optional)</span>
              </label>
              <select
                id="add-coach-pace"
                className="field-input field-select"
                value={coachPaceToAdd}
                onChange={(e) => setCoachPaceToAdd(e.target.value)}
              >
                <option value="">No pace</option>
                <option value="8-9">8-9</option>
                <option value="9-10">9-10</option>
                <option value="10-11">10-11</option>
                <option value="11-12">11-12</option>
                <option value="12-13">12-13</option>
                <option value="13+">13+</option>
              </select>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={
                  saving ||
                  availableCoaches.length === 0 ||
                  coachIdsToAdd.length === 0
                }
              >
                Add Coach{coachIdsToAdd.length > 1 ? 'es' : ''}
              </button>
            </form>

            <h2>Mentors + Pace Group</h2>
            <ul className="practice-list">
              {assignedMentorReplies.map((r) => renderMentorReplyRow(r, false))}
              {assignedMentorReplies.length === 0 &&
                sortedAvailableMentorReplies.length === 0 && (
                  <li className="muted">No mentors assigned.</li>
                )}
            </ul>

            {sortedAvailableMentorReplies.length > 0 && (
              <section
                className="practices-section practice-available-mentors-section"
                aria-labelledby="available-mentors-heading"
              >
                <h3
                  id="available-mentors-heading"
                  className="practices-section-heading"
                >
                  Available Mentors
                </h3>
                <ul className="practice-list">
                  {sortedAvailableMentorReplies.map((r) =>
                    renderMentorReplyRow(r, true)
                  )}
                </ul>
              </section>
            )}

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
