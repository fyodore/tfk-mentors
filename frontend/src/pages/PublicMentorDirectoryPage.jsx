import { useEffect, useMemo, useState } from 'react'

import { fetchPublicMentorDirectory } from '../api'
import { PublicPracticeRosterHover } from '../components/PublicPracticeRosterHover.jsx'
import { formatMentorDirectoryPracticeDate } from '../datetime.js'
import { PACE_GROUPS } from '../paceHelpers.js'

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
            </PublicPracticeRosterHover>
          </li>
        ))}
      </ul>
    </div>
  )
}

function MentorDirectoryList({ mentors, expandedIds, onToggleExpanded }) {
  return (
    <ul className="mentor-directory-list">
      {mentors.map((mentor) => {
        const expanded = expandedIds.has(mentor.id)
        const assignedCount = mentor.assigned_practices?.length ?? 0
        const availableCount = mentor.available_practices?.length ?? 0
        return (
          <li key={mentor.id} className="mentor-directory-item">
            <button
              type="button"
              className="mentor-directory-toggle"
              aria-expanded={expanded}
              onClick={() => onToggleExpanded(mentor.id)}
            >
              <span className="mentor-directory-name">{mentorName(mentor)}</span>
              <span className="mentor-directory-pace">
                {mentor.pace ? `Pace ${mentor.pace}` : 'No pace'}
              </span>
              <span className="mentor-directory-counts muted">
                {assignedCount} attending · {availableCount} available
              </span>
              <span className="mentor-directory-chevron" aria-hidden>
                {expanded ? '▾' : '▸'}
              </span>
            </button>

            {expanded ? (
              <div className="mentor-directory-details">
                <PracticeList
                  title="Attending"
                  practices={mentor.assigned_practices ?? []}
                  emptyMessage="No assigned practices."
                />
                <PracticeList
                  title="Available"
                  practices={mentor.available_practices ?? []}
                  emptyMessage="No available practices."
                />
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

export default function PublicMentorDirectoryPage() {
  const [mentors, setMentors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [nameFilter, setNameFilter] = useState('')
  const [paceFilter, setPaceFilter] = useState('')
  const [expandedIds, setExpandedIds] = useState(() => new Set())

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

  const remoteMentors = useMemo(
    () => filteredMentors.filter((mentor) => mentor.type === REMOTE),
    [filteredMentors]
  )

  function toggleExpanded(id) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
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

        {!loading && !error && filteredMentors.length === 0 ? (
          <p className="muted">No mentors match these filters.</p>
        ) : null}

        {!loading && !error && filteredMentors.length > 0 ? (
          <>
            <section className="mentor-directory-section" aria-labelledby="at-practice-heading">
              <h2 id="at-practice-heading">At Practice</h2>
              {atPracticeMentors.length === 0 ? (
                <p className="muted">No at-practice mentors match these filters.</p>
              ) : (
                <MentorDirectoryList
                  mentors={atPracticeMentors}
                  expandedIds={expandedIds}
                  onToggleExpanded={toggleExpanded}
                />
              )}
            </section>

            <section className="mentor-directory-section" aria-labelledby="remote-heading">
              <h2 id="remote-heading">Remote</h2>
              {remoteMentors.length === 0 ? (
                <p className="muted">No remote mentors match these filters.</p>
              ) : (
                <MentorDirectoryList
                  mentors={remoteMentors}
                  expandedIds={expandedIds}
                  onToggleExpanded={toggleExpanded}
                />
              )}
            </section>
          </>
        ) : null}
      </main>
    </>
  )
}
