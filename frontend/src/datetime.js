import { displayTimeZoneOptions, getDisplayTimeZone } from './timezone.js'

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
  const d = new Date(2000, 0, 1, h, m, 0, 0)
  return d.toLocaleTimeString(undefined, {
    ...displayTimeZoneOptions(),
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** @param {string|number|Date} iso */
function zonedParts(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: getDisplayTimeZone(),
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
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

const pad2 = (n) => String(n).padStart(2, '0')

/** API datetime → date + quarter-hour in the server timezone. */
export function isoToDateAndQuarterTime(iso) {
  const parts = zonedParts(iso)
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

function zonedWallClockToUtcMs(year, month, day, hour, minute) {
  let ms = Date.UTC(year, month - 1, day, hour, minute)
  for (let i = 0; i < 8; i += 1) {
    const p = zonedParts(new Date(ms).toISOString())
    if (!p) return null
    if (
      p.year === year &&
      p.month === month &&
      p.day === day &&
      p.hour === hour &&
      p.minute === minute
    ) {
      return ms
    }
    ms += ((hour - p.hour) * 60 + (minute - p.minute)) * 60_000
    ms += (day - p.day) * 86_400_000
  }
  return ms
}
