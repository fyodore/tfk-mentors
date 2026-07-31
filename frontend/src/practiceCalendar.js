/**
 * Build and download an .ics calendar of a mentor's assigned practices.
 */

const PRACTICE_DURATION_MS = 2 * 60 * 60 * 1000

/** @param {string} value */
function escapeIcsText(value) {
  return String(value ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

/** @param {Date} date */
function icsUtcStamp(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}` +
    `T${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}Z`
  )
}

/** @param {string} attendance */
function attendanceLabel(attendance) {
  if (attendance === 'first_half') return 'First half'
  if (attendance === 'second_half') return 'Second half'
  return 'Attending'
}

/**
 * @param {{
 *   practice_id: number,
 *   date?: string | null,
 *   nyrr_race?: string | null,
 *   pace?: string | null,
 *   attendance?: string | null,
 * }} practice
 * @param {{ mentorId: number, mentorName: string, stamp: string }} ctx
 */
function buildPracticeEvent(practice, ctx) {
  if (!practice.date) return null
  const start = new Date(practice.date)
  if (Number.isNaN(start.getTime())) return null
  const end = new Date(start.getTime() + PRACTICE_DURATION_MS)

  const race = (practice.nyrr_race || '').trim()
  const summary = race ? `TFK Practice · ${race}` : 'TFK Practice'
  const descParts = [`Mentor: ${ctx.mentorName}`]
  descParts.push(`Status: ${attendanceLabel(practice.attendance)}`)
  if (practice.pace?.trim()) descParts.push(`Pace: ${practice.pace.trim()}`)
  if (race) descParts.push(`NYRR race: ${race}`)

  return [
    'BEGIN:VEVENT',
    `UID:tfk-practice-${practice.practice_id}-mentor-${ctx.mentorId}@tfkmentors`,
    `DTSTAMP:${ctx.stamp}`,
    `DTSTART:${icsUtcStamp(start)}`,
    `DTEND:${icsUtcStamp(end)}`,
    `SUMMARY:${escapeIcsText(summary)}`,
    `DESCRIPTION:${escapeIcsText(descParts.join('\n'))}`,
    'END:VEVENT',
  ].join('\r\n')
}

/**
 * @param {{
 *   mentorId: number,
 *   firstName?: string,
 *   lastName?: string,
 *   practices: Array<{
 *     practice_id: number,
 *     date?: string | null,
 *     nyrr_race?: string | null,
 *     pace?: string | null,
 *     attendance?: string | null,
 *   }>,
 * }} options
 */
export function buildMentorAssignedPracticesIcs(options) {
  const firstName = (options.firstName || '').trim()
  const lastName = (options.lastName || '').trim()
  const mentorName = `${firstName} ${lastName}`.trim() || 'Mentor'
  const stamp = icsUtcStamp(new Date())
  const ctx = { mentorId: options.mentorId, mentorName, stamp }

  const events = (options.practices || [])
    .map((practice) => buildPracticeEvent(practice, ctx))
    .filter(Boolean)

  return (
    [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//TFK Mentors//Mentor Practices//EN',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      `X-WR-CALNAME:${escapeIcsText(`${mentorName} TFK Practices`)}`,
      ...events,
      'END:VCALENDAR',
    ].join('\r\n') + '\r\n'
  )
}

/**
 * @param {'apple' | 'google' | 'outlook'} provider
 * @param {{
 *   mentorId: number,
 *   firstName?: string,
 *   lastName?: string,
 *   practices: Array<object>,
 * }} options
 */
export function downloadMentorAssignedPracticesIcs(provider, options) {
  const practices = Array.isArray(options.practices) ? options.practices : []
  if (practices.length === 0) return false

  const firstName = (options.firstName || '').trim()
  const lastName = (options.lastName || '').trim()
  const base =
    [firstName, lastName].filter(Boolean).join('_').replace(/[^\w.-]+/g, '_') ||
    'mentor'
  const filename = `TFK-${base}-practices-${provider}.ics`

  const blob = new Blob(
    [buildMentorAssignedPracticesIcs({ ...options, practices })],
    { type: 'text/calendar;charset=utf-8' }
  )
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  return true
}
