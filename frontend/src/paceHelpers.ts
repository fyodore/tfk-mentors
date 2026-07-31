export const PACE_GROUPS = ['8-9', '9-10', '10-11', '11-12', '12-13', '13+'] as const

export type PaceGroup = (typeof PACE_GROUPS)[number]

export const PACE_ORDER: Record<string, number> = Object.fromEntries(
  PACE_GROUPS.map((pace, index) => [pace, index])
)

export type PaceSortable = {
  pace?: string | null
  first_name?: string | null
  last_name?: string | null
}

export function paceSortKey(pace?: string | null): number {
  return PACE_ORDER[pace ?? ''] ?? 99
}

export function compareByPaceThenName(a: PaceSortable, b: PaceSortable): number {
  const pa = paceSortKey(a.pace)
  const pb = paceSortKey(b.pace)
  if (pa !== pb) return pa - pb
  const ln = (a.last_name || '').localeCompare(b.last_name || '')
  if (ln !== 0) return ln
  return (a.first_name || '').localeCompare(b.first_name || '')
}

export function sortByPaceThenName<T extends PaceSortable>(list: T[]): T[] {
  return [...list].sort(compareByPaceThenName)
}
