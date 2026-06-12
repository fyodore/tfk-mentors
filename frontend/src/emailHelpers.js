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
  const emailedFromStats = stats?.mentors_emailed
  const emailedFromField = row.recipients_emailed_count
  const emailedCount = isSent
    ? (emailedFromStats ??
      (emailedFromField != null ? emailedFromField : null))
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
        (stats.pending_mentor_ids?.length ?? null) ??
        (stats.mentors_emailed != null
          ? Math.max(0, stats.mentors_emailed - (replied ?? 0))
          : null))
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
    if (count === 0 || count == null) {
      return isSent && count == null
        ? 'Specific mentors — sent (recipient count unavailable)'
        : 'Specific mentors — none selected'
    }
    return (
      `Specific mentors (${count} mentor${count === 1 ? '' : 's'} ${countLabel}` +
      `${responseSummarySuffix()})`
    )
  }

  const sid = row.recipient_season
  const year = sid != null ? seasonYearById.get(sid) ?? sid : null
  let text = `All mentors in season ${year ?? '—'}`
  if (isSent && count == null) {
    text += ' (sent — recipient count unavailable'
    return text + `${responseSummarySuffix()})`
  }
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

/** @param {{ practices?: Array<{ id: number, scheduled_email_id?: number|null, pending_mentors?: Array<{ mentor_id?: number, id?: number, first_name?: string, last_name?: string, email?: string, mentor_type?: string, type?: string }> }> }} report @param {number} emailId @param {number[]} practiceIds */
export function pendingMentorsFromNonResponseReport(report, emailId, practiceIds) {
  const practiceIdSet = new Set(practiceIds)
  const practices = (report?.practices ?? []).filter((practice) => {
    if (!practiceIdSet.has(practice.id)) return false
    if (
      practice.scheduled_email_id != null &&
      practice.scheduled_email_id !== emailId
    ) {
      return false
    }
    return true
  })
  if (practices.length === 0) return []

  const pendingLists = practices.map((practice) => practice.pending_mentors ?? [])
  const mentorKey = (row) => row.mentor_id ?? row.id

  let sharedIds = new Set(
    (pendingLists[0] ?? []).map(mentorKey).filter((id) => id != null)
  )
  for (let i = 1; i < pendingLists.length; i += 1) {
    const practiceIdsSet = new Set(
      (pendingLists[i] ?? []).map(mentorKey).filter((id) => id != null)
    )
    sharedIds = new Set([...sharedIds].filter((id) => practiceIdsSet.has(id)))
  }

  const rowById = new Map()
  for (const list of pendingLists) {
    for (const row of list) {
      const id = mentorKey(row)
      if (id != null && !rowById.has(id)) rowById.set(id, row)
    }
  }

  return [...sharedIds]
    .map((id) => rowById.get(id))
    .filter(Boolean)
    .sort(
      (a, b) =>
        (a.last_name ?? '').localeCompare(b.last_name ?? '') ||
        (a.first_name ?? '').localeCompare(b.first_name ?? '') ||
        mentorKey(a) - mentorKey(b)
    )
    .map((row) => ({
      id: mentorKey(row),
      name: formatMentorName(row),
      email: row.email ?? '',
      type: row.type ?? row.mentor_type ?? '',
    }))
}

/** @param {unknown} rows */
export function normalizePendingMentorRows(rows) {
  if (!Array.isArray(rows)) return []
  return rows
    .map((m) => ({
      id: m.id ?? m.mentor_id,
      name: formatMentorName(m),
      email: m.email ?? '',
      type: m.type ?? m.mentor_type ?? '',
    }))
    .filter((m) => m.id != null)
}

/** @param {{ pending_mentors?: Array<{ id: number, first_name?: string, last_name?: string, name?: string, email?: string, type?: string }>, reply_stats?: { pending_mentor_ids?: number[], pending_mentors?: Array<{ id: number, first_name?: string, last_name?: string, name?: string, email?: string, type?: string }> } }} email @param {Array<{ id: number, first_name?: string, last_name?: string, email?: string, type?: string }>} mentors */
export function pendingMentorsForEmail(email, mentors) {
  const stats = email?.reply_stats

  if (Array.isArray(stats?.pending_mentors)) {
    return normalizePendingMentorRows(stats.pending_mentors)
  }

  if (Array.isArray(email?.pending_mentors)) {
    return normalizePendingMentorRows(email.pending_mentors)
  }

  const pendingIds = stats?.pending_mentor_ids
  if (Array.isArray(pendingIds)) {
    if (pendingIds.length === 0 || !mentors?.length) {
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

  return []
}

/** @param {{ task_completed_at?: string|null, recipients_emailed_count?: number|null, reply_stats?: { mentors_replied?: number, mentors_responded?: number, mentors_selected_practices?: number, mentors_pending?: number, mentors_emailed?: number, pending_mentor_ids?: number[] } }} row */
export function sentEmailReplyStats(row) {
  if (!row.task_completed_at) return null
  const stats = row.reply_stats
  if (!stats && row.recipients_emailed_count == null) return null
  const emailed =
    stats?.mentors_emailed ?? row.recipients_emailed_count ?? 0
  const replied = stats?.mentors_replied ?? stats?.mentors_responded ?? 0
  const pendingIds = stats?.pending_mentor_ids
  const pendingFromIds = Array.isArray(pendingIds) ? pendingIds.length : null
  const pendingFromStats = stats?.mentors_pending
  const pending =
    pendingFromIds != null
      ? pendingFromIds
      : pendingFromStats != null
        ? pendingFromStats
        : Math.max(0, emailed - replied)
  return {
    emailed,
    replied,
    selectedPractices: stats.mentors_selected_practices ?? 0,
    pending,
  }
}
