export type SeasonSummary = {
  id: number
  year: number
  is_current?: boolean
}

export type DatedItem = {
  id?: number
  date?: string | null
}

export function sortSeasonsByYearDesc<T extends SeasonSummary>(list: T[]): T[] {
  return [...list].sort(
    (a, b) => Number(b.year) - Number(a.year) || b.id - a.id
  )
}

export function currentSeasonFromList<T extends SeasonSummary>(
  seasons: T[]
): T | null {
  if (!Array.isArray(seasons) || seasons.length === 0) return null
  return (
    seasons.find((season) => season.is_current) ??
    sortSeasonsByYearDesc(seasons)[0]
  )
}

export function splitPracticesByUpcoming<T extends DatedItem>(practices: T[]): {
  upcoming: T[]
  past: T[]
} {
  const now = Date.now()
  const upcoming: T[] = []
  const past: T[] = []

  for (const practice of practices) {
    const when = practice.date ? new Date(practice.date).getTime() : Number.NaN
    if (Number.isNaN(when) || when >= now) {
      upcoming.push(practice)
    } else {
      past.push(practice)
    }
  }

  upcoming.sort((a, b) => {
    const ta = new Date(a.date ?? '').getTime()
    const tb = new Date(b.date ?? '').getTime()
    return (
      (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) ||
      (a.id ?? 0) - (b.id ?? 0)
    )
  })

  past.sort((a, b) => {
    const ta = new Date(a.date ?? '').getTime()
    const tb = new Date(b.date ?? '').getTime()
    return (
      (Number.isNaN(tb) ? 0 : tb) - (Number.isNaN(ta) ? 0 : ta) ||
      (b.id ?? 0) - (a.id ?? 0)
    )
  })

  return { upcoming, past }
}
