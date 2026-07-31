import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { fetchMentor, fetchMentorPractices, fetchSeasons } from '../api'
import { AppHeader } from '../components/AppHeader.tsx'
import { formatDateTime } from '../datetime.js'

function practiceStatusLabel(row) {
  if (row.status === 'available') return 'Available'
  if (row.status !== 'assigned') return 'Not assigned'
  if (row.attendance === 'first_half') return 'Assigned (first half)'
  if (row.attendance === 'second_half') return 'Assigned (second half)'
  return 'Assigned'
}

function practiceStatusClass(row) {
  if (row.status === 'available') return 'mentor-practice-status mentor-practice-status-available'
  if (row.status === 'assigned') return 'mentor-practice-status mentor-practice-status-assigned'
  return 'mentor-practice-status mentor-practice-status-none'
}

export default function MentorDetailPage() {
  const { id } = useParams()
  const mentorId = Number.parseInt(String(id), 10)

  const [mentor, setMentor] = useState(null)
  const [practiceRows, setPracticeRows] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const seasonYearById = useMemo(() => {
    const m = new Map()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  useEffect(() => {
    let cancelled = false
    if (Number.isNaN(mentorId)) {
      setError('Invalid mentor id.')
      setLoading(false)
      return () => {
        cancelled = true
      }
    }

    setLoading(true)
    setError(null)
    Promise.all([fetchMentor(mentorId), fetchMentorPractices(mentorId), fetchSeasons()])
      .then(([mentorRow, practices, sList]) => {
        if (!cancelled) {
          setMentor(mentorRow)
          setPracticeRows(practices)
          setSeasons(sList)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setMentor(null)
          setPracticeRows([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [mentorId])

  const assignedCount = practiceRows.filter((row) => row.status === 'assigned').length
  const availableCount = practiceRows.filter((row) => row.status === 'available').length

  return (
    <>
      <AppHeader title="Mentor View" />

      <main className="panel mentor-detail-panel">
        <p className="muted">
          <Link to="/mentors">← Back to mentors</Link>
        </p>

        {loading && <p className="muted">Loading…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && mentor && (
          <>
            <header className="mentor-detail-header">
              <h2>
                {mentor.first_name} {mentor.last_name}
              </h2>
              <p className="muted">{mentor.email}</p>
              <p className="muted">
                {mentor.cell_phone || 'No cell phone'} · {mentor.type}
                {mentor.pace ? ` · Pace ${mentor.pace}` : ''}
                {mentor.split_practice ? ' · Split practice' : ''}
              </p>
              <p className="muted">
                Seasons{' '}
                {Array.isArray(mentor.seasons) && mentor.seasons.length > 0
                  ? mentor.seasons
                      .map((seasonId) => seasonYearById.get(seasonId) ?? seasonId)
                      .join(', ')
                  : 'none'}
              </p>
            </header>

            <section className="reports-section" aria-labelledby="mentor-practices-heading">
              <h3 id="mentor-practices-heading">Practices</h3>
              <p className="muted reports-intro">
                All practices in this mentor&apos;s seasons. Assigned: {assignedCount}. Available:{' '}
                {availableCount}.
              </p>

              {practiceRows.length === 0 ? (
                <p className="muted">No practices found for this mentor&apos;s seasons.</p>
              ) : (
                <div className="report-table-wrap">
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th scope="col">Practice date</th>
                        <th scope="col">Season</th>
                        <th scope="col">NYRR race</th>
                        <th scope="col">Type</th>
                        <th scope="col">Status</th>
                        <th scope="col">Pace</th>
                        <th scope="col">Practice</th>
                      </tr>
                    </thead>
                    <tbody>
                      {practiceRows.map((row) => (
                        <tr key={row.practice_id}>
                          <td>{row.date ? formatDateTime(row.date) : '—'}</td>
                          <td>{row.season_year ?? row.season_id ?? '—'}</td>
                          <td>{row.nyrr_race?.trim() || '—'}</td>
                          <td>{row.full_practice ? 'Full' : 'Partial'}</td>
                          <td>
                            <span className={practiceStatusClass(row)}>
                              {practiceStatusLabel(row)}
                            </span>
                          </td>
                          <td>{row.pace || '—'}</td>
                          <td>
                            <Link className="btn btn-text" to={`/practices/${row.practice_id}`}>
                              View
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </>
  )
}
