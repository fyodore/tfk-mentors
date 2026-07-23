import { displayTimeZoneOptions, getDisplayTimeZone } from './timezone.js'

const pad2 = (n) => String(n).padStart(2, '0')

/** @param {number} utcMs @param {string} [timeZone] */
function zonedPartsFromMs(utcMs, timeZone = getDisplayTimeZone()) {
  const d = new Date(utcMs)
  if (Number.isNaN(d.getTime())) return null
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
    hour12: false,
  }).formatToParts(d)
  const pick = (type) => parts.find((p) => p.type === type)?.value
  return {
    year: Number(pick('year')),
    month: Number(pick('month')),
    day: Number(pick('day')),
    hour: Number(pick('hour')),
    minute: Number(pick('minute')),
  }
}

/** Wall clock in the server timezone → UTC epoch ms. */
function zonedWallClockToUtcMs(year, month, day, hour, minute) {
  const timeZone = getDisplayTimeZone()
  const start = Date.UTC(year, month - 1, day, 0) - 16 * 3_600_000
  const end = Date.UTC(year, month - 1, day, 23, 59) + 16 * 3_600_000

  for (let ms = start; ms <= end; ms += 60_000) {
    const parts = zonedPartsFromMs(ms, timeZone)
    if (!parts) continue
    if (
      parts.year === year &&
      parts.month === month &&
      parts.day === day &&
      parts.hour === hour &&
      parts.minute === minute
    ) {
      return ms
    }
  }

  return null
}

/** @param {string|number|Date} iso */
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString(undefined, {
    ...displayTimeZoneOptions(),
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

/** Calendar date YYYY-MM-DD in the display timezone (for filenames, etc.). */
export function formatDateStamp(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date)
  if (Number.isNaN(d.getTime())) return ''
  const parts = zonedPartsFromMs(d.getTime())
  if (!parts) return ''
  return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`
}

/** @param {string|number|Date} iso */
export function formatMentorDirectoryPracticeDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const tz = displayTimeZoneOptions()
  const weekday = d.toLocaleDateString(undefined, { ...tz, weekday: 'short' })
  const datePart = d.toLocaleDateString(undefined, {
    ...tz,
    month: 'short',
    day: 'numeric',
  })
  const timePart = d.toLocaleTimeString(undefined, { ...tz, timeStyle: 'short' })
  return `${weekday}, ${datePart}, ${timePart}`
}

/** @param {string|number|Date} iso @param {string} [nyrrRace] */
export function formatPracticeWhen(iso, nyrrRace) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const tz = displayTimeZoneOptions()
  const datePart = d.toLocaleDateString(undefined, { ...tz, dateStyle: 'medium' })
  const weekday = d.toLocaleDateString(undefined, { ...tz, weekday: 'long' })
  const timePart = d.toLocaleTimeString(undefined, { ...tz, timeStyle: 'short' })
  const when = `${datePart}, ${weekday}, ${timePart}`
  const race = nyrrRace?.trim()
  return race ? `${when} · NYRR Race: ${race}` : when
}

/** @param {number} h @param {number} m */
export function formatWallClockTime(h, m) {
  const iso = dateAndQuarterTimeToIso('2000-01-01', `${pad2(h)}:${pad2(m)}`)
  if (!iso) return `${h}:${pad2(m)}`
  return new Date(iso).toLocaleTimeString(undefined, {
    ...displayTimeZoneOptions(),
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** Quarter-hour slots for practice/email time pickers (server timezone labels). */
export function buildQuarterTimeOptions() {
  const out = []
  for (let q = 0; q < 96; q += 1) {
    const h = Math.floor(q / 4)
    const m = (q % 4) * 15
    const value = `${pad2(h)}:${pad2(m)}`
    out.push({ value, label: formatWallClockTime(h, m) })
  }
  return out
}

/** API datetime → date + quarter-hour in the server timezone. */
export function isoToDateAndQuarterTime(iso) {
  const parts = zonedPartsFromMs(new Date(iso).getTime())
  if (!parts) return { date: '', time: '09:00' }
  const totalMin = parts.hour * 60 + parts.minute
  const snapped = Math.min(23 * 60 + 45, Math.round(totalMin / 15) * 15)
  const hh = Math.floor(snapped / 60)
  const mm = snapped % 60
  return {
    date: `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`,
    time: `${pad2(hh)}:${pad2(mm)}`,
  }
}

/** Date + quarter-hour wall clock in the server timezone → UTC ISO for the API. */
export function dateAndQuarterTimeToIso(dateStr, timeStr) {
  if (!dateStr?.trim() || !timeStr?.trim()) return ''
  const [y, mo, da] = dateStr.split('-').map((x) => Number.parseInt(x, 10))
  const [hh, mm] = timeStr.split(':').map((x) => Number.parseInt(x, 10))
  if ([y, mo, da, hh, mm].some((n) => Number.isNaN(n))) return ''
  const utcMs = zonedWallClockToUtcMs(y, mo, da, hh, mm)
  if (utcMs == null) return ''
  return new Date(utcMs).toISOString()
}

/** Round-trip check for forms: saved ISO should map back to the same wall clock. */
export function wallClockMatchesIso(dateStr, timeStr, iso) {
  if (!iso) return false
  const { date, time } = isoToDateAndQuarterTime(iso)
  return date === dateStr && time === timeStr
}
