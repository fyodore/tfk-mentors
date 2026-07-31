import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  fetchMentorNonResponseReport,
  fetchMentorSwapReport,
  fetchPracticeRosterReport,
  fetchSeasons,
} from '../api'
import { AppHeader } from '../components/AppHeader.tsx'
import { formatDateStamp, formatDateTime } from '../datetime.js'
import {
  currentSeasonFromList,
  sortSeasonsByYearDesc,
} from '../seasonHelpers.js'
import type {
  EmailResponsePaceCount,
  MentorNonResponsePractice,
  MentorSwapReport,
  PracticeRosterReportRow,
  ReportPaceCount,
  ReportRosterPerson,
  Season,
} from '../types.js'

type SortKey = 'name' | 'email' | 'pace'
type SortDirection = 'asc' | 'desc'

type DisplayPerson = ReportRosterPerson & { available?: boolean }

type DisplayPractice = PracticeRosterReportRow & {
  people: DisplayPerson[]
}

type SignupMentor = {
  mentor_id?: number
  first_name?: string | null
  last_name?: string | null
  email?: string | null
  pace?: string | null
  mentor_type?: string | null
  practice_count: number
}

type CellStyle = {
  fill?: { patternType: string; fgColor: { rgb: string } }
  alignment?: { horizontal: string }
  font?: { bold?: boolean }
}

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
const AVAILABLE_COLUMN_INDEX = ROSTER_HEADERS.indexOf('Available')

const AVAILABLE_CELL_FILL = {
  fill: {
    patternType: 'solid',
    fgColor: { rgb: 'FFFF00' },
  },
  alignment: { horizontal: 'center' },
}

function mentorPaceCountCellStyle(count: number): CellStyle | null {
  let rgb: string | null = null
  if (count <= 2) rgb = 'FF6B6B' // red
  else if (count === 3) rgb = 'FFE066' // yellow
  else if (count === 4) rgb = '69DB7C' // green
  else if (count >= 5) rgb = 'B197FC' // purple
  if (!rgb) return null
  return {
    fill: {
      patternType: 'solid',
      fgColor: { rgb },
    },
    alignment: { horizontal: 'center' },
    font: { bold: true },
  }
}

const PACE_ORDER: Record<string, number> = {
  '8-9': 1,
  '9-10': 2,
  '10-11': 3,
  '11-12': 4,
  '12-13': 5,
  '13+': 6,
}


function fullName(first?: string | null, last?: string | null): string {
  return `${first ?? ''} ${last ?? ''}`.trim()
}

function comparePeople(
  a: DisplayPerson,
  b: DisplayPerson,
  sortKey: SortKey,
  direction: SortDirection
): number {
  const sign = direction === 'asc' ? 1 : -1
  if (sortKey === 'name') {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln * sign
    return (a.first_name || '').localeCompare(b.first_name || '') * sign
  }
  if (sortKey === 'email') {
    return (a.email || '').localeCompare(b.email || '') * sign
  }
  const pa = PACE_ORDER[a.pace ?? ''] ?? 99
  const pb = PACE_ORDER[b.pace ?? ''] ?? 99
  if (pa !== pb) return (pa - pb) * sign
  return fullName(a.first_name, a.last_name).localeCompare(
    fullName(b.first_name, b.last_name)
  )
}

function sortPracticesByDateAsc<T extends { date?: string | null; id?: number }>(
  practices: T[]
): T[] {
  return [...practices].sort((a, b) => {
    const ta = a.date ? new Date(a.date).getTime() : 0
    const tb = b.date ? new Date(b.date).getTime() : 0
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || (a.id ?? 0) - (b.id ?? 0)
  })
}

function sortPracticePeople(
  practices: PracticeRosterReportRow[],
  sortKey: SortKey,
  direction: SortDirection
): DisplayPractice[] {
  return practices.map((practice) => {
    const attendingMentors = (practice.mentors ?? []).map((mentor) => ({
      ...mentor,
      available: false,
    }))
    const availableMentors = (practice.available_mentors ?? []).map((mentor) => ({
      ...mentor,
      available: true,
    }))
    const people: DisplayPerson[] = [
      ...(practice.coaches ?? []),
      ...attendingMentors,
      ...availableMentors,
    ]
    people.sort((a, b) => comparePeople(a, b, sortKey, direction))
    return { ...practice, people }
  })
}

