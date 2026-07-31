import { useEffect, useRef, useState, type ReactNode } from 'react'

import { fetchMentorPractices } from '../api'
import { formatDateTime } from '../datetime.js'
import type { MentorPracticeRow } from '../types.js'

function signupStatusLabel(row: MentorPracticeRow): string {
  if (row.status === 'available') return 'Available'
  if (row.attendance === 'first_half') return 'First half'
  if (row.attendance === 'second_half') return 'Second half'
  return 'Assigned'
}

type MentorPracticeHoverProps = {
  mentorId: number
  currentPracticeId?: number
  refreshKey?: string
  children: ReactNode
}

export function MentorPracticeHover({
  mentorId,
  currentPracticeId,
  refreshKey = '',
  children,
}: MentorPracticeHoverProps) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<MentorPracticeRow[] | null>(null)
  const [loading, setLoading] = useState(false)
  const cacheRef = useRef(new Map<number, MentorPracticeRow[]>())
  const requestRef = useRef(0)

  useEffect(() => {
    cacheRef.current.delete(mentorId)
    setRows(null)
  }, [mentorId, refreshKey])

  async function loadRows() {
    const cached = cacheRef.current.get(mentorId)
    if (cached) {
      setRows(cached)
      return
    }

    const requestId = requestRef.current + 1
    requestRef.current = requestId
    setLoading(true)
    try {
      const practiceRows = await fetchMentorPractices(mentorId)
      if (requestRef.current !== requestId) return
      const signedUp = practiceRows.filter(
        (row) => row.status === 'assigned' || row.status === 'available'
      )
      cacheRef.current.set(mentorId, signedUp)
      setRows(signedUp)
    } catch {
      if (requestRef.current !== requestId) return
      setRows([])
    } finally {
      if (requestRef.current === requestId) setLoading(false)
    }
  }

  function handleEnter() {
    setOpen(true)
    void loadRows()
  }

  function handleLeave() {
    setOpen(false)
  }

  const signedUpRows = rows ?? []

  return (
    <span
      className="mentor-practice-hover"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onFocus={handleEnter}
      onBlur={handleLeave}
      tabIndex={0}
    >
      <span className="mentor-practice-hover-trigger">{children}</span>
      {open ? (
        <span className="mentor-practice-hover-card" role="tooltip">
          <span className="mentor-practice-hover-title">Practice signups</span>
          {loading && rows === null ? (
            <span className="muted">Loading…</span>
          ) : signedUpRows.length === 0 ? (
            <span className="muted">Not signed up for any practices.</span>
          ) : (
            <ul className="mentor-practice-hover-list">
              {signedUpRows.map((row) => {
                const isCurrent = row.practice_id === currentPracticeId
                return (
                  <li
                    key={row.practice_id}
                    className={
                      isCurrent
                        ? 'mentor-practice-hover-item mentor-practice-hover-item-current'
                        : 'mentor-practice-hover-item'
                    }
                  >
                    <span className="mentor-practice-hover-date">
                      {row.date ? formatDateTime(row.date) : `Practice #${row.practice_id}`}
                      {isCurrent ? ' (this practice)' : ''}
                    </span>
                    <span className="mentor-practice-hover-meta muted">
                      {signupStatusLabel(row)}
                      {row.pace ? ` · Pace ${row.pace}` : ''}
                      {row.nyrr_race?.trim() ? ` · ${row.nyrr_race.trim()}` : ''}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </span>
      ) : null}
    </span>
  )
}
