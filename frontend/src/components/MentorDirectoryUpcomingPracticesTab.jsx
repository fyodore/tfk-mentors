import { useEffect, useMemo, useState } from 'react'

import {
  fetchPublicPracticeMentorRoster,
  fetchPublicUpcomingPractices,
} from '../api'
import { formatMentorDirectoryPracticeDate } from '../datetime.js'
import { PACE_GROUPS, paceSortKey } from '../paceHelpers.js'

function personName(row) {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim()
}

function sortByLastName(list) {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    return (a.first_name || '').localeCompare(b.first_name || '')
  })
}

function filterBySelectedPaces(people, selectedPaces) {
  if (selectedPaces.size === 0) return people
  return people.filter((person) => {
    const pace = person.pace?.trim() || ''
    return pace && selectedPaces.has(pace)
  })
}

function buildMentorPaceGroups(mentors, selectedPaces) {
  const byPace = new Map()

  for (const mentor of filterBySelectedPaces(mentors, selectedPaces)) {
    const pace = mentor.pace?.trim() || ''
    const key = pace || '__none__'
    if (!byPace.has(key)) byPace.set(key, [])
    byPace.get(key).push(mentor)
  }

  const groups = []
  for (const pace of PACE_GROUPS) {
    if (!byPace.has(pace)) continue
    groups.push({
      pace,
      label: `Pace ${pace}`,
      mentors: sortByLastName(byPace.get(pace)),
    })
    byPace.delete(pace)
  }

  if (byPace.has('__none__')) {
    groups.push({
      pace: '__none__',
      label: 'No pace',
      mentors: sortByLastName(byPace.get('__none__')),
    })
    byPace.delete('__none__')
  }

  for (const [pace, paceMentors] of [...byPace.entries()].sort(
    ([a], [b]) => paceSortKey(a) - paceSortKey(b) || a.localeCompare(b)
  )) {
    groups.push({
      pace,
      label: pace ? `Pace ${pace}` : 'No pace',
      mentors: sortByLastName(paceMentors),
    })
  }

  return groups
}

function practiceLabel(practice) {
  const when = practice.date
    ? formatMentorDirectoryPracticeDate(practice.date)
    : '—'
  const race = practice.nyrr_race?.trim()
  return race ? `${when} · ${race}` : when
}

