export const PACE_GROUPS = ['8-9', '9-10', '10-11', '11-12', '12-13', '13+']

export const PACE_ORDER = Object.fromEntries(
  PACE_GROUPS.map((pace, index) => [pace, index])
)

/** @param {string | undefined | null} pace */
export function paceSortKey(pace) {
  return PACE_ORDER[pace ?? ''] ?? 99
}

/** @param {{ pace?: string, first_name?: string, last_name?: string }} a @param {{ pace?: string, first_name?: string, last_name?: string }} b */
export function compareByPaceThenName(a, b) {
  const pa = paceSortKey(a.pace)
  const pb = paceSortKey(b.pace)
  if (pa !== pb) return pa - pb
  const ln = (a.last_name || '').localeCompare(b.last_name || '')
  if (ln !== 0) return ln
  return (a.first_name || '').localeCompare(b.first_name || '')
}

/** @template T @param {T[]} list @returns {T[]} */
export function sortByPaceThenName(list) {
  return [...list].sort(compareByPaceThenName)
}
