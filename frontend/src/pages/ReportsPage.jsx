import { useEffect, useMemo, useState } from 'react'
import * as XLSX from 'xlsx'

import { fetchPracticeRosterReport, fetchSeasons } from '../api'
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

/** @param {Array<{ coaches?: unknown[], mentors?: unknown[] }>} practices */
function sortPracticePeople(practices, sortKey, direction) {
  return practices.map((practice) => {
    const people = [...(practice.coaches ?? []), ...(practice.mentors ?? [])]
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
  ]

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Practice roster')
  XLSX.writeFile(workbook, filename)
}

export default function ReportsPage() {
  const [seasons, setSeasons] = useState([])
  const [report, setReport] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [seasonFilter, setSeasonFilter] = useState('')
  const [practiceFilter, setPracticeFilter] = useState('')
  /** @type {[SortKey, function(SortKey): void]} */
  const [sortKey, setSortKey] = useState('name')
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
    fetchPracticeRosterReport(
      seasonFilter ? { season: seasonFilter } : {}
    )
      .then((data) => {
        if (!cancelled) {
          setReport(Array.isArray(data) ? data : [])
          setPracticeFilter('')
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setReport([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [seasonFilter])

  const filteredReport = useMemo(() => {
    if (!practiceFilter) return report
    return report.filter((p) => String(p.id) === practiceFilter)
  }, [report, practiceFilter])

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
          Coaches and attending mentors for each practice. Sort rows by name, email, or pace.
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
              disabled={loading || report.length === 0}
            >
              <option value="">All practices</option>
              {report.map((p) => (
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

        {loading && <p className="muted">Loading report…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && displayPractices.length === 0 && (
          <p className="muted">No practices match the current filters.</p>
        )}

        {!loading && !error && displayPractices.length > 0 && (
          <div className="reports-practice-list">
            {displayPractices.map((practice) => (
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
                    {practice.people.length} attendee
                    {practice.people.length === 1 ? '' : 's'}
                  </p>
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
                        </tr>
                      </thead>
                      <tbody>
                        {practice.people.map((person, idx) => (
                          <tr key={`${person.role}-${person.email}-${idx}`}>
                            <td>{person.role}</td>
                            <td>{fullName(person.first_name, person.last_name)}</td>
                            <td>{person.email || '—'}</td>
                            <td>{person.pace || '—'}</td>
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
      </main>
    </>
  )
}
