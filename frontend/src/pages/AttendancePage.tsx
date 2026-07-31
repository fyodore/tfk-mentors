import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  fetchArchivedPracticeAttendance,
  fetchCurrentPracticeAttendance,
  fetchPracticeAttendance,
  fetchSeasons,
  patchPracticeAttendance,
} from '../api'
import { AppHeader } from '../components/AppHeader.tsx'
import { formatDateTime } from '../datetime.js'
import { sortByPaceThenName } from '../paceHelpers.js'
import {
  currentSeasonFromList,
  sortSeasonsByYearDesc,
} from '../seasonHelpers.js'
import type {
  ArchivedPracticeAttendance,
  AttendanceShowUp,
  PracticeAttendanceDetail,
  PracticeAttendanceMentor,
  Season,
} from '../types.js'

function mentorName(row: PracticeAttendanceMentor): string {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim()
}

function showUpLabel(showUp: AttendanceShowUp | null | undefined): string {
  if (showUp === 'attended') return 'Attended'
  if (showUp === 'missed') return 'Missed'
  if (showUp === 'found_replacement') return 'Found Replacement'
  return 'Not recorded'
}

function AttendanceStatusBadge({
  showUp,
}: {
  showUp: AttendanceShowUp | null | undefined
}) {
  const className =
    showUp === 'attended'
      ? 'attendance-status attended'
      : showUp === 'missed'
        ? 'attendance-status missed'
        : showUp === 'found_replacement'
          ? 'attendance-status found-replacement'
          : 'attendance-status unset'
  return <span className={className}>{showUpLabel(showUp)}</span>
}

