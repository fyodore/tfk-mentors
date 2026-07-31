import {
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  createCoachPracticeAssignment,
  createPracticeMentorReply,
  deleteCoachPracticeAssignment,
  deletePracticeMentorReply,
  fetchCoachPracticeAssignments,
  fetchCoaches,
  fetchMentors,
  fetchPractice,
  fetchPractices,
  fetchSeasons,
  makePracticeMentorAvailable,
  patchPracticeMentorPace,
  swapPracticeMentor,
} from '../api'
import { AppHeader } from '../components/AppHeader.tsx'
import { MentorPracticeHover } from '../components/MentorPracticeHover.tsx'
import { Modal } from '../components/Modal.tsx'
import { formatDateTime } from '../datetime.js'
import { PACE_GROUPS, sortByPaceThenName } from '../paceHelpers.js'
import { splitPracticesByUpcoming } from '../seasonHelpers.js'
import type {
  Coach,
  CoachPracticeAssignment,
  Mentor,
  Practice,
  PracticeMentorReply,
  Season,
} from '../types.js'

type NamedPerson = {
  first_name?: string | null
  last_name?: string | null
}

type SwapModalState = {
  mentorId: number
  mentorName: string
  pace: string
}

function byName(a: NamedPerson, b: NamedPerson) {
  const ln = (a.last_name || '').localeCompare(b.last_name || '')
  if (ln !== 0) return ln
  return (a.first_name || '').localeCompare(b.first_name || '')
}

function practiceSwitcherLabel(practice: Practice) {
  const dateLabel = practice.date ? formatDateTime(practice.date) : '—'
  const race = practice.nyrr_race?.trim()
  return race ? `${dateLabel} · ${race}` : dateLabel
}

