/** @param {Array<{ id: number, year: number, is_current?: boolean }>} list */
export function sortSeasonsByYearDesc(list) {
  return [...list].sort(
    (a, b) => Number(b.year) - Number(a.year) || b.id - a.id
  )
}

/** @param {Array<{ id: number, year: number, is_current?: boolean }>} seasons */
export function currentSeasonFromList(seasons) {
  if (!Array.isArray(seasons) || seasons.length === 0) return null
  return seasons.find((season) => season.is_current) ?? sortSeasonsByYearDesc(seasons)[0]
}

/** @param {Array<{ date?: string, id?: number }>} practices */
export function splitPracticesByUpcoming(practices) {
  const now = Date.now()
  const upcoming = []
  const past = []

  for (const practice of practices) {
    const when = practice.date ? new Date(practice.date).getTime() : Number.NaN
    if (Number.isNaN(when) || when >= now) {
      upcoming.push(practice)
    } else {
      past.push(practice)
    }
  }

  upcoming.sort((a, b) => {
    const ta = new Date(a.date).getTime()
    const tb = new Date(b.date).getTime()
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || (a.id ?? 0) - (b.id ?? 0)
  })

  past.sort((a, b) => {
    const ta = new Date(a.date).getTime()
    const tb = new Date(b.date).getTime()
    return (Number.isNaN(tb) ? 0 : tb) - (Number.isNaN(ta) ? 0 : ta) || (b.id ?? 0) - (a.id ?? 0)
  })

  return { upcoming, past }
}