export default function AttendancePage() {
  const { id: routeId } = useParams()
  const navigate = useNavigate()
  const practiceIdFromRoute = routeId
    ? Number.parseInt(String(routeId), 10)
    : null

  const [seasons, setSeasons] = useState<Season[]>([])
  const [seasonFilter, setSeasonFilter] = useState('')
  const [practice, setPractice] = useState<PracticeAttendanceDetail | null>(null)
  const [archived, setArchived] = useState<ArchivedPracticeAttendance[]>([])
  const [comments, setComments] = useState('')
  const [showUpByMentor, setShowUpByMentor] = useState<
    Record<number, AttendanceShowUp | null>
  >({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

  function applyPracticePayload(payload: PracticeAttendanceDetail) {
    setPractice(payload)
    setComments(payload.attendance_comments ?? '')
    const next: Record<number, AttendanceShowUp | null> = {}
    for (const row of payload.assigned_mentors ?? []) {
      next[row.mentor_id] = row.show_up ?? null
    }
    setShowUpByMentor(next)
  }

  async function loadArchived(seasonId: string | undefined) {
    const rows = await fetchArchivedPracticeAttendance(
      seasonId ? { season: seasonId } : {}
    )
    setArchived(Array.isArray(rows) ? rows : [])
  }

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setError(null)
      setSaveMessage('')
      try {
        const sList = await fetchSeasons()
        if (cancelled) return
        setSeasons(sList)
        const defaultSeason =
          seasonFilter ||
          String(
            currentSeasonFromList(sList)?.id ??
              sortSeasonsByYearDesc(sList)[0]?.id ??
              ''
          )
        if (!seasonFilter && defaultSeason) {
          setSeasonFilter(String(defaultSeason))
        }

        if (practiceIdFromRoute && !Number.isNaN(practiceIdFromRoute)) {
          const payload = await fetchPracticeAttendance(practiceIdFromRoute)
          if (!cancelled) applyPracticePayload(payload)
        } else {
          const current = await fetchCurrentPracticeAttendance()
          if (!cancelled) {
            if (current.practice) {
              applyPracticePayload(current.practice)
            } else {
              setPractice(null)
              setComments('')
              setShowUpByMentor({})
            }
          }
        }

        const rows = await fetchArchivedPracticeAttendance(
          defaultSeason ? { season: defaultSeason } : {}
        )
        if (!cancelled) setArchived(Array.isArray(rows) ? rows : [])
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
  }, [practiceIdFromRoute])

  useEffect(() => {
    if (!seasonFilter || loading) return
    let cancelled = false

    Promise.resolve().then(async () => {
      try {
        const rows = await fetchArchivedPracticeAttendance({
          season: seasonFilter,
        })
        if (!cancelled) setArchived(Array.isArray(rows) ? rows : [])
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [seasonFilter, loading])

  const assignedMentors = useMemo(
    () => sortByPaceThenName(practice?.assigned_mentors ?? []),
    [practice]
  )

  async function handleSave() {
    if (!practice?.practice_id) return
    setSaving(true)
    setError(null)
    setSaveMessage('')
    try {
      const mentors = Object.entries(showUpByMentor).map(([mentorId, showUp]) => ({
        mentor_id: Number.parseInt(mentorId, 10),
        show_up: showUp,
      }))
      const updated = await patchPracticeAttendance(practice.practice_id, {
        attendance_comments: comments,
        mentors,
      })
      applyPracticePayload(updated)
      setSaveMessage('Attendance saved.')
      await loadArchived(seasonFilter || undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  function setMentorShowUp(
    mentorId: number,
    showUp: AttendanceShowUp | null
  ) {
    setShowUpByMentor((prev) => ({ ...prev, [mentorId]: showUp }))
  }

  function openArchivedPractice(practiceId: number) {
    navigate(`/attendance/${practiceId}`)
  }

  return (
    <>
      <AppHeader title="Practice Attendance" />

      <main className="panel attendance-page">
        <div className="attendance-intro">
          <p className="muted">
            Bookmark{' '}
            <Link to="/attendance" className="inline-link">
              /attendance
            </Link>{' '}
            to open the practice coming up or within the last 24 hours.
          </p>
          {!routeId ? (
            <p className="muted">Showing the current practice window.</p>
          ) : (
            <p>
              <Link to="/attendance" className="inline-link">
                Back to current practice
              </Link>
            </p>
          )}
        </div>

        {loading ? <p className="muted">Loading…</p> : null}
        {error ? <p className="error">{error}</p> : null}

        {!loading && !practice ? (
          <section className="attendance-section">
            <h2>Current practice</h2>
            <p className="muted">
              No practice is coming up or within the last 24 hours. Choose an
              archived practice below.
            </p>
          </section>
        ) : null}

        {!loading && practice ? (
          <>
            <section className="attendance-section">
              <h2>
                {practice.is_current_window ? 'Current practice' : 'Practice'}
              </h2>
              <dl className="attendance-practice-meta">
                <div>
                  <dt>Date</dt>
                  <dd>{formatDateTime(practice.date)}</dd>
                </div>
                <div>
                  <dt>Season</dt>
                  <dd>{practice.season_year}</dd>
                </div>
                {practice.nyrr_race ? (
                  <div>
                    <dt>NYRR race</dt>
                    <dd>{practice.nyrr_race}</dd>
                  </div>
                ) : null}
                {practice.start_location ? (
                  <div>
                    <dt>Start location</dt>
                    <dd>{practice.start_location}</dd>
                  </div>
                ) : null}
              </dl>
              {practice.description ? (
                <p className="attendance-practice-description muted">
                  {practice.description}
                </p>
              ) : null}
            </section>

            <section className="attendance-section">
              <h2>Assigned mentors</h2>
              {assignedMentors.length === 0 ? (
                <p className="muted">No mentors are assigned to this practice.</p>
              ) : (
                <ul className="attendance-mentor-list">
                  {assignedMentors.map((row) => (
                    <li
                      key={row.mentor_id}
                      className={
                        row.swapped_out
                          ? 'attendance-mentor-row attendance-mentor-row-swapped'
                          : 'attendance-mentor-row'
                      }
                    >
                      <div className="attendance-mentor-info">
                        <span className="attendance-mentor-name">
                          {mentorName(row)}
                        </span>
                        <span className="muted">{row.pace || '—'}</span>
                        <AttendanceStatusBadge
                          showUp={showUpByMentor[row.mentor_id]}
                        />
                        {row.swapped_out ? (
                          <span className="muted attendance-swapped-note">
                            Swapped off roster
                          </span>
                        ) : null}
                      </div>
                      {row.swapped_out ||
                      showUpByMentor[row.mentor_id] ===
                        'found_replacement' ? null : (
                        <div className="attendance-mentor-actions">
                          <button
                            type="button"
                            className={
                              showUpByMentor[row.mentor_id] === 'attended'
                                ? 'btn-primary'
                                : 'btn-secondary'
                            }
                            disabled={saving}
                            onClick={() =>
                              setMentorShowUp(row.mentor_id, 'attended')
                            }
                          >
                            Attended
                          </button>
                          <button
                            type="button"
                            className={
                              showUpByMentor[row.mentor_id] === 'missed'
                                ? 'btn-danger'
                                : 'btn-secondary'
                            }
                            disabled={saving}
                            onClick={() =>
                              setMentorShowUp(row.mentor_id, 'missed')
                            }
                          >
                            Missed
                          </button>
                          <button
                            type="button"
                            className="btn-text"
                            disabled={saving}
                            onClick={() => setMentorShowUp(row.mentor_id, null)}
                          >
                            Clear
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="attendance-section">
              <h2>General comments</h2>
              <label className="field-label" htmlFor="attendance-comments">
                Notes for this practice
              </label>
              <textarea
                id="attendance-comments"
                className="field-input field-textarea"
                rows={5}
                value={comments}
                disabled={saving}
                onChange={(e) => setComments(e.target.value)}
              />
              <div className="attendance-save-row">
                <button
                  type="button"
                  className="btn-primary"
                  disabled={saving}
                  onClick={handleSave}
                >
                  {saving ? 'Saving…' : 'Save attendance'}
                </button>
                {saveMessage ? (
                  <span className="muted attendance-save-message">
                    {saveMessage}
                  </span>
                ) : null}
              </div>
            </section>
          </>
        ) : null}

        <section className="attendance-section">
          <div className="attendance-section-header">
            <h2>Archived practices</h2>
            <div className="attendance-season-filter">
              <label className="field-label" htmlFor="attendance-season-filter">
                Season
              </label>
              <select
                id="attendance-season-filter"
                className="field-input field-select"
                value={seasonFilter}
                onChange={(e) => setSeasonFilter(e.target.value)}
              >
                {sortedSeasons.map((season) => (
                  <option key={season.id} value={String(season.id)}>
                    {season.year}
                    {season.is_current ? ' (current)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {archived.length === 0 ? (
            <p className="muted">No archived practices for this season.</p>
          ) : (
            <div className="report-table-wrap">
              <table className="report-table attendance-archive-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Assigned</th>
                    <th>Attended</th>
                    <th>Missed</th>
                    <th>Found replacement</th>
                    <th>Not recorded</th>
                    <th>Mentors</th>
                  </tr>
                </thead>
                <tbody>
                  {archived.map((row) => {
                    const isSelected = practice?.practice_id === row.practice_id
                    return (
                      <tr
                        key={row.practice_id}
                        className={
                          isSelected ? 'attendance-archive-selected' : ''
                        }
                      >
                        <td>
                          <button
                            type="button"
                            className="btn-text attendance-archive-link"
                            onClick={() =>
                              openArchivedPractice(row.practice_id)
                            }
                          >
                            {formatDateTime(row.date)}
                          </button>
                        </td>
                        <td>{row.assigned_count}</td>
                        <td>{row.attended_count}</td>
                        <td>{row.missed_count}</td>
                        <td>{row.found_replacement_count ?? 0}</td>
                        <td>{row.unset_count}</td>
                        <td>
                          <ul className="attendance-archive-mentors">
                            {sortByPaceThenName(row.assigned_mentors ?? []).map(
                              (mentor) => (
                                <li key={mentor.mentor_id}>
                                  {mentorName(mentor)}
                                  {' — '}
                                  <AttendanceStatusBadge
                                    showUp={mentor.show_up}
                                  />
                                </li>
                              )
                            )}
                          </ul>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </>
  )
}