function buildRosterRows(practices: DisplayPractice[]): (string | number)[][] {
  const rows: (string | number)[][] = [ROSTER_HEADERS]
  for (const practice of practices) {
    const when = practice.date ? formatDateTime(practice.date) : ''
    for (const person of practice.people) {
      rows.push([
        when,
        practice.season_year ?? practice.season ?? '',
        practice.nyrr_race ?? '',
        person.role,
        person.first_name ?? '',
        person.last_name ?? '',
        person.email ?? '',
        person.pace ?? '',
        person.available ? 'X' : '',
      ])
    }
  }
  return rows
}

async function downloadExcel(filename: string, practices: DisplayPractice[]) {
  const XLSX = await import('xlsx-js-style')
  const rows = buildRosterRows(practices)
  const worksheet = XLSX.utils.aoa_to_sheet(rows)

  for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
    const paceCellAddress = XLSX.utils.encode_cell({
      r: rowIndex,
      c: PACE_COLUMN_INDEX,
    })
    const paceCell = worksheet[paceCellAddress]
    if (paceCell) {
      paceCell.t = 's'
      paceCell.v = String(paceCell.v ?? '')
      paceCell.z = '@'
    }

    if (rows[rowIndex][AVAILABLE_COLUMN_INDEX] === 'X') {
      const availableCellAddress = XLSX.utils.encode_cell({
        r: rowIndex,
        c: AVAILABLE_COLUMN_INDEX,
      })
      const availableCell = worksheet[availableCellAddress]
      if (availableCell) {
        availableCell.s = AVAILABLE_CELL_FILL
      }
    }
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

async function downloadMentorNumberSummaryExcel(
  filename: string,
  practices: PracticeRosterReportRow[],
  options: { includeSeasonColumn?: boolean } = {}
) {
  const XLSX = await import('xlsx-js-style')
  const includeSeason = Boolean(options.includeSeasonColumn)
  const sorted = sortPracticesByDateAsc(practices)

  const header = [
    ...(includeSeason ? ['Season'] : []),
    'Practice Date',
    'NYRR Race',
    ...PACE_GROUPS,
    'Total',
  ]
  const rows: (string | number)[][] = [header]
  const columnTotals: Record<string, number> = Object.fromEntries(PACE_GROUPS.map((pace) => [pace, 0]))
  let grandTotal = 0

  for (const practice of sorted) {
    const countsByPace: Record<string, number> = Object.fromEntries(PACE_GROUPS.map((pace) => [pace, 0]))
    if (Array.isArray(practice.mentor_pace_counts) && practice.mentor_pace_counts.length) {
      for (const row of practice.mentor_pace_counts) {
        const pace = row.pace?.trim() || ''
        if (pace in countsByPace) {
          countsByPace[pace] = Number(row.count) || 0
        }
      }
    } else {
      for (const mentor of practice.mentors ?? []) {
        const pace = mentor.pace?.trim() || ''
        if (pace in countsByPace) countsByPace[pace] += 1
      }
    }
    const total = PACE_GROUPS.reduce((sum, pace) => sum + countsByPace[pace], 0)
    for (const pace of PACE_GROUPS) {
      columnTotals[pace] += countsByPace[pace]
    }
    grandTotal += total
    rows.push([
      ...(includeSeason ? [practice.season_year ?? practice.season ?? ''] : []),
      practice.date ? formatDateTime(practice.date) : '',
      practice.nyrr_race ?? '',
      ...PACE_GROUPS.map((pace) => countsByPace[pace]),
      total,
    ])
  }

  rows.push([
    ...(includeSeason ? [''] : []),
    'Total',
    '',
    ...PACE_GROUPS.map((pace) => columnTotals[pace]),
    grandTotal,
  ])

  const worksheet = XLSX.utils.aoa_to_sheet(rows)
  worksheet['!cols'] = [
    ...(includeSeason ? [{ wch: 8 }] : []),
    { wch: 24 },
    { wch: 22 },
    ...PACE_GROUPS.map(() => ({ wch: 8 })),
    { wch: 8 },
  ]

  const paceStartCol = includeSeason ? 3 : 2
  const totalRowIndex = rows.length - 1
  for (let c = 0; c < header.length; c += 1) {
    const headerAddr = XLSX.utils.encode_cell({ r: 0, c })
    if (worksheet[headerAddr]) {
      worksheet[headerAddr].s = { font: { bold: true } }
    }
    const totalAddr = XLSX.utils.encode_cell({ r: totalRowIndex, c })
    if (worksheet[totalAddr]) {
      worksheet[totalAddr].s = { font: { bold: true } }
    }
  }

  // Color pace-count cells on practice rows (not header or totals).
  for (let rowIndex = 1; rowIndex < totalRowIndex; rowIndex += 1) {
    for (let paceIndex = 0; paceIndex < PACE_GROUPS.length; paceIndex += 1) {
      const col = paceStartCol + paceIndex
      const addr = XLSX.utils.encode_cell({ r: rowIndex, c: col })
      const cell = worksheet[addr]
      if (!cell) continue
      const count = Number(cell.v) || 0
      const style = mentorPaceCountCellStyle(count)
      if (style) cell.s = style
    }
  }

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Mentor numbers')
  XLSX.writeFile(workbook, filename)
}

function buildMentorSignupSummary(practices: PracticeRosterReportRow[]) {
  const mentorById = new Map<string | number, SignupMentor>()
  const paceToPracticeIds = new Map<string, Set<number>>(
    PACE_GROUPS.map((pace) => [pace, new Set<number>()])
  )
  let practicesWithMentors = 0

  for (const practice of practices) {
    const mentors = practice.mentors ?? []
    if (mentors.length === 0) continue
    practicesWithMentors += 1
    const pacesInPractice = new Set<string>()
    for (const mentor of mentors) {
      const pace = mentor.pace?.trim() || ''
      if (PACE_ORDER[pace]) pacesInPractice.add(pace)
      const key =
        mentor.mentor_id ??
        mentor.email ??
        fullName(mentor.first_name, mentor.last_name)
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
      const entry = mentorById.get(key)
      if (entry) entry.practice_count += 1
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

function formatPaceCounts(counts: ReportPaceCount[] | null | undefined): string {
  if (!Array.isArray(counts) || counts.length === 0) return ''
  return counts.map(({ pace, count }) => `${pace}: ${count}`).join(' · ')
}

function formatPracticePaceCounts(counts: ReportPaceCount[] | null | undefined): string {
  if (!Array.isArray(counts) || counts.length === 0) return ''
  return counts
    .map(({ pace, count }) => `${pace}: ${count} practice${count === 1 ? '' : 's'}`)
    .join(' · ')
}

function buildMentorPaceCounts(mentors: ReportRosterPerson[] | null | undefined): ReportPaceCount[] {
  const counts: Record<string, number> = Object.fromEntries(PACE_GROUPS.map((pace) => [pace, 0]))
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

function mentorCountFromPaceCounts(counts: ReportPaceCount[] | null | undefined): number {
  if (!Array.isArray(counts)) return 0
  return counts.reduce((sum, row) => sum + (row.count ?? 0), 0)
}

function effectiveMentorPaceCounts(
  mentors: ReportRosterPerson[] | null | undefined,
  counts: ReportPaceCount[] | null | undefined
): ReportPaceCount[] {
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

function MentorPaceBreakdownTable({
  mentors,
  counts,
  caption,
}: {
  mentors?: ReportRosterPerson[] | null
  counts?: ReportPaceCount[] | null
  caption?: string
}) {
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

function EmailResponsePaceTable({
  counts,
}: {
  counts?: EmailResponsePaceCount[] | null
}) {
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
  const [searchParams] = useSearchParams()
  const [seasons, setSeasons] = useState<Season[]>([])
  const [report, setReport] = useState<PracticeRosterReportRow[]>([])
  const [pendingReport, setPendingReport] = useState<MentorNonResponsePractice[]>([])
  const [swapReport, setSwapReport] = useState<MentorSwapReport>({
    approved: [],
    rejected: [],
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedApprovedSwapId, setSelectedApprovedSwapId] = useState<number | null>(null)
  const [selectedRejectedSwapId, setSelectedRejectedSwapId] = useState<number | null>(null)

  const [seasonFilter, setSeasonFilter] = useState('')
  const [seasonFilterReady, setSeasonFilterReady] = useState(false)
  const [practiceFilter, setPracticeFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('pace')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [exporting, setExporting] = useState<null | 'roster' | 'summary'>(null)

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

  useEffect(() => {
    let cancelled = false
    fetchSeasons()
      .then((list) => {
        if (cancelled) return
        const orderedSeasons = sortSeasonsByYearDesc(list)
        setSeasons(orderedSeasons)
        const current = currentSeasonFromList(orderedSeasons)
        if (current) {
          setSeasonFilter(String(current.id))
        }
        setSeasonFilterReady(true)
      })
      .catch(() => {
        if (!cancelled) {
          setSeasons([])
          setSeasonFilterReady(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!seasonFilterReady) return
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      fetchPracticeRosterReport(seasonFilter ? { season: seasonFilter } : {}),
      fetchMentorNonResponseReport(seasonFilter ? { season: seasonFilter } : {}),
      fetchMentorSwapReport(seasonFilter ? { season: seasonFilter } : {}),
    ])
      .then(([rosterData, pendingData, swapData]) => {
        if (!cancelled) {
          setReport(Array.isArray(rosterData) ? rosterData : [])
          setPendingReport(
            Array.isArray(pendingData?.practices) ? pendingData.practices : []
          )
          setSwapReport({
            approved: Array.isArray(swapData?.approved) ? swapData.approved : [],
            rejected: Array.isArray(swapData?.rejected) ? swapData.rejected : [],
          })
          setPracticeFilter('')
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setReport([])
          setPendingReport([])
          setSwapReport({ approved: [], rejected: [] })
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [seasonFilter, seasonFilterReady])

  useEffect(() => {
    if (loading) return
    const section = searchParams.get('section')
    if (section !== 'mentor-swaps') return
    const swapId = Number.parseInt(String(searchParams.get('swap') || ''), 10)
    const status = searchParams.get('status')
    if (Number.isFinite(swapId) && swapId > 0) {
      if (status === 'rejected') setSelectedRejectedSwapId(swapId)
      else if (status === 'approved') setSelectedApprovedSwapId(swapId)
    }
    const el = document.getElementById('mentor-swaps-heading')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [loading, searchParams, swapReport])

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

  function toggleSort(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(nextKey)
      setSortDirection('asc')
    }
  }

  function sortIndicator(key: SortKey): string {
    if (sortKey !== key) return ''
    return sortDirection === 'asc' ? ' ↑' : ' ↓'
  }

  async function handleDownloadExcel() {
    const stamp = formatDateStamp()
    setExporting('roster')
    setError(null)
    try {
      await downloadExcel(`practice-roster-report-${stamp}.xlsx`, displayPractices)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(null)
    }
  }

  async function handleDownloadMentorNumberSummary() {
    const stamp = formatDateStamp()
    const season = sortedSeasons.find((s) => String(s.id) === seasonFilter)
    const yearPart = season?.year ? `${season.year}-` : ''
    setExporting('summary')
    setError(null)
    try {
      await downloadMentorNumberSummaryExcel(
        `mentor-number-summary-${yearPart}${stamp}.xlsx`,
        sortedReport,
        { includeSeasonColumn: !seasonFilter }
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(null)
    }
  }

  return (
    <>
      <AppHeader title="Reports" />

      <main className="panel reports-panel">
        <div className="reports-toolbar">
          <h2>Practice roster</h2>
          <div className="reports-toolbar-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading || exporting !== null || sortedReport.length === 0}
              onClick={handleDownloadMentorNumberSummary}
              title={
                seasonFilter
                  ? 'Excel: mentor counts by pace for each practice in this season'
                  : 'Excel: mentor counts by pace for each practice (all seasons)'
              }
            >
              {exporting === 'summary'
                ? 'Preparing…'
                : 'Download mentor number summary'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading || exporting !== null || displayPractices.length === 0}
              onClick={handleDownloadExcel}
            >
              {exporting === 'roster' ? 'Preparing…' : 'Download Excel'}
            </button>
          </div>
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
                  {s.is_current ? ' (current)' : ''}
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
              onChange={(e) => setSortKey(e.target.value as SortKey)}
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
                setSortDirection(e.target.value as SortDirection)
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
                          {(practice.pending_mentors ?? []).map((mentor) => (
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

        <section
          className="reports-section reports-section-swaps"
          aria-labelledby="mentor-swaps-heading"
        >
          <div className="reports-toolbar">
            <h2 id="mentor-swaps-heading">Mentor Swap</h2>
          </div>
          <p className="muted reports-intro">
            Approved and rejected swap requests from the mentor directory.
          </p>

          {!loading && !error ? (
            <>
              <h3 className="reports-swap-subheading">Approved swaps</h3>
              {swapReport.approved.length === 0 ? (
                <p className="muted">No approved swaps for this season.</p>
              ) : (
                <ul className="reports-swap-list">
                  {swapReport.approved.map((row) => {
                    const open = selectedApprovedSwapId === row.id
                    const outgoing = row.outgoing_mentor || {}
                    const incoming = row.incoming_mentor || {}
                    return (
                      <li key={`approved-${row.id}`} className="reports-swap-item">
                        <button
                          type="button"
                          className={`reports-swap-summary${open ? ' is-open' : ''}`}
                          onClick={() =>
                            setSelectedApprovedSwapId(open ? null : row.id)
                          }
                        >
                          <span>
                            {row.practice_date
                              ? formatDateTime(row.practice_date)
                              : `Practice #${row.practice_id}`}
                          </span>
                          <span className="muted">
                            {row.decided_at
                              ? formatDateTime(row.decided_at)
                              : '—'}
                          </span>
                          <span>
                            {outgoing.last_name || '—'}/{incoming.last_name || '—'}
                          </span>
                        </button>
                        {open ? (
                          <div className="reports-swap-detail">
                            <p>
                              Original: {fullName(outgoing.first_name, outgoing.last_name)}
                              {outgoing.pace ? ` · Pace ${outgoing.pace}` : ''}
                            </p>
                            <p>
                              Replacement:{' '}
                              {fullName(incoming.first_name, incoming.last_name)}
                              {incoming.pace ? ` · Pace ${incoming.pace}` : ''}
                            </p>
                            {row.nyrr_race ? (
                              <p className="muted">NYRR race: {row.nyrr_race}</p>
                            ) : null}
                          </div>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              )}

              <h3 className="reports-swap-subheading">Rejected swaps</h3>
              {swapReport.rejected.length === 0 ? (
                <p className="muted">No rejected swaps for this season.</p>
              ) : (
                <ul className="reports-swap-list">
                  {swapReport.rejected.map((row) => {
                    const open = selectedRejectedSwapId === row.id
                    const outgoing = row.outgoing_mentor || {}
                    const incoming = row.incoming_mentor || {}
                    return (
                      <li
                        key={`rejected-${row.id}`}
                        id={`mentor-swap-${row.id}`}
                        className="reports-swap-item"
                      >
                        <button
                          type="button"
                          className={`reports-swap-summary${open ? ' is-open' : ''}`}
                          onClick={() =>
                            setSelectedRejectedSwapId(open ? null : row.id)
                          }
                        >
                          <span>
                            {row.practice_date
                              ? formatDateTime(row.practice_date)
                              : `Practice #${row.practice_id}`}
                          </span>
                          <span className="muted">
                            {row.decided_at
                              ? formatDateTime(row.decided_at)
                              : '—'}
                          </span>
                          <span>
                            {outgoing.last_name || '—'}/{incoming.last_name || '—'}
                          </span>
                        </button>
                        {open ? (
                          <div className="reports-swap-detail">
                            <p>
                              Original: {fullName(outgoing.first_name, outgoing.last_name)}
                              {outgoing.pace ? ` · Pace ${outgoing.pace}` : ''}
                            </p>
                            <p>
                              Requested:{' '}
                              {fullName(incoming.first_name, incoming.last_name)}
                              {incoming.pace ? ` · Pace ${incoming.pace}` : ''}
                            </p>
                            <p>
                              Comments:{' '}
                              {(row.reject_comments || '').trim() || '(none)'}
                            </p>
                          </div>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              )}
            </>
          ) : null}
        </section>
      </main>
    </>
  )
}
