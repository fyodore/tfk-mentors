/** @param {Map<number, number>} seasonYearById @param {Array<{ id: number, seasons?: number[] }>} mentors */
export function recipientSummaryText(row, { seasonYearById, mentors }) {
  const mode =
    row.recipient_mode === 'specific_mentors'
      ? 'specific_mentors'
      : 'all_in_season'
  const stats = row.reply_stats
  const isSent = Boolean(row.task_completed_at)
  const emailed =
    isSent && stats ? stats.mentors_emailed : null
  const replied =
    isSent && stats
      ? (stats.mentors_replied ?? stats.mentors_responded ?? 0)
      : null
  const selectedPractices =
    isSent && stats ? (stats.mentors_selected_practices ?? 0) : null
  const pending =
    isSent && stats ? stats.mentors_pending : null

  function responseSummarySuffix() {
    if (!isSent || !stats) return ''
    return (
      ` · ${replied} replied` +
      ` · ${selectedPractices} selected practice${selectedPractices === 1 ? '' : 's'}` +
      ` · ${pending} awaiting response`
    )
  }

  if (mode === 'specific_mentors') {
    const ids = row.specific_mentors || []
    const count = emailed ?? ids.length
    if (count === 0) {
      return 'Specific mentors — none selected'
    }
    return (
      `Specific mentors (${count} mentor${count === 1 ? '' : 's'} emailed` +
      `${responseSummarySuffix()})`
    )
  }

  const sid = row.recipient_season
  const year = sid != null ? seasonYearById.get(sid) ?? sid : null
  const seasonCount =
    sid != null
      ? mentors.filter(
          (m) => Array.isArray(m.seasons) && m.seasons.includes(sid)
        ).length
      : 0
  const count = emailed ?? seasonCount
  let text = `All mentors in season ${year ?? '—'}`
  if (sid != null || count > 0) {
    text += ` (${count} mentor${count === 1 ? '' : 's'} emailed${responseSummarySuffix()})`
  }
  return text
}

/** @param {number[]} ids @param {(id: number) => string} labelForId */
export function practiceLabelsForIds(ids, labelForId) {
  if (!Array.isArray(ids) || ids.length === 0) {
    return []
  }
  return ids.map((pid) => ({
    id: pid,
    label: labelForId(pid),
  }))
}
