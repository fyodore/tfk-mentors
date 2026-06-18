import { useRef, useState } from 'react'

import { fetchPublicPracticeMentorRoster } from '../api'

function mentorName(row) {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim()
}

function attendanceLabel(attendance) {
  if (attendance === 'first_half') return 'First half'
  if (attendance === 'second_half') return 'Second half'
  return null
}

function MentorRosterSection({ title, mentors, showAttendance = false, emptyMessage }) {
  return (
    <div className="public-practice-roster-section">
      <span className="public-practice-roster-section-title">{title}</span>
      {mentors.length === 0 ? (
        <span className="muted">{emptyMessage}</span>
      ) : (
        <ul className="mentor-practice-hover-list">
          {mentors.map((mentor) => {
            const label = showAttendance ? attendanceLabel(mentor.attendance) : null
            return (
              <li key={mentor.mentor_id} className="mentor-practice-hover-item">
                <span className="mentor-practice-hover-date">{mentorName(mentor)}</span>
                <span className="mentor-practice-hover-meta muted">
                  {mentor.pace ? `Pace ${mentor.pace}` : 'No pace'}
                  {label ? ` · ${label}` : ''}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

/**
 * @param {{ practiceId: number, children: import('react').ReactNode }} props
 */
export function PublicPracticeRosterHover({ practiceId, children }) {
  const [open, setOpen] = useState(false)
  const [roster, setRoster] = useState(null)
  const [loading, setLoading] = useState(false)
  const cacheRef = useRef(new Map())
  const requestRef = useRef(0)

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

  function handleEnter() {
    setOpen(true)
    loadRoster()
  }

  function handleLeave() {
    setOpen(false)
  }

  const attending = roster?.attending_mentors ?? []
  const available = roster?.available_mentors ?? []

  return (
    <span
      className="mentor-practice-hover mentor-directory-practice-hover"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onFocus={handleEnter}
      onBlur={handleLeave}
      tabIndex={0}
    >
      <span className="mentor-practice-hover-trigger mentor-directory-practice-hover-trigger">
        {children}
      </span>
      {open ? (
        <span className="mentor-practice-hover-card public-practice-roster-card" role="tooltip">
          <span className="mentor-practice-hover-title">Mentors at this practice</span>
          {loading && roster === null ? (
            <span className="muted">Loading…</span>
          ) : (
            <>
              <MentorRosterSection
                title="Attending"
                mentors={attending}
                showAttendance
                emptyMessage="No attending mentors."
              />
              <MentorRosterSection
                title="Available"
                mentors={available}
                emptyMessage="No available mentors."
              />
            </>
          )}
        </span>
      ) : null}
    </span>
  )
}
