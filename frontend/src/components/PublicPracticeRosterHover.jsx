import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchPublicPracticeMentorRoster } from '../api'
import { PACE_GROUPS } from '../paceHelpers.js'

const RUNNER_CURSOR =
  'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 24 24\' fill=\'none\'%3E%3Ccircle cx=\'15\' cy=\'4.5\' r=\'2\' fill=\'%23166534\'/%3E%3Cpath d=\'M13 8.5 11 13l2.5.8-2.2 4.7 1.8.8 2.8-6.2-2.4-.8 1.5-3.5z\' fill=\'%23166534\'/%3E%3Cpath d=\'M8.5 14.5 6 20h2l1.8-4.2\' fill=\'%23166534\'/%3E%3C/svg%3E") 8 18, pointer'

function mentorName(row) {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim()
}

function sortByName(list) {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    return (a.first_name || '').localeCompare(b.first_name || '')
  })
}

function buildPaceGroups(attending, available) {
  const byPace = new Map()
  const seen = new Set()

  for (const mentor of [...attending, ...available]) {
    if (seen.has(mentor.mentor_id)) continue
    seen.add(mentor.mentor_id)
    const pace = mentor.pace?.trim() || '—'
    if (!byPace.has(pace)) byPace.set(pace, [])
    byPace.get(pace).push(mentor)
  }

  const groups = []
  for (const pace of PACE_GROUPS) {
    if (!byPace.has(pace)) continue
    groups.push({ pace, mentors: sortByName(byPace.get(pace)) })
    byPace.delete(pace)
  }

  for (const [pace, mentors] of [...byPace.entries()].sort(([a], [b]) =>
    a.localeCompare(b)
  )) {
    groups.push({ pace, mentors: sortByName(mentors) })
  }

  return groups
}

function PaceGroupRoster({ groups }) {
  if (groups.length === 0) {
    return <p className="muted public-practice-roster-empty">No mentors signed up.</p>
  }

  return (
    <div className="public-practice-roster-pace-groups">
      {groups.map((group) => (
        <section key={group.pace} className="public-practice-roster-pace-group">
          <h4 className="public-practice-roster-pace-title">
            {group.pace === '—' ? 'No pace' : `Pace ${group.pace}`}
          </h4>
          <ul className="public-practice-roster-mentor-list">
            {group.mentors.map((mentor) => (
              <li key={mentor.mentor_id}>{mentorName(mentor)}</li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

/**
 * @param {{ practiceId: number, children: import('react').ReactNode }} props
 */
export function PublicPracticeRosterHover({ practiceId, children }) {
  const containerRef = useRef(null)
  const cacheRef = useRef(new Map())
  const requestRef = useRef(0)

  const [hoverOpen, setHoverOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [roster, setRoster] = useState(null)
  const [loading, setLoading] = useState(false)

  const open = hoverOpen || pinned

  async function loadRoster() {
    const cached = cacheRef.current.get(practiceId)
    if (cached) {
      setRoster(cached)
      return
    }

    const requestId = requestRef.current + 1
    requestRef.current = requestId
    setLoading(true)
    try {
      const data = await fetchPublicPracticeMentorRoster(practiceId)
      if (requestRef.current !== requestId) return
      cacheRef.current.set(practiceId, data)
      setRoster(data)
    } catch {
      if (requestRef.current !== requestId) return
      setRoster({ attending_mentors: [], available_mentors: [] })
    } finally {
      if (requestRef.current === requestId) setLoading(false)
    }
  }

  function closePopup() {
    setPinned(false)
    setHoverOpen(false)
  }

  function handleEnter() {
    if (pinned) return
    setHoverOpen(true)
    loadRoster()
  }

  function handleLeave() {
    if (pinned) return
    setHoverOpen(false)
  }

  function handleTriggerClick(event) {
    event.stopPropagation()
    setPinned(true)
    setHoverOpen(true)
    loadRoster()
  }

  useEffect(() => {
    if (!pinned) return undefined

    function handlePointerDown(event) {
      if (containerRef.current?.contains(event.target)) return
      closePopup()
    }

    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [pinned])

  const paceGroups = useMemo(
    () =>
      buildPaceGroups(
        roster?.attending_mentors ?? [],
        roster?.available_mentors ?? []
      ),
    [roster]
  )

  return (
    <div
      ref={containerRef}
      className="mentor-practice-hover mentor-directory-practice-hover"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <button
        type="button"
        className="mentor-practice-hover-trigger mentor-directory-practice-hover-trigger"
        style={{ cursor: RUNNER_CURSOR }}
        aria-expanded={open}
        onClick={handleTriggerClick}
      >
        {children}
      </button>
      {open ? (
        <div
          className={
            pinned
              ? 'mentor-practice-hover-card public-practice-roster-card public-practice-roster-card-pinned'
              : 'mentor-practice-hover-card public-practice-roster-card'
          }
          role={pinned ? 'dialog' : 'tooltip'}
          aria-modal={pinned ? 'true' : undefined}
        >
          {pinned ? (
            <button
              type="button"
              className="public-practice-roster-close"
              aria-label="Close"
              onClick={(event) => {
                event.stopPropagation()
                closePopup()
              }}
            >
              ×
            </button>
          ) : null}
          <span className="mentor-practice-hover-title">Mentors at this practice</span>
          {loading && roster === null ? (
            <span className="muted">Loading…</span>
          ) : (
            <PaceGroupRoster groups={paceGroups} />
          )}
        </div>
      ) : null}
    </div>
  )
}
