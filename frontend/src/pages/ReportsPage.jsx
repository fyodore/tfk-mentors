import { useEffect, useMemo, useState } from 'react'
import * as XLSX from 'xlsx'

import { fetchMentorNonResponseReport, fetchPracticeRosterReport, fetchSeasons } from '../api'
import { AppHeader } from '../components/AppHeader.jsx'
import { formatDateTime } from '../datetime.js'

const ROSTER_HEADERS = [
  'Practice Date',
  'Season',
  'NYRR Race',
  'Role',
  'First Name',
  'Last Name',
  'Email',
  'Pace',
  'Available',
]

const PACE_COLUMN_INDEX = ROSTER_HEADERS.indexOf('Pace')

const PACE_ORDER = {
  '8-9': 1,
  '9-10': 2,
  '10-11': 3,
  '11-12': 4,
  '12-13': 5,
  '13+': 6,
}

/** @typedef {'name' | 'email' | 'pace'} SortKey */

function fullName(first, last) {
  return `${first ?? ''} ${last ?? ''}`.trim()
}

/** @param {SortKey} sortKey @param {'asc' | 'desc'} direction */
function comparePeople(a, b, sortKey, direction) {
  const sign = direction === 'asc' ? 1 : -1
  if (sortKey === 'name') {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln * sign
    return (a.first_name || '').localeCompare(b.first_name || '') * sign
  }
  if (sortKey === 'email') {
    return (a.email || '').localeCompare(b.email || '') * sign
  }
  const pa = PACE_ORDER[a.pace] ?? 99
  const pb = PACE_ORDER[b.pace] ?? 99
  if (pa !== pb) return (pa - pb) * sign
  return fullName(a.first_name, a.last_name).localeCompare(
    fullName(b.first_name, b.last_name)
  )
}

/** @param {Array<{ date?: string, id?: number }>} practices */
function sortPracticesByDateAsc(practices) {
  return [...practices].sort((a, b) => {
    const ta = a.date ? new Date(a.date).getTime() : 0
    const tb = b.date ? new Date(b.date).getTime() : 0
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || (a.id ?? 0) - (b.id ?? 0)
  })
}

/** @param {Array<{ coaches?: unknown[], mentors?: unknown[], available_mentors?: unknown[] }>} practices */
function sortPracticePeople(practices, sortKey, direction) {
  return practices.map((practice) => {
    const attendingMentors = (practice.mentors ?? []).map((mentor) => ({
      ...mentor,
      available: false,
    }))
    const availableMentors = (practice.available_mentors ?? []).map((mentor) => ({
      ...mentor,
      available: true,
    }))
    const people = [
      ...(practice.coaches ?? []),
      ...attendingMentors,
      ...availableMentors,
    ]
    people.sort((a, b) => comparePeople(a, b, sortKey, direction))
    return { ...practice, people }
  })
}

/** @param {ReturnType<typeof sortPracticePeople>} practices */
function buildRosterRows(practices) {
  const rows = [ROSTER_HEADERS]
  for (const practice of practices) {
    const when = practice.date ? formatDateTime(practice.date) : ''
    for (const person of practice.people) {
      rows.push([
        when,
        practice.season_year ?? practice.season,
        practice.nyrr_race ?? '',
        person.role,
        person.first_name,
        person.last_name,
        person.email ?? '',
        person.pace ?? '',
        person.available ? 'X' : '',
      ])
    }
  }
  return rows
}

/** @param {ReturnType<typeof sortPracticePeople>} practices */
function downloadExcel(filename, practices) {
  const rows = buildRosterRows(practices)
  const worksheet = XLSX.utils.aoa_to_sheet(rows)

  for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
    const cellAddress = XLSX.utils.encode_cell({
      r: rowIndex,
      c: PACE_COLUMN_INDEX,
    })
    const cell = worksheet[cellAddress]
    if (!cell) continue
    cell.t = 's'
    cell.v = String(cell.v ?? '')
    cell.z = '@'
  }

  worksheet['!cols'] = [
    { wch: 24 },
    { wch: 8 },
    { wch: 22 },
    { wch: 8 },
    { wch: 14 },
    { wch: 14 },
    { wch: 28 },
    { wch: 8 },
    { wch: 10 },
  ]

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Practice roster')
  XLSX.writeFile(workbook, filename)
}

