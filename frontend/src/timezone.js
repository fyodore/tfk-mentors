/** @type {string | null} */
let serverTimeZone = null

/** Fallback until /api/config/ loads (UTC avoids locale-specific guesses). */
const FALLBACK_TIME_ZONE = 'UTC'

/** @returns {string} */
export function getDisplayTimeZone() {
  return serverTimeZone ?? FALLBACK_TIME_ZONE
}

/** @param {string} timeZone */
export function setDisplayTimeZone(timeZone) {
  if (typeof timeZone === 'string' && timeZone.trim()) {
    serverTimeZone = timeZone.trim()
  }
}

/** @returns {{ timeZone: string }} */
export function displayTimeZoneOptions() {
  return { timeZone: getDisplayTimeZone() }
}
