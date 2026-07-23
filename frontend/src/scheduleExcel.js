import { formatDateTime } from './datetime.js'
import { paceSortKey } from './paceHelpers.js'

const NEEDS_MENTORS_FILL = {
  fill: { patternType: 'solid', fgColor: { rgb: 'FFF8E1' } },
}

function mentorDisplayName(row) {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim() || '—'
}

function practiceLabel(practice) {
  const when = practice.date ? formatDateTime(practice.date) : '—'
  const race = practice.nyrr_race?.trim()
  return race ? `${when} · ${race}` : when
}

function pacesForPractice(practice) {
  const paces = new Set()
  for (const pace of Object.keys(practice.assignments_by_pace ?? {})) {
    if (pace) paces.add(pace)
  }
  for (const pace of Object.keys(practice.available_by_pace ?? {})) {
    if (pace) paces.add(pace)
  }
  for (const group of practice.underfilled_pace_groups ?? []) {
    if (group?.pace) paces.add(group.pace)
  }
  return [...paces].sort(
    (a, b) =>
      paceSortKey(a) - paceSortKey(b) || a.localeCompare(b)
  )
}

/**
 * Build Excel rows for pace fill levels across the preview.
 * @param {{
 *   practices?: Array<{
 *     practice_id?: number,
 *     date?: string,
 *     nyrr_race?: string,
 *     assignments_by_pace?: Record<string, unknown[]>,
 *     available_by_pace?: Record<string, unknown[]>,
 *     underfilled_pace_groups?: Array<{ pace?: string, assigned_count?: number, slots_remaining?: number }>,
 *   }>,
 *   summary?: { max_per_pace?: number },
 * }} result
 */
export function buildPaceSlotRows(result) {
  const maxPerPace = result.summary?.max_per_pace ?? 4
  const header = [
    'Practice',
    'Date',
    'NYRR race',
    'Pace',
    'Filled',
    'Free',
    'Capacity',
    'Status',
  ]
  const rows = [header]
  const needsMentorsRowIndexes = []

  for (const practice of result.practices ?? []) {
    const paces = pacesForPractice(practice)
    if (paces.length === 0) {
      needsMentorsRowIndexes.push(rows.length)
      rows.push([
        practiceLabel(practice),
        practice.date ? formatDateTime(practice.date) : '—',
        practice.nyrr_race?.trim() || '',
        '—',
        0,
        '—',
        maxPerPace,
        'No mentor interest',
      ])
      continue
    }

    const underfilledByPace = new Map(
      (practice.underfilled_pace_groups ?? []).map((group) => [
        group.pace,
        group,
      ])
    )
    for (const pace of paces) {
      const filled =
        underfilledByPace.get(pace)?.assigned_count ??
        (practice.assignments_by_pace?.[pace]?.length ?? 0)
      const free =
        underfilledByPace.get(pace)?.slots_remaining ??
        Math.max(0, maxPerPace - filled)
      const needsMentors = free > 0
      if (needsMentors) {
        needsMentorsRowIndexes.push(rows.length)
      }
      rows.push([
        practiceLabel(practice),
        practice.date ? formatDateTime(practice.date) : '—',
        practice.nyrr_race?.trim() || '',
        pace,
        filled,
        free,
        maxPerPace,
        needsMentors ? 'Needs mentors' : 'Full',
      ])
    }
  }

  return { rows, needsMentorsRowIndexes }
}

/**
 * Build Excel rows for remote mentor practice signups.
 * @param {{
 *   remote_mentors?: Array<{
 *     mentor_id?: number,
 *     first_name?: string,
 *     last_name?: string,
 *     email?: string,
 *     pace?: string,
 *     practices?: Array<{
 *       practice_id?: number,
 *       date?: string,
 *       nyrr_race?: string,
 *       pace?: string,
 *       attendance?: string,
 *     }>,
 *   }>,
 * }} result
 */
export function buildRemoteMentorRows(result) {
  const header = [
    'Mentor',
    'Email',
    'Mentor pace',
    'Practice',
    'Date',
    'NYRR race',
    'Signup pace',
    'Attendance',
  ]
  const rows = [header]
  const mentors = [...(result.remote_mentors ?? [])].sort(
    (a, b) =>
      (a.last_name || '').localeCompare(b.last_name || '') ||
      (a.first_name || '').localeCompare(b.first_name || '')
  )

  for (const mentor of mentors) {
    const practices = [...(mentor.practices ?? [])].sort(
      (a, b) =>
        String(a.date || '').localeCompare(String(b.date || '')) ||
        (a.practice_id ?? 0) - (b.practice_id ?? 0)
    )
    if (practices.length === 0) {
      rows.push([
        mentorDisplayName(mentor),
        mentor.email || '',
        mentor.pace || '',
        '—',
        '—',
        '',
        '',
        '',
      ])
      continue
    }
    for (const practice of practices) {
      rows.push([
        mentorDisplayName(mentor),
        mentor.email || '',
        mentor.pace || '',
        practiceLabel(practice),
        practice.date ? formatDateTime(practice.date) : '—',
        practice.nyrr_race?.trim() || '',
        practice.pace || '',
        practice.attendance || '',
      ])
    }
  }

  return rows
}

/**
 * @param {string} filename
 * @param {object} result schedule preview payload from scheduleMentors()
 */
export async function downloadSchedulePreviewExcel(filename, result) {
  const XLSX = await import('xlsx-js-style')
  const { rows: paceRows, needsMentorsRowIndexes } = buildPaceSlotRows(result)
  const hasRemoteMentors = (result.remote_mentors ?? []).length > 0
  const remoteRows = hasRemoteMentors
    ? buildRemoteMentorRows(result)
    : [
        [
          'Mentor',
          'Email',
          'Mentor pace',
          'Practice',
          'Date',
          'NYRR race',
          'Signup pace',
          'Attendance',
        ],
        ['None', '', '', '', '', '', '', ''],
      ]

  const paceSheet = XLSX.utils.aoa_to_sheet(paceRows)
  for (const rowIndex of needsMentorsRowIndexes) {
    for (let col = 0; col < paceRows[0].length; col += 1) {
      const address = XLSX.utils.encode_cell({ r: rowIndex, c: col })
      const cell = paceSheet[address]
      if (!cell) continue
      cell.s = { ...(cell.s || {}), ...NEEDS_MENTORS_FILL }
    }
  }
  paceSheet['!cols'] = [
    { wch: 36 },
    { wch: 22 },
    { wch: 18 },
    { wch: 10 },
    { wch: 8 },
    { wch: 8 },
    { wch: 10 },
    { wch: 14 },
  ]

  const remoteSheet = XLSX.utils.aoa_to_sheet(remoteRows)
  remoteSheet['!cols'] = [
    { wch: 22 },
    { wch: 28 },
    { wch: 12 },
    { wch: 36 },
    { wch: 22 },
    { wch: 18 },
    { wch: 12 },
    { wch: 12 },
  ]

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, paceSheet, 'Pace slots')
  XLSX.utils.book_append_sheet(workbook, remoteSheet, 'Remote mentors')
  XLSX.writeFile(workbook, filename)
}
