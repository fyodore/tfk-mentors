/** @param {Map<number, number>} seasonYearById @param {Array<{ id: number, seasons?: number[] }>} mentors */
export function scheduledRecipientCount(row, mentors) {
  const mode =
    row.recipient_mode === 'specific_mentors'
      ? 'specific_mentors'
      : 'all_in_season'
  if (mode === 'specific_mentors') {
    return (row.specific_mentors || []).length
  }
  const sid = row.recipient_season
  if (sid == null) return 0
  return mentors.filter(
    (m) => Array.isArray(m.seasons) && m.seasons.includes(sid)
  ).length
}

/** @param {Map<number, number>} seasonYearById @param {Array<{ id: number, seasons?: number[] }>} mentors */
export function recipientSummaryText(row, { seasonYearById, mentors }) {
  const mode =
    row.recipient_mode === 'specific_mentors'
      ? 'specific_mentors'
      : 'all_in_season'
  const stats = row.reply_stats
  const isSent = Boolean(row.task_completed_at)
  const scheduledCount = scheduledRecipientCount(row, mentors)
  const emailedCount =
    isSent && stats?.mentors_emailed != null
      ? Math.max(stats.mentors_emailed, scheduledCount)
      : scheduledCount
  const countLabel = isSent ? 'emailed' : 'scheduled'
  const count = isSent ? emailedCount : scheduledCount
  const replied =
    isSent && stats
      ? (stats.mentors_replied ?? stats.mentors_responded ?? 0)
      : null
  const selectedPractices =
    isSent && stats ? (stats.mentors_selected_practices ?? 0) : null
  const pending =
    isSent && stats
      ? (stats.mentors_pending ??
        Math.max(0, emailedCount - (replied ?? 0)))
      : null

  function responseSummarySuffix() {
    if (!isSent) return ''
    return (
      ` · ${replied ?? 0} replied` +
      ` · ${selectedPractices ?? 0} selected practice${selectedPractices === 1 ? '' : 's'}` +
      ` · ${pending ?? 0} awaiting response`
    )
  }

  if (mode === 'specific_mentors') {
    if (count === 0) {
      return 'Specific mentors — none selected'
    }
    return (
      `Specific mentors (${count} mentor${count === 1 ? '' : 's'} ${countLabel}` +
      `${responseSummarySuffix()})`
    )
  }

  const sid = row.recipient_season
  const year = sid != null ? seasonYearById.get(sid) ?? sid : null
  let text = `All mentors in season ${year ?? '—'}`
  if (sid != null || count > 0) {
    text += ` (${count} mentor${count === 1 ? '' : 's'} ${countLabel}${responseSummarySuffix()})`
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

/** @param {{ first_name?: string, last_name?: string, email?: string, id?: number, name?: string }} mentor */
export function formatMentorName(mentor) {
  if (mentor?.name?.trim()) return mentor.name.trim()
  const name = [mentor?.first_name, mentor?.last_name]
    .filter(Boolean)
    .join(' ')
    .trim()
  if (name) return name
  if (mentor?.email?.trim()) return mentor.email.trim()
  return mentor?.id != null ? `Mentor #${mentor.id}` : 'Unknown mentor'
}

/** @param {{ pending_mentors?: Array<{ id: number, first_name?: string, last_name?: string, name?: string, email?: string, type?: string }>, reply_stats?: { pending_mentor_ids?: number[], pending_mentors?: Array<{ id: number, first_name?: string, last_name?: string, name?: string, email?: string, type?: string }> } }} email @param {Array<{ id: number, first_name?: string, last_name?: string, email?: string, type?: string }>} mentors */
export function pendingMentorsForEmail(email, mentors) {
  const fromStats = email?.reply_stats?.pending_mentors
  if (Array.isArray(fromStats) && fromStats.length > 0) {
    return fromStats.map((m) => ({
      id: m.id,
      name: formatMentorName(m),
      email: m.email ?? '',
      type: m.type ?? '',
    }))
  }

  const fromApi = email?.pending_mentors
  if (Array.isArray(fromApi) && fromApi.length > 0) {
    return fromApi.map((m) => ({
      id: m.id,
      name: formatMentorName(m),
      email: m.email ?? '',
      type: m.type ?? '',
    }))
  }

  const pendingIds = email?.reply_stats?.pending_mentor_ids
  if (!Array.isArray(pendingIds) || pendingIds.length === 0 || !mentors?.length) {
    return []
  }

  const byId = new Map(mentors.map((m) => [m.id, m]))
  return pendingIds
    .map((id) => byId.get(id))
    .filter(Boolean)
    .sort(
      (a, b) =>
        (a.last_name ?? '').localeCompare(b.last_name ?? '') ||
        (a.first_name ?? '').localeCompare(b.first_name ?? '') ||
        a.id - b.id
    )
    .map((m) => ({
      id: m.id,
      name: formatMentorName(m),
      email: m.email ?? '',
      type: m.type ?? '',
    }))
}

/** @param {{ task_completed_at?: string|null, reply_stats?: { mentors_replied?: number, mentors_responded?: number, mentors_selected_practices?: number, mentors_pending?: number, mentors_emailed?: number, pending_mentor_ids?: number[] }, recipient_mode?: string, recipient_season?: number|null, specific_mentors?: number[] }} row @param {{ emailedCount?: number }} [options] */
export function sentEmailReplyStats(row, options = {}) {
  if (!row.task_completed_at) return null
  const stats = row.reply_stats ?? {}
  const emailedFromStats = stats.mentors_emailed ?? 0
  const emailed = Math.max(emailedFromStats, options.emailedCount ?? 0)
  const replied = stats.mentors_replied ?? stats.mentors_responded ?? 0
  const pendingIds = stats.pending_mentor_ids
  const pendingFromIds = Array.isArray(pendingIds) ? pendingIds.length : null
  const pendingFromStats = stats.mentors_pending
  const pending =
    pendingFromIds != null && pendingFromIds > 0
      ? pendingFromIds
      : pendingFromStats != null && pendingFromStats > 0
        ? pendingFromStats
        : Math.max(0, emailed - replied)
  return {
    emailed,
    replied,
    selectedPractices: stats.mentors_selected_practices ?? 0,
    pending,
  }
}
