import { useEffect, useRef, useState, type ReactNode } from 'react'

import { fetchCoachPractices } from '../api'
import { formatDateTime } from '../datetime.js'
import type { CoachPracticeRow } from '../types.js'

type CoachPracticeHoverProps = {
  coachId: number
  refreshKey?: string
  children: ReactNode
}

export function CoachPracticeHover({
  coachId,
  refreshKey = '',
  children,
}: CoachPracticeHoverProps) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<CoachPracticeRow[] | null>(null)
  const [loading, setLoading] = useState(false)
  const cacheRef = useRef(new Map<number, CoachPracticeRow[]>())
  const requestRef = useRef(0)

  useEffect(() => {
    cacheRef.current.delete(coachId)
    setRows(null)
  }, [coachId, refreshKey])

  async function loadRows() {
    const cached = cacheRef.current.get(coachId)
    if (cached) {
      setRows(cached)
      return
    }

    const requestId = requestRef.current + 1
    requestRef.current = requestId
    setLoading(true)
    try {
      const practiceRows = await fetchCoachPractices(coachId)
      if (requestRef.current !== requestId) return
      cacheRef.current.set(coachId, practiceRows)
      setRows(practiceRows)
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

  const assignedRows = rows ?? []

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
          <span className="mentor-practice-hover-title">Assigned practices</span>
          {loading && rows === null ? (
            <span className="muted">Loading…</span>
          ) : assignedRows.length === 0 ? (
            <span className="muted">Not assigned to any practices.</span>
          ) : (
            <ul className="mentor-practice-hover-list">
              {assignedRows.map((row) => (
                <li key={row.practice_id} className="mentor-practice-hover-item">
                  <span className="mentor-practice-hover-date">
                    {row.date
                      ? formatDateTime(row.date)
                      : `Practice #${row.practice_id}`}
                  </span>
                  <span className="mentor-practice-hover-meta muted">
                    {[
                      row.season_year != null ? `Season ${row.season_year}` : null,
                      row.pace?.trim() ? `Pace ${row.pace.trim()}` : null,
                      row.nyrr_race?.trim() || null,
                      row.start_location?.trim() || null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </span>
      ) : null}
    </span>
  )
}
