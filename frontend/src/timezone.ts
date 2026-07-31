let serverTimeZone: string | null = null

/** Fallback until /api/config/ loads (UTC avoids locale-specific guesses). */
const FALLBACK_TIME_ZONE = 'UTC'

export function getDisplayTimeZone(): string {
  return serverTimeZone ?? FALLBACK_TIME_ZONE
}

export function setDisplayTimeZone(timeZone: string): void {
  if (typeof timeZone === 'string' && timeZone.trim()) {
    serverTimeZone = timeZone.trim()
  }
}

export function displayTimeZoneOptions(): { timeZone: string } {
  return { timeZone: getDisplayTimeZone() }
}