const PACE_GROUPS = ['8-9', '9-10', '10-11', '11-12', '12-13', '13+']

/** @param {Array<{ mentors?: Array<{ mentor_id?: number, email?: string, pace?: string, first_name?: string, last_name?: string, mentor_type?: string }>, id?: number }>} practices */
function buildMentorSignupSummary(practices) {
  /** @type {Map<number|string, { mentor_id?: number, first_name?: string, last_name?: string, email?: string, pace?: string, mentor_type?: string, practice_count: number }>} */
  const mentorById = new Map()
  /** @type {Map<string, Set<number>>} */
  const paceToPracticeIds = new Map(PACE_GROUPS.map((pace) => [pace, new Set()]))
  let practicesWithMentors = 0

  for (const practice of practices) {
    const mentors = practice.mentors ?? []
    if (mentors.length === 0) continue
    practicesWithMentors += 1
    const pacesInPractice = new Set()
    for (const mentor of mentors) {
      const pace = mentor.pace?.trim() || ''
      if (PACE_ORDER[pace]) pacesInPractice.add(pace)
      const key = mentor.mentor_id ?? mentor.email ?? fullName(mentor.first_name, mentor.last_name)
      if (!mentorById.has(key)) {
        mentorById.set(key, {
          mentor_id: mentor.mentor_id,
          first_name: mentor.first_name,
          last_name: mentor.last_name,
          email: mentor.email,
          pace: mentor.pace,
          mentor_type: mentor.mentor_type,
          practice_count: 0,
        })
      }
      mentorById.get(key).practice_count += 1
    }
    for (const pace of pacesInPractice) {
      paceToPracticeIds.get(pace)?.add(practice.id)
    }
  }

  const practicesByPace = PACE_GROUPS.map((pace) => ({
    pace,
    count: paceToPracticeIds.get(pace)?.size ?? 0,
  })).filter((row) => row.count > 0)

  const mentorsByPace = PACE_GROUPS.map((pace) => ({
    pace,
    count: practices.reduce(
      (sum, practice) =>
        sum +
        (practice.mentors ?? []).filter((mentor) => (mentor.pace?.trim() || '') === pace)
          .length,
      0
    ),
  })).filter((row) => row.count > 0)

  const mentors = [...mentorById.values()].sort(
    (a, b) =>
      b.practice_count - a.practice_count ||
      (a.last_name || '').localeCompare(b.last_name || '') ||
      (a.first_name || '').localeCompare(b.first_name || '')
  )

  return { practicesWithMentors, practicesByPace, mentorsByPace, mentors }
}

function formatPaceCounts(counts) {
  if (!Array.isArray(counts) || counts.length === 0) return ''
  return counts.map(({ pace, count }) => `${pace}: ${count}`).join(' · ')
}

function formatPracticePaceCounts(counts) {
  if (!Array.isArray(counts) || counts.length === 0) return ''
  return counts
    .map(({ pace, count }) => `${pace}: ${count} practice${count === 1 ? '' : 's'}`)
    .join(' · ')
}

function buildMentorPaceCounts(mentors) {
  const counts = Object.fromEntries(PACE_GROUPS.map((pace) => [pace, 0]))
  let other = 0
  for (const mentor of mentors ?? []) {
    const pace = (mentor.pace ?? '').trim()
    if (Object.hasOwn(PACE_ORDER, pace)) {
      counts[pace] += 1
    } else {
      other += 1
    }
  }
  const rows = PACE_GROUPS.map((pace) => ({ pace, count: counts[pace] }))
  if (other > 0) {
    rows.push({ pace: 'Other', count: other })
  }
  return rows
}

function mentorCountFromPaceCounts(counts) {
  if (!Array.isArray(counts)) return 0
  return counts.reduce((sum, row) => sum + (row.count ?? 0), 0)
}

