import { useEffect, useMemo, useState } from 'react'

import {
  fetchPublicMentorDirectory,
  fetchPublicMentorDirectoryPractices,
} from '../api'
import { Modal } from '../components/Modal.jsx'
import { PublicPracticeRosterHover } from '../components/PublicPracticeRosterHover.jsx'
import { formatMentorDirectoryPracticeDate } from '../datetime.js'
import { compareByPaceThenName, PACE_GROUPS } from '../paceHelpers.js'
import { downloadMentorAssignedPracticesIcs } from '../practiceCalendar.js'

const AT_PRACTICE = 'At Practice'
const REMOTE = 'Remote'

function mentorName(row) {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim()
}

function assignedPracticeLabel(row) {
  if (row.attendance === 'first_half') return 'First half'
  if (row.attendance === 'second_half') return 'Second half'
  return 'Attending'
}

function PracticeList({ title, practices, emptyMessage }) {
  if (!practices.length) {
    return (
      <div className="mentor-directory-practice-group">
        <h4>{title}</h4>
        <p className="muted">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="mentor-directory-practice-group">
      <h4>{title}</h4>
      <ul className="mentor-directory-practice-list">
        {practices.map((practice) => (
          <li key={practice.practice_id} className="mentor-directory-practice-row">
            <PublicPracticeRosterHover practiceId={practice.practice_id}>
              <span className="mentor-directory-practice-date">
                {practice.date ? formatMentorDirectoryPracticeDate(practice.date) : '—'}
              </span>
            </PublicPracticeRosterHover>
            {practice.nyrr_race ? (
              <span className="muted">{practice.nyrr_race}</span>
            ) : null}
            {title === 'Attending' ? (
              <span className="mentor-directory-practice-status">
                {assignedPracticeLabel(practice)}
              </span>
            ) : null}
            {practice.pace ? (
              <span className="muted">Pace {practice.pace}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function MentorDirectoryList({
  mentors,
  expandedIds,
  practiceDetailsByMentorId,
  loadingPracticeIds,
  practiceErrorsByMentorId,
  onToggleExpanded,
  onOpenCalendar,
  hidePace = false,
}) {
  return (
    <ul className="mentor-directory-list">
      {mentors.map((mentor) => {
        const expanded = expandedIds.has(mentor.id)
        const assignedCount = mentor.assigned_count ?? 0
        const availableCount = mentor.available_count ?? 0
        const practiceDetails = practiceDetailsByMentorId[mentor.id]
        const loadingPractices = loadingPracticeIds.has(mentor.id)
        const practiceError = practiceErrorsByMentorId[mentor.id]

        return (
          <li key={mentor.id} className="mentor-directory-item">
            <div className="mentor-directory-item-top">
              <button
                type="button"
                className={`mentor-directory-toggle${hidePace ? ' mentor-directory-toggle--no-pace' : ''}`}
                aria-expanded={expanded}
                onClick={() => onToggleExpanded(mentor.id)}
              >
                <span className="mentor-directory-name">{mentorName(mentor)}</span>
                {hidePace ? null : (
                  <span className="mentor-directory-pace">
                    {mentor.pace ? `Pace ${mentor.pace}` : 'No pace'}
                  </span>
                )}
                <span className="mentor-directory-counts muted">
                  {assignedCount} attending · {availableCount} available
                </span>
                <span className="mentor-directory-chevron" aria-hidden>
                  {expanded ? '▾' : '▸'}
                </span>
              </button>
              {assignedCount > 0 ? (
                <button
                  type="button"
                  className="btn btn-text mentor-directory-calendar-btn"
                  onClick={() => onOpenCalendar(mentor)}
                >
                  Add to calendar
                </button>
              ) : null}
            </div>

            {expanded ? (
              <div className="mentor-directory-details">
                {loadingPractices && !practiceDetails ? (
                  <p className="muted">Loading practices…</p>
                ) : null}
                {practiceError ? (
                  <p className="error" role="alert">
                    {practiceError}
                  </p>
                ) : null}
                {practiceDetails ? (
                  <>
                    <PracticeList
                      title="Attending"
                      practices={practiceDetails.assigned_practices ?? []}
                      emptyMessage="No assigned practices."
                    />
                    <PracticeList
                      title="Available"
                      practices={practiceDetails.available_practices ?? []}
                      emptyMessage="No available practices."
                    />
                  </>
                ) : null}
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

function sortMentorsByName(mentors) {
  return [...mentors].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    return (a.first_name || '').localeCompare(b.first_name || '')
  })
}

function groupAtPracticeMentorsByPace(mentors) {
  const byPace = new Map()

  for (const mentor of mentors) {
    const pace = mentor.pace?.trim() || ''
    if (!byPace.has(pace)) byPace.set(pace, [])
    byPace.get(pace).push(mentor)
  }

  const groups = []
  for (const pace of PACE_GROUPS) {
    if (!byPace.has(pace)) continue
    groups.push({
      pace,
      label: `Pace ${pace}`,
      mentors: sortMentorsByName(byPace.get(pace)),
    })
    byPace.delete(pace)
  }

  for (const [pace, paceMentors] of [...byPace.entries()].sort(([a], [b]) =>
    compareByPaceThenName({ pace: a }, { pace: b })
  )) {
    groups.push({
      pace,
      label: pace ? `Pace ${pace}` : 'No pace',
      mentors: sortMentorsByName(paceMentors),
    })
  }

  return groups
}

export default function PublicMentorDirectoryPage() {
  const [activeTab, setActiveTab] = useState('all')
  const [mentors, setMentors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [nameFilter, setNameFilter] = useState('')
  const [paceFilter, setPaceFilter] = useState('')
  const [expandedIds, setExpandedIds] = useState(() => new Set())
  const [practiceDetailsByMentorId, setPracticeDetailsByMentorId] = useState({})
  const [loadingPracticeIds, setLoadingPracticeIds] = useState(() => new Set())
  const [practiceErrorsByMentorId, setPracticeErrorsByMentorId] = useState({})
  const [calendarMentor, setCalendarMentor] = useState(null)
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [calendarError, setCalendarError] = useState(null)

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setError(null)
      try {
        const rows = await fetchPublicMentorDirectory()
        if (!cancelled) {
          setMentors(Array.isArray(rows) ? rows : [])
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setMentors([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  const filteredMentors = useMemo(() => {
    const nameQuery = nameFilter.trim().toLowerCase()
    return mentors.filter((mentor) => {
      if (paceFilter && mentor.pace !== paceFilter) return false
      if (!nameQuery) return true
      return mentorName(mentor).toLowerCase().includes(nameQuery)
    })
  }, [mentors, nameFilter, paceFilter])

  const atPracticeMentors = useMemo(
    () => filteredMentors.filter((mentor) => mentor.type === AT_PRACTICE),
    [filteredMentors]
  )

  const atPracticeMentorsByPace = useMemo(() => {
    const groups = groupAtPracticeMentorsByPace(atPracticeMentors)
    if (!paceFilter) return groups
    return groups.filter((group) => group.pace === paceFilter)
  }, [atPracticeMentors, paceFilter])

  const remoteMentors = useMemo(
    () => filteredMentors.filter((mentor) => mentor.type === REMOTE),
    [filteredMentors]
  )

  async function ensurePracticeDetails(id) {
    if (practiceDetailsByMentorId[id]) {
      return practiceDetailsByMentorId[id]
    }

    setLoadingPracticeIds((prev) => new Set(prev).add(id))
    setPracticeErrorsByMentorId((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })

    try {
      const details = await fetchPublicMentorDirectoryPractices(id)
      setPracticeDetailsByMentorId((prev) => ({ ...prev, [id]: details }))
      return details
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setPracticeErrorsByMentorId((prev) => ({
        ...prev,
        [id]: message,
      }))
      throw e
    } finally {
      setLoadingPracticeIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  async function toggleExpanded(id) {
    const willExpand = !expandedIds.has(id)

    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (willExpand) next.add(id)
      else next.delete(id)
      return next
    })

    if (!willExpand || practiceDetailsByMentorId[id]) {
      return
    }

    try {
      await ensurePracticeDetails(id)
    } catch {
      // Error state is stored for the expanded panel.
    }
  }

  async function openCalendar(mentor) {
    setCalendarMentor(mentor)
    setCalendarError(null)
    setCalendarLoading(true)
    try {
      await ensurePracticeDetails(mentor.id)
    } catch (e) {
      setCalendarError(e instanceof Error ? e.message : String(e))
    } finally {
      setCalendarLoading(false)
    }
  }

  function closeCalendar() {
    setCalendarMentor(null)
    setCalendarError(null)
    setCalendarLoading(false)
  }

  function handleCalendarDownload(provider) {
    if (!calendarMentor) return
    const details = practiceDetailsByMentorId[calendarMentor.id]
    const practices = details?.assigned_practices ?? []
    const ok = downloadMentorAssignedPracticesIcs(provider, {
      mentorId: calendarMentor.id,
      firstName: calendarMentor.first_name,
      lastName: calendarMentor.last_name,
      practices,
    })
    if (!ok) {
      setCalendarError('No assigned practices to add to the calendar.')
      return
    }
    closeCalendar()
  }

  const calendarAssignedCount =
    calendarMentor && practiceDetailsByMentorId[calendarMentor.id]
      ? (practiceDetailsByMentorId[calendarMentor.id].assigned_practices ?? []).length
      : calendarMentor?.assigned_count ?? 0

  const listProps = {
    expandedIds,
    practiceDetailsByMentorId,
    loadingPracticeIds,
    practiceErrorsByMentorId,
    onToggleExpanded: toggleExpanded,
    onOpenCalendar: openCalendar,
  }

  return (
    <>
      <header className="app-header">
        <h1>Mentor directory</h1>
        <p className="tagline muted">
          Assigned and available practices for each mentor.
        </p>
      </header>

      <main className="panel mentor-directory-panel">
        <div
          className="emails-tabs mentor-directory-tabs"
          role="tablist"
          aria-label="Mentor directory views"
        >
          <button
            type="button"
            role="tab"
            className={`emails-tab${activeTab === 'all' ? ' emails-tab-active' : ''}`}
            aria-selected={activeTab === 'all'}
            onClick={() => setActiveTab('all')}
          >
            All mentors
          </button>
          <button
            type="button"
            role="tab"
            className={`emails-tab${activeTab === 'at-practice-by-pace' ? ' emails-tab-active' : ''}`}
            aria-selected={activeTab === 'at-practice-by-pace'}
            onClick={() => setActiveTab('at-practice-by-pace')}
          >
            Practice Mentors by Pace
          </button>
        </div>

        <div className="mentor-directory-filters">
          <label className="field-label" htmlFor="mentor-directory-name-filter">
            Name
          </label>
          <input
            id="mentor-directory-name-filter"
            className="field-input"
            type="search"
            placeholder="Search by name"
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
          />

          <label className="field-label" htmlFor="mentor-directory-pace-filter">
            Pace
          </label>
          <select
            id="mentor-directory-pace-filter"
            className="field-input field-select"
            value={paceFilter}
            onChange={(e) => setPaceFilter(e.target.value)}
          >
            <option value="">All paces</option>
            {PACE_GROUPS.map((pace) => (
              <option key={pace} value={pace}>
                {pace}
              </option>
            ))}
          </select>
        </div>

        {loading ? <p className="muted">Loading…</p> : null}
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {!loading && !error && activeTab === 'all' && filteredMentors.length === 0 ? (
          <p className="muted">No mentors match these filters.</p>
        ) : null}

        {!loading && !error && activeTab === 'at-practice-by-pace' && atPracticeMentors.length === 0 ? (
          <p className="muted">No at-practice mentors match these filters.</p>
        ) : null}

        {!loading && !error && activeTab === 'all' && filteredMentors.length > 0 ? (
          <>
            <section className="mentor-directory-section" aria-labelledby="at-practice-heading">
              <h2 id="at-practice-heading">At Practice</h2>
              {atPracticeMentors.length === 0 ? (
                <p className="muted">No at-practice mentors match these filters.</p>
              ) : (
                <MentorDirectoryList mentors={atPracticeMentors} {...listProps} />
              )}
            </section>

            <section className="mentor-directory-section" aria-labelledby="remote-heading">
              <h2 id="remote-heading">Remote</h2>
              {remoteMentors.length === 0 ? (
                <p className="muted">No remote mentors match these filters.</p>
              ) : (
                <MentorDirectoryList mentors={remoteMentors} {...listProps} />
              )}
            </section>
          </>
        ) : null}

        {!loading && !error && activeTab === 'at-practice-by-pace' && atPracticeMentors.length > 0 ? (
          atPracticeMentorsByPace.length === 0 ? (
            <p className="muted">No mentors match the selected pace.</p>
          ) : (
            atPracticeMentorsByPace.map((group) => (
              <section
                key={group.pace || 'no-pace'}
                className="mentor-directory-section mentor-directory-pace-section"
                aria-labelledby={`pace-group-${group.pace || 'none'}`}
              >
                <h2 id={`pace-group-${group.pace || 'none'}`}>{group.label}</h2>
                <MentorDirectoryList
                  mentors={group.mentors}
                  hidePace
                  {...listProps}
                />
              </section>
            ))
          )
        ) : null}
      </main>

      <Modal
        open={Boolean(calendarMentor)}
        title="Add to calendar"
        onClose={closeCalendar}
        closeDisabled={calendarLoading}
        footer={
          <button
            type="button"
            className="btn btn-secondary"
            onClick={closeCalendar}
            disabled={calendarLoading}
          >
            Cancel
          </button>
        }
      >
        {calendarMentor ? (
          <>
            <p className="mentor-directory-calendar-intro">
              Download assigned practices for{' '}
              <strong>{mentorName(calendarMentor)}</strong>
              {calendarLoading
                ? '…'
                : ` (${calendarAssignedCount} practice${
                    calendarAssignedCount === 1 ? '' : 's'
                  }).`}
              Available practices are not included.
            </p>
            {calendarLoading ? <p className="muted">Loading practices…</p> : null}
            {calendarError ? (
              <p className="error" role="alert">
                {calendarError}
              </p>
            ) : null}
            <div className="mentor-directory-calendar-options">
              <button
                type="button"
                className="btn btn-primary mentor-directory-calendar-option"
                disabled={calendarLoading || Boolean(calendarError) || calendarAssignedCount === 0}
                onClick={() => handleCalendarDownload('apple')}
              >
                Apple Calendar
              </button>
              <button
                type="button"
                className="btn btn-primary mentor-directory-calendar-option"
                disabled={calendarLoading || Boolean(calendarError) || calendarAssignedCount === 0}
                onClick={() => handleCalendarDownload('google')}
              >
                Google Calendar
              </button>
              <button
                type="button"
                className="btn btn-primary mentor-directory-calendar-option"
                disabled={calendarLoading || Boolean(calendarError) || calendarAssignedCount === 0}
                onClick={() => handleCalendarDownload('outlook')}
              >
                Outlook
              </button>
            </div>
            <p className="muted mentor-directory-calendar-hint">
              Opens a calendar file (.ics) you can add in your chosen app.
            </p>
          </>
        ) : null}
      </Modal>
    </>
  )
}