export default function PracticeDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const practiceId = Number.parseInt(String(id), 10)

  const [practice, setPractice] = useState<Practice | null>(null)
  const [allPractices, setAllPractices] = useState<Practice[]>([])
  const [seasons, setSeasons] = useState<Season[]>([])
  const [coaches, setCoaches] = useState<Coach[]>([])
  const [mentors, setMentors] = useState<Mentor[]>([])
  const [coachAssignments, setCoachAssignments] = useState<
    CoachPracticeAssignment[]
  >([])
  const [mentorReplies, setMentorReplies] = useState<PracticeMentorReply[]>([])
  const [availableMentorReplies, setAvailableMentorReplies] = useState<
    PracticeMentorReply[]
  >([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [coachIdsToAdd, setCoachIdsToAdd] = useState<string[]>([])
  const [coachPaceToAdd, setCoachPaceToAdd] = useState('')
  const [mentorIdToAdd, setMentorIdToAdd] = useState('')
  const [mentorPaceToAdd, setMentorPaceToAdd] = useState('8-9')
  const [saving, setSaving] = useState(false)
  const [updatingMentorPaceId, setUpdatingMentorPaceId] = useState<
    number | null
  >(null)
  const [swapModal, setSwapModal] = useState<SwapModalState | null>(null)
  const [swapIncomingId, setSwapIncomingId] = useState('')
  const [swapError, setSwapError] = useState('')

  const seasonById = useMemo(() => {
    const m = new Map<number, Season>()
    for (const s of seasons) m.set(s.id, s)
    return m
  }, [seasons])

  const coachById = useMemo(() => {
    const m = new Map<number, Coach>()
    for (const c of coaches) m.set(c.id, c)
    return m
  }, [coaches])

  const mentorById = useMemo(() => {
    const m = new Map<number, Mentor>()
    for (const mtr of mentors) m.set(mtr.id, mtr)
    return m
  }, [mentors])

  const seasonPractices = useMemo(() => {
    if (!practice?.season) return []
    return allPractices.filter((row) => row.season === practice.season)
  }, [allPractices, practice?.season])

  const { upcoming: upcomingSeasonPractices, past: pastSeasonPractices } =
    useMemo(
      () => splitPracticesByUpcoming(seasonPractices),
      [seasonPractices]
    )

  function handlePracticeSwitch(event: ChangeEvent<HTMLSelectElement>) {
    const nextId = Number.parseInt(event.target.value, 10)
    if (Number.isNaN(nextId) || nextId === practiceId) return
    navigate(`/practices/${nextId}`)
  }

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
        const [p, sList, cList, mList, caList, pList] = await Promise.all([
          fetchPractice(practiceId),
          fetchSeasons(),
          fetchCoaches(),
          fetchMentors(),
          fetchCoachPracticeAssignments(),
          fetchPractices(),
        ])
        if (!cancelled) {
          setPractice(p)
          setAllPractices(Array.isArray(pList) ? pList : [])
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

  const attendingMentorIds = useMemo(
    () => new Set(mentorReplies.map((r) => r.mentor_id)),
    [mentorReplies]
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
          !attendingMentorIds.has(m.id)
      )
    )
  }, [mentors, practiceSeasonId, attendingMentorIds])

  const assignedMentorReplies = useMemo(
    () => sortByPaceThenName(mentorReplies),
    [mentorReplies]
  )

  const sortedAvailableMentorReplies = useMemo(
    () => sortByPaceThenName(availableMentorReplies),
    [availableMentorReplies]
  )

  const mentorSignupRefreshKey = useMemo(
    () =>
      [...mentorReplies, ...availableMentorReplies]
        .map((row) => `${row.mentor_id}:${row.pace}:${row.attendance ?? ''}`)
        .join('|'),
    [mentorReplies, availableMentorReplies]
  )

  function renderMentorReplyRow(
    r: PracticeMentorReply,
    isAvailable: boolean
  ): ReactNode {
    const m = mentorById.get(r.mentor_id)
    const mentorName =
      r.first_name && r.last_name
        ? `${r.first_name} ${r.last_name}`
        : m
          ? `${m.first_name} ${m.last_name}`
          : `Mentor #${r.mentor_id}`

    return (
      <li
        key={r.mentor_id ?? r.id}
        className={
          isAvailable ? 'practice-row practice-row-available' : 'practice-row'
        }
      >
        <div className="practice-row-main">
          <span className="practice-date">
            <MentorPracticeHover
              mentorId={r.mentor_id}
              currentPracticeId={practiceId}
              refreshKey={mentorSignupRefreshKey}
            >
              {mentorName}
            </MentorPracticeHover>
          </span>
          <label className="practice-mentor-pace-label">
            <span className="muted">Pace group</span>
            <select
              className="field-input field-select practice-mentor-pace-select"
              value={r.pace || PACE_GROUPS[0]}
              disabled={saving || updatingMentorPaceId === r.mentor_id}
              aria-label={`Pace group for ${mentorName}`}
              onChange={(e) =>
                handleUpdateMentorPace(r.mentor_id, e.target.value, isAvailable)
              }
            >
              {PACE_GROUPS.map((pace) => (
                <option key={pace} value={pace}>
                  {pace}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="practice-row-actions">
          {isAvailable ? (
            <button
              type="button"
              className="btn btn-secondary practice-available-add-btn"
              disabled={saving}
              onClick={() => handleAddMentorToPractice(r.mentor_id, r.pace)}
            >
              Add to Practice
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-text"
                disabled={saving}
                onClick={() => openSwapModal(r)}
              >
                Swap
              </button>
              <button
                type="button"
                className="btn btn-text"
                disabled={saving}
                onClick={() => handleMakeMentorAvailable(r.mentor_id)}
              >
                Make available
              </button>
            </>
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

  async function handleAddCoach(e: FormEvent) {
    e.preventDefault()
    const coachIds = coachIdsToAdd
      .map((coachId) => Number.parseInt(String(coachId), 10))
      .filter((coachId) => !Number.isNaN(coachId))
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

  async function handleRemoveCoach(assignmentId: number) {
    setSaving(true)
    setError(null)
    try {
      await deleteCoachPracticeAssignment(assignmentId)
      await loadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleAddMentor(e: FormEvent) {
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

  async function handleRemoveMentor(mentorId: number) {
    setSaving(true)
    setError(null)
    try {
      await deletePracticeMentorReply(practiceId, mentorId)
      await loadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleAddMentorToPractice(
    mentorId: number,
    pace?: string | null
  ) {
    setSaving(true)
    setError(null)
    try {
      const updated = await createPracticeMentorReply(practiceId, {
        mentor: mentorId,
        pace: pace || '8-9',
      })
      setAvailableMentorReplies((prev) =>
        prev.filter((row) => row.mentor_id !== mentorId)
      )
      setMentorReplies((prev) => {
        const without = prev.filter((row) => row.mentor_id !== mentorId)
        return sortByPaceThenName([...without, updated])
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleMakeMentorAvailable(mentorId: number) {
    setSaving(true)
    setError(null)
    try {
      const updated = await makePracticeMentorAvailable(practiceId, mentorId)
      setMentorReplies((prev) => prev.filter((r) => r.mentor_id !== mentorId))
      setAvailableMentorReplies((prev) => {
        const without = prev.filter((r) => r.mentor_id !== mentorId)
        return [...without, updated]
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleUpdateMentorPace(
    mentorId: number,
    pace: string,
    isAvailable: boolean
  ) {
    setUpdatingMentorPaceId(mentorId)
    setError(null)
    try {
      const updated = await patchPracticeMentorPace(practiceId, mentorId, pace)
      if (isAvailable) {
        setAvailableMentorReplies((prev) =>
          prev.map((row) => (row.mentor_id === mentorId ? updated : row))
        )
      } else {
        setMentorReplies((prev) =>
          prev.map((row) => (row.mentor_id === mentorId ? updated : row))
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setUpdatingMentorPaceId(null)
    }
  }

  function handleMentorSelectChange(nextId: string) {
    setMentorIdToAdd(nextId)
    const mentorId = Number.parseInt(nextId, 10)
    if (Number.isNaN(mentorId)) return
    const mentor = mentorById.get(mentorId)
    if (mentor?.pace) setMentorPaceToAdd(mentor.pace)
  }

  function openSwapModal(reply: PracticeMentorReply) {
    const m = mentorById.get(reply.mentor_id)
    const mentorName =
      reply.first_name && reply.last_name
        ? `${reply.first_name} ${reply.last_name}`
        : m
          ? `${m.first_name} ${m.last_name}`
          : `Mentor #${reply.mentor_id}`
    setSwapError('')
    setSwapIncomingId('')
    setSwapModal({
      mentorId: reply.mentor_id,
      mentorName,
      pace: reply.pace || m?.pace || '',
    })
  }

  function closeSwapModal() {
    if (saving) return
    setSwapModal(null)
    setSwapIncomingId('')
    setSwapError('')
  }

  async function handleSwapConfirm() {
    if (!swapModal) return
    const incomingId = Number.parseInt(swapIncomingId, 10)
    if (Number.isNaN(incomingId)) {
      setSwapError('Select a replacement mentor.')
      return
    }
    setSaving(true)
    setSwapError('')
    try {
      const result = await swapPracticeMentor(practiceId, {
        outgoing_mentor: swapModal.mentorId,
        incoming_mentor: incomingId,
      })
      setMentorReplies((prev) => {
        const without = prev.filter((row) => row.mentor_id !== swapModal.mentorId)
        return sortByPaceThenName([...without, result.incoming_mentor])
      })
      setAvailableMentorReplies((prev) =>
        prev.filter((row) => row.mentor_id !== incomingId)
      )
      setSwapModal(null)
      setSwapIncomingId('')
      setSwapError('')
    } catch (e) {
      setSwapError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <AppHeader title="Practice View" />

      <main className="panel">
        {loading && <p className="muted">Loading…</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {!loading && practice && (
          <>
            <div className="practice-detail-switcher">
              <label className="field-label" htmlFor="practice-switcher">
                Practice
              </label>
              <select
                id="practice-switcher"
                className="field-input field-select"
                value={String(practiceId)}
                onChange={handlePracticeSwitch}
              >
                {upcomingSeasonPractices.length > 0 ? (
                  <optgroup label="Upcoming">
                    {upcomingSeasonPractices.map((row) => (
                      <option key={row.id} value={String(row.id)}>
                        {practiceSwitcherLabel(row)}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                {pastSeasonPractices.length > 0 ? (
                  <optgroup label="Past">
                    {pastSeasonPractices.map((row) => (
                      <option key={row.id} value={String(row.id)}>
                        {practiceSwitcherLabel(row)}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </select>
              <p className="muted practice-detail-season-note">
                Season{' '}
                {(practice.season != null
                  ? seasonById.get(practice.season)?.year
                  : undefined) ?? practice.season}
              </p>
            </div>
            {practice.description?.trim() ? (
              <div className="practice-description-block">
                <p className="practice-description">{practice.description.trim()}</p>
              </div>
            ) : null}
            {practice.start_location?.trim() ? (
              <p className="muted">
                Start location: {practice.start_location.trim()}
              </p>
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
                onChange={(e: ChangeEvent<HTMLSelectElement>) =>
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
                <div className="practice-available-mentors-header">
                  <h3
                    id="available-mentors-heading"
                    className="practices-section-heading practice-available-mentors-heading"
                  >
                    Available Mentors
                    <span className="practice-available-count">
                      {sortedAvailableMentorReplies.length}
                    </span>
                  </h3>
                  <p className="practice-available-mentors-note">
                    Signed up but not on the assigned roster — add them to the
                    practice if you need coverage.
                  </p>
                </div>
                <ul className="practice-list practice-available-list">
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

      <Modal
        open={swapModal !== null}
        title="Swap mentor"
        onClose={closeSwapModal}
        closeDisabled={saving}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={saving}
              onClick={closeSwapModal}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving || !swapIncomingId}
              onClick={handleSwapConfirm}
            >
              {saving ? 'Swapping…' : 'Confirm swap'}
            </button>
          </>
        }
      >
        {swapModal ? (
          <div className="modal-form-stack">
            <p className="muted">
              Replace <strong>{swapModal.mentorName}</strong>
              {swapModal.pace ? ` (${swapModal.pace})` : ''} with another mentor
              not assigned to this practice. The outgoing mentor will be recorded in
              attendance as <strong>Found Replacement</strong>.
            </p>
            <label className="field-label" htmlFor="swap-incoming-mentor">
              Replacement mentor
            </label>
            <select
              id="swap-incoming-mentor"
              className="field-input field-select"
              value={swapIncomingId}
              onChange={(e) => setSwapIncomingId(e.target.value)}
              disabled={saving}
            >
              <option value="" disabled>
                Select mentor
              </option>
              {availableMentors.map((m) => (
                <option key={m.id} value={String(m.id)}>
                  {m.first_name} {m.last_name} ({m.pace})
                </option>
              ))}
            </select>
            {availableMentors.length === 0 ? (
              <p className="muted">No mentors available to swap in.</p>
            ) : null}
            {swapError ? (
              <p className="error modal-error" role="alert">
                {swapError}
              </p>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  )
}