function effectiveMentorPaceCounts(mentors, counts) {
  const mentorTotal = mentors?.length ?? 0
  const apiTotal = mentorCountFromPaceCounts(counts)
  if (mentorTotal > 0 && apiTotal !== mentorTotal) {
    return buildMentorPaceCounts(mentors)
  }
  if (Array.isArray(counts) && counts.length > 0) {
    return counts
  }
  return buildMentorPaceCounts(mentors)
}

function MentorPaceBreakdownTable({ mentors, counts, caption }) {
  const resolvedCounts = effectiveMentorPaceCounts(mentors, counts)
  const total = mentors?.length ?? mentorCountFromPaceCounts(resolvedCounts)
  if (total === 0) return null
  return (
    <div className="report-pace-breakdown-block">
      {caption ? (
        <p className="muted report-pace-breakdown-label">{caption}</p>
      ) : null}
      <div className="report-table-wrap report-pace-table-wrap">
        <table className="report-table report-pace-table">
          <caption className="sr-only">
            {caption || 'Mentors at this practice by pace'}
          </caption>
          <thead>
            <tr>
              <th scope="col">Pace</th>
              <th scope="col">Mentors</th>
            </tr>
          </thead>
          <tbody>
            {resolvedCounts.map(({ pace, count }) => (
              <tr key={pace} className={count === 0 ? 'report-pace-row-zero' : undefined}>
                <td>{pace}</td>
                <td>{count}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td>{total}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

function EmailResponsePaceTable({ counts }) {
  if (!Array.isArray(counts) || counts.length === 0) return null
  const totals = counts.reduce(
    (acc, row) => ({
      emailed: acc.emailed + (row.emailed ?? 0),
      responded: acc.responded + (row.responded ?? 0),
      pending: acc.pending + (row.pending ?? 0),
    }),
    { emailed: 0, responded: 0, pending: 0 }
  )
  if (totals.emailed === 0) return null
  return (
    <div className="report-pace-breakdown-block">
      <p className="muted report-pace-breakdown-label">
        Mentor email responses by pace
      </p>
      <div className="report-table-wrap report-pace-table-wrap">
        <table className="report-table report-pace-table">
          <caption className="sr-only">Mentor email responses by pace</caption>
          <thead>
            <tr>
              <th scope="col">Pace</th>
              <th scope="col">Emailed</th>
              <th scope="col">Responded</th>
              <th scope="col">Awaiting</th>
            </tr>
          </thead>
          <tbody>
            {counts.map(({ pace, emailed, responded, pending }) => (
              <tr
                key={pace}
                className={emailed === 0 ? 'report-pace-row-zero' : undefined}
              >
                <td>{pace}</td>
                <td>{emailed}</td>
                <td>{responded}</td>
                <td>{pending}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td>{totals.emailed}</td>
              <td>{totals.responded}</td>
              <td>{totals.pending}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const [seasons, setSeasons] = useState([])
  const [report, setReport] = useState([])
  const [pendingReport, setPendingReport] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [seasonFilter, setSeasonFilter] = useState('')
  const [practiceFilter, setPracticeFilter] = useState('')
  /** @type {[SortKey, function(SortKey): void]} */
  const [sortKey, setSortKey] = useState('pace')
  const [sortDirection, setSortDirection] = useState('asc')

  const sortedSeasons = useMemo(
    () =>
      [...seasons].sort(
        (a, b) => Number(b.year) - Number(a.year) || b.id - a.id
      ),
    [seasons]
  )

  useEffect(() => {
    let cancelled = false
    fetchSeasons()
      .then((list) => {
        if (!cancelled) setSeasons(list)
      })
      .catch(() => {
        if (!cancelled) setSeasons([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      fetchPracticeRosterReport(seasonFilter ? { season: seasonFilter } : {}),
      fetchMentorNonResponseReport(seasonFilter ? { season: seasonFilter } : {}),
    ])
      .then(([rosterData, pendingData]) => {
        if (!cancelled) {
          setReport(Array.isArray(rosterData) ? rosterData : [])
          setPendingReport(
            Array.isArray(pendingData?.practices) ? pendingData.practices : []
          )
          setPracticeFilter('')
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setReport([])
          setPendingReport([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [seasonFilter])

  const sortedPendingReport = useMemo(
    () => sortPracticesByDateAsc(pendingReport),
    [pendingReport]
  )

  const filteredPendingReport = useMemo(() => {
    if (!practiceFilter) return sortedPendingReport
    return sortedPendingReport.filter((p) => String(p.id) === practiceFilter)
  }, [sortedPendingReport, practiceFilter])

  const totalPendingMentors = useMemo(
    () =>
      filteredPendingReport.reduce(
        (sum, practice) => sum + (practice.pending_mentors?.length ?? 0),
        0
      ),
    [filteredPendingReport]
  )

  const sortedReport = useMemo(() => sortPracticesByDateAsc(report), [report])

  const filteredReport = useMemo(() => {
    if (!practiceFilter) return sortedReport
    return sortedReport.filter((p) => String(p.id) === practiceFilter)
  }, [sortedReport, practiceFilter])

  const filteredEmailStats = useMemo(() => {
    let mentors_emailed = 0
    let mentors_responded = 0
    for (const practice of filteredPendingReport) {
      mentors_emailed += practice.mentors_emailed ?? 0
      mentors_responded += practice.mentors_responded ?? 0
    }
    return { mentors_emailed, mentors_responded }
  }, [filteredPendingReport])

  const signupSummary = useMemo(
    () => buildMentorSignupSummary(filteredReport),
    [filteredReport]
  )

  const displayPractices = useMemo(
    () => sortPracticePeople(filteredReport, sortKey, sortDirection),
    [filteredReport, sortKey, sortDirection]
  )

  function toggleSort(nextKey) {
    if (sortKey === nextKey) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(nextKey)
      setSortDirection('asc')
    }
  }

  function sortIndicator(key) {
    if (sortKey !== key) return ''
    return sortDirection === 'asc' ? ' ↑' : ' ↓'
  }

  function handleDownloadExcel() {
    const stamp = new Date().toISOString().slice(0, 10)
    downloadExcel(`practice-roster-report-${stamp}.xlsx`, displayPractices)
  }

  return (
    <>
      <AppHeader title="Reports" />

      <main className="panel reports-panel">
        <div className="reports-toolbar">
          <h2>Practice roster</h2>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loading || displayPractices.length === 0}
            onClick={handleDownloadExcel}
          >
            Download Excel
          </button>
        </div>

        <p className="muted reports-intro">
          Coaches and attending mentors for each practice (soonest first). Rows default to pace order within each practice.
        </p>

        <div className="reports-filters">
          <div className="reports-filter">
            <label className="field-label" htmlFor="report-season-filter">
              Season
            </label>
            <select
              id="report-season-filter"
              className="field-input field-select"
              value={seasonFilter}
              onChange={(e) => setSeasonFilter(e.target.value)}
            >
              <option value="">All seasons</option>
              {sortedSeasons.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.year}
                </option>
              ))}
            </select>
          </div>

          <div className="reports-filter">
            <label className="field-label" htmlFor="report-practice-filter">
              Practice
            </label>
            <select
              id="report-practice-filter"
              className="field-input field-select"
              value={practiceFilter}
              onChange={(e) => setPracticeFilter(e.target.value)}
              disabled={loading || sortedReport.length === 0}
            >
              <option value="">All practices</option>
              {sortedReport.map((p) => (
                <option key={p.id} value={String(p.id)}>
                  {p.date ? formatDateTime(p.date) : `Practice #${p.id}`}
                  {p.nyrr_race?.trim() ? ` · ${p.nyrr_race.trim()}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="reports-filter">
            <label className="field-label" htmlFor="report-sort">
              Sort by
            </label>
            <select
              id="report-sort"
              className="field-input field-select"
              value={sortKey}
              onChange={(e) => setSortKey(/** @type {SortKey} */ (e.target.value))}
            >
              <option value="name">Name</option>
              <option value="email">Email</option>
              <option value="pace">Pace</option>
            </select>
          </div>

          <div className="reports-filter reports-filter-sort-dir">
            <label className="field-label" htmlFor="report-sort-dir">
              Direction
            </label>
            <select
              id="report-sort-dir"
              className="field-input field-select"
              value={sortDirection}
              onChange={(e) =>
                setSortDirection(/** @type {'asc' | 'desc'} */ (e.target.value))
              }
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </div>
        </div>

        {!loading && !error && (
          <>
            <div className="reports-stats" aria-label="Email response summary">
              <div className="reports-stat">
                <span className="reports-stat-value">
                  {filteredEmailStats.mentors_emailed}
                </span>
                <span className="reports-stat-label">Mentors emailed</span>
              </div>
              <div className="reports-stat">
                <span className="reports-stat-value">
                  {filteredEmailStats.mentors_responded}
                </span>
                <span className="reports-stat-label">Responded</span>
              </div>
              <div className="reports-stat">
                <span className="reports-stat-value">
                  {Math.max(
                    0,
                    filteredEmailStats.mentors_emailed -
                      filteredEmailStats.mentors_responded
                  )}
                </span>
                <span className="reports-stat-label">Awaiting response</span>
              </div>
              <div className="reports-stat">
                <span className="reports-stat-value">
                  {signupSummary.practicesWithMentors}
                </span>
                <span className="reports-stat-label">Practices with mentors</span>
              </div>
            </div>
            {signupSummary.mentorsByPace.length > 0 ? (
              <p className="muted reports-pace-breakdown">
                Attending mentors by pace (all filtered practices):{' '}
                {formatPaceCounts(signupSummary.mentorsByPace)}
              </p>
            ) : null}
            {signupSummary.practicesByPace.length > 0 ? (
              <p className="muted reports-pace-breakdown">
                Practices with mentors by pace:{' '}
                {formatPracticePaceCounts(signupSummary.practicesByPace)}
              </p>
            ) : null}
          </>
        )}

        {loading && <p className="muted">Loading report…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && displayPractices.length === 0 && (
          <p className="muted">No practices match the current filters.</p>
        )}

        {!loading && !error && signupSummary.mentors.length > 0 && (
          <section
            className="reports-section reports-section-signups"
            aria-labelledby="signup-heading"
          >
            <h2 id="signup-heading">Mentor signups</h2>
            <p className="muted reports-intro">
              Attending mentors and how many practices each has signed up for (soonest practices first in roster below).
            </p>
            <div className="report-table-wrap">
              <table className="report-table">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Email</th>
                    <th scope="col">Pace</th>
                    <th scope="col">Type</th>
                    <th scope="col">Practices signed up</th>
                  </tr>
                </thead>
                <tbody>
                  {signupSummary.mentors.map((mentor) => (
                    <tr key={mentor.mentor_id ?? mentor.email}>
                      <td>{fullName(mentor.first_name, mentor.last_name)}</td>
                      <td>{mentor.email || '—'}</td>
                      <td>{mentor.pace || '—'}</td>
                      <td>{mentor.mentor_type || '—'}</td>
                      <td>{mentor.practice_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!loading && !error && displayPractices.length > 0 && (
          <div className="reports-practice-list">
            {displayPractices.map((practice) => {
              const coachCount = practice.coaches?.length ?? 0
              const mentorCount = practice.mentors?.length ?? 0
              const availableCount = practice.available_mentors?.length ?? 0
              return (
              <section key={practice.id} className="report-practice-block">
                <header className="report-practice-header">
                  <h3>
                    {practice.date ? formatDateTime(practice.date) : `Practice #${practice.id}`}
                  </h3>
                  <p className="muted">
                    Season {practice.season_year ?? practice.season}
                    {practice.nyrr_race?.trim()
                      ? ` · ${practice.nyrr_race.trim()}`
                      : ''}
                    {practice.full_practice ? ' · Full practice' : ' · Partial'}
                    {' · '}
                    {coachCount} coach{coachCount === 1 ? '' : 'es'}
                    {' · '}
                    {mentorCount} mentor{mentorCount === 1 ? '' : 's'}
                    {availableCount > 0
                      ? ` · ${availableCount} available`
                      : ''}
                  </p>
                  <MentorPaceBreakdownTable
                    mentors={practice.mentors}
                    counts={practice.mentor_pace_counts}
                    caption="Mentors at this practice by pace"
                  />
                </header>

                {practice.people.length === 0 ? (
                  <p className="muted">No coaches or mentors assigned.</p>
                ) : (
                  <div className="report-table-wrap">
                    <table className="report-table">
                      <thead>
                        <tr>
                          <th scope="col">Role</th>
                          <th scope="col">
                            <button
                              type="button"
                              className="report-sort-btn"
                              onClick={() => toggleSort('name')}
                            >
                              Name{sortIndicator('name')}
                            </button>
                          </th>
                          <th scope="col">
                            <button
                              type="button"
                              className="report-sort-btn"
                              onClick={() => toggleSort('email')}
                            >
                              Email{sortIndicator('email')}
                            </button>
                          </th>
                          <th scope="col">
                            <button
                              type="button"
                              className="report-sort-btn"
                              onClick={() => toggleSort('pace')}
                            >
                              Pace{sortIndicator('pace')}
                            </button>
                          </th>
                          <th scope="col">Available</th>
                        </tr>
                      </thead>
                      <tbody>
                        {practice.people.map((person, idx) => (
                          <tr key={`${person.role}-${person.email}-${idx}`}>
                            <td>{person.role}</td>
                            <td>{fullName(person.first_name, person.last_name)}</td>
                            <td>{person.email || '—'}</td>
                            <td>{person.pace || '—'}</td>
                            <td>{person.available ? 'X' : ''}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
              )
            })}
          </div>
        )}

        <section className="reports-section reports-section-pending" aria-labelledby="pending-heading">
          <div className="reports-toolbar">
            <h2 id="pending-heading">Mentors without responses</h2>
            {!loading && !error ? (
              <p className="muted reports-pending-summary">
                {totalPendingMentors} mentor
                {totalPendingMentors === 1 ? '' : 's'} still need to respond
              </p>
            ) : null}
          </div>

          <p className="muted reports-intro">
            Mentors on the latest sent email for each practice who have not submitted any reply yet (sorted by pace).
          </p>

          {!loading && !error && filteredPendingReport.length === 0 && (
            <p className="muted">No practices match the current filters.</p>
          )}

          {!loading && !error && filteredPendingReport.length > 0 && (
            <div className="reports-practice-list">
              {filteredPendingReport.map((practice) => (
                <section key={`pending-${practice.id}`} className="report-practice-block">
                  <header className="report-practice-header">
                    <h3>
                      {practice.date
                        ? formatDateTime(practice.date)
                        : `Practice #${practice.id}`}
                    </h3>
                    <p className="muted">
                      Season {practice.season_year ?? practice.season}
                      {practice.nyrr_race?.trim()
                        ? ` · ${practice.nyrr_race.trim()}`
                        : ''}
                      {practice.full_practice ? ' · Full practice' : ' · Partial'}
                      {practice.email_sent && practice.scheduled_send_at
                        ? ` · Email sent ${formatDateTime(practice.scheduled_send_at)}`
                        : ''}
                      {practice.email_sent
                        ? ` · ${practice.mentors_responded ?? 0}/${practice.mentors_emailed ?? 0} responded`
                        : ''}
                    </p>
                    {practice.email_sent ? (
                      <EmailResponsePaceTable counts={practice.response_pace_counts} />
                    ) : null}
                  </header>

                  {!practice.email_sent ? (
                    <p className="muted">No mentor email has been sent for this practice yet.</p>
                  ) : practice.pending_mentors?.length === 0 ? (
                    <p className="muted">All mentors have responded.</p>
                  ) : (
                    <div className="report-table-wrap">
                      <table className="report-table">
                        <thead>
                          <tr>
                            <th scope="col">Name</th>
                            <th scope="col">Email</th>
                            <th scope="col">Pace</th>
                            <th scope="col">Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {practice.pending_mentors.map((mentor) => (
                            <tr key={mentor.mentor_id}>
                              <td>{fullName(mentor.first_name, mentor.last_name)}</td>
                              <td>{mentor.email || '—'}</td>
                              <td>{mentor.pace || '—'}</td>
                              <td>{mentor.mentor_type || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              ))}
            </div>
          )}
        </section>
      </main>
    </>
  )
}