export function MentorDirectoryUpcomingPracticesTab() {
  const [practices, setPractices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedPracticeId, setSelectedPracticeId] = useState(null)
  const [rosterByPracticeId, setRosterByPracticeId] = useState({})
  const [rosterLoadingId, setRosterLoadingId] = useState(null)
  const [rosterErrorById, setRosterErrorById] = useState({})
  const [selectedPaces, setSelectedPaces] = useState(() => new Set())

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setError(null)
      try {
        const rows = await fetchPublicUpcomingPractices()
        if (cancelled) return
        const list = Array.isArray(rows) ? rows : []
        setPractices(list)
        setSelectedPracticeId((prev) => {
          if (prev && list.some((p) => p.id === prev)) return prev
          return list[0]?.id ?? null
        })
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setPractices([])
          setSelectedPracticeId(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (selectedPracticeId == null) return undefined
    if (rosterByPracticeId[selectedPracticeId]) return undefined

    let cancelled = false
    const practiceId = selectedPracticeId

    Promise.resolve().then(async () => {
      setRosterLoadingId(practiceId)
      setRosterErrorById((prev) => {
        if (!(practiceId in prev)) return prev
        const next = { ...prev }
        delete next[practiceId]
        return next
      })
      try {
        const roster = await fetchPublicPracticeMentorRoster(practiceId)
        if (cancelled) return
        setRosterByPracticeId((prev) => ({ ...prev, [practiceId]: roster }))
      } catch (e) {
        if (cancelled) return
        setRosterErrorById((prev) => ({
          ...prev,
          [practiceId]: e instanceof Error ? e.message : String(e),
        }))
      } finally {
        if (!cancelled) {
          setRosterLoadingId((prev) => (prev === practiceId ? null : prev))
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [selectedPracticeId, rosterByPracticeId])

  const selectedPractice = useMemo(
    () => practices.find((p) => p.id === selectedPracticeId) ?? null,
    [practices, selectedPracticeId]
  )

  const roster = selectedPracticeId
    ? rosterByPracticeId[selectedPracticeId]
    : null
  const rosterError = selectedPracticeId
    ? rosterErrorById[selectedPracticeId]
    : null
  const rosterLoading =
    selectedPracticeId != null && rosterLoadingId === selectedPracticeId

  const coaches = useMemo(
    () =>
      sortByLastName(filterBySelectedPaces(roster?.coaches ?? [], selectedPaces)),
    [roster, selectedPaces]
  )

  const mentorPaceGroups = useMemo(
    () => buildMentorPaceGroups(roster?.attending_mentors ?? [], selectedPaces),
    [roster, selectedPaces]
  )

  function togglePace(pace) {
    setSelectedPaces((prev) => {
      const next = new Set(prev)
      if (next.has(pace)) next.delete(pace)
      else next.add(pace)
      return next
    })
  }

  if (loading) return <p className="muted">Loading practices…</p>
  if (error) {
    return (
      <p className="error" role="alert">
        {error}
      </p>
    )
  }
  if (practices.length === 0) {
    return <p className="muted">No upcoming practices are visible to mentors.</p>
  }

  return (
    <div className="mentor-directory-upcoming">
      <div className="mentor-directory-upcoming-layout">
        <section
          className="mentor-directory-upcoming-list-panel"
          aria-labelledby="upcoming-practices-heading"
        >
          <h2 id="upcoming-practices-heading">Upcoming practices</h2>
          <ul className="mentor-directory-upcoming-list">
            {practices.map((practice) => {
              const selected = practice.id === selectedPracticeId
              return (
                <li key={practice.id}>
                  <button
                    type="button"
                    className={`mentor-directory-upcoming-practice${
                      selected ? ' is-selected' : ''
                    }`}
                    aria-pressed={selected}
                    onClick={() => setSelectedPracticeId(practice.id)}
                  >
                    <span className="mentor-directory-upcoming-practice-when">
                      {practice.date
                        ? formatMentorDirectoryPracticeDate(practice.date)
                        : '—'}
                    </span>
                    {practice.nyrr_race?.trim() ? (
                      <span className="muted">
                        {practice.nyrr_race.trim()}
                      </span>
                    ) : null}
                  </button>
                </li>
              )
            })}
          </ul>
        </section>

        <section
          className="mentor-directory-upcoming-detail-panel"
          aria-labelledby="upcoming-practice-detail-heading"
        >
          <h2 id="upcoming-practice-detail-heading">
            {selectedPractice ? practiceLabel(selectedPractice) : 'Practice roster'}
          </h2>

          <div className="mentor-directory-upcoming-pace-filter">
            <span className="field-label">Pace groups</span>
            <div
              className="mentor-directory-upcoming-pace-options"
              role="group"
              aria-label="Filter coaches and mentors by pace"
            >
              {PACE_GROUPS.map((pace) => {
                const checked = selectedPaces.has(pace)
                return (
                  <label
                    key={pace}
                    className={`mentor-directory-upcoming-pace-chip${
                      checked ? ' is-selected' : ''
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => togglePace(pace)}
                    />
                    <span>{pace}</span>
                  </label>
                )
              })}
            </div>
            <p className="muted mentor-directory-upcoming-pace-hint">
              {selectedPaces.size === 0
                ? 'Showing all pace groups.'
                : `Showing ${selectedPaces.size} selected pace group${
                    selectedPaces.size === 1 ? '' : 's'
                  }.`}
            </p>
          </div>

          {rosterLoading && !roster ? (
            <p className="muted">Loading roster…</p>
          ) : null}
          {rosterError ? (
            <p className="error" role="alert">
              {rosterError}
            </p>
          ) : null}

          {roster ? (
            <>
              <section
                className="mentor-directory-upcoming-roster-section"
                aria-labelledby="upcoming-coaches-heading"
              >
                <h3 id="upcoming-coaches-heading">Coaches</h3>
                {coaches.length === 0 ? (
                  <p className="muted">
                    {selectedPaces.size > 0
                      ? 'No coaches match the selected pace groups.'
                      : 'No coaches assigned.'}
                  </p>
                ) : (
                  <ul className="mentor-directory-upcoming-person-list">
                    {coaches.map((coach) => (
                      <li key={coach.coach_id}>
                        <span>{personName(coach)}</span>
                        {coach.pace?.trim() ? (
                          <span className="muted">Pace {coach.pace}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section
                className="mentor-directory-upcoming-roster-section"
                aria-labelledby="upcoming-mentors-heading"
              >
                <h3 id="upcoming-mentors-heading">Mentors</h3>
                {mentorPaceGroups.length === 0 ? (
                  <p className="muted">
                    {selectedPaces.size > 0
                      ? 'No mentors match the selected pace groups.'
                      : 'No mentors assigned.'}
                  </p>
                ) : (
                  <div className="mentor-directory-upcoming-pace-groups">
                    {mentorPaceGroups.map((group) => (
                      <section
                        key={group.pace}
                        className="mentor-directory-upcoming-pace-group"
                        aria-labelledby={`upcoming-pace-${group.pace}`}
                      >
                        <h4 id={`upcoming-pace-${group.pace}`}>{group.label}</h4>
                        <ul className="mentor-directory-upcoming-person-list">
                          {group.mentors.map((mentor) => (
                            <li key={mentor.mentor_id}>{personName(mentor)}</li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                )}
              </section>
            </>
          ) : null}
        </section>
      </div>
    </div>
  )
}
