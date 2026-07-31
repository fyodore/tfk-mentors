import type {
  Mentor,
  MentorNonResponseReport,
  PendingMentorRow,
  ScheduledEmail,
  ScheduledEmailRecipientMode,
} from './types.js'

const AT_PRACTICE = 'At Practice'
const REMOTE = 'Remote'

function mentorsInSeason(
  mentors: Mentor[],
  seasonId: number,
  mentorType: string | null = null
): Mentor[] {
  return mentors.filter((m) => {
    if (!Array.isArray(m.seasons) || !m.seasons.includes(seasonId)) return false
    if (mentorType && m.type !== mentorType) return false
    return true
  })
}

function mentorTypeForRecipientMode(
  mode: ScheduledEmailRecipientMode | undefined
): string | null {
  if (mode === 'all_at_practice_in_season') return AT_PRACTICE
  if (mode === 'all_remote_in_season') return REMOTE
  return null
}

export function scheduledRecipientCount(
  row: ScheduledEmail,
  mentors: Mentor[]
): number {
  const mode =
    row.recipient_mode === 'specific_mentors'
      ? 'specific_mentors'
      : row.recipient_mode
  if (mode === 'specific_mentors') {
    return (row.specific_mentors || []).length
  }
  const sid = row.recipient_season
  if (sid == null) return 0
  return mentorsInSeason(mentors, sid, mentorTypeForRecipientMode(mode)).length
}

export function recipientSummaryText(
  row: ScheduledEmail,
  {
    seasonYearById,
    mentors,
  }: {
    seasonYearById: Map<number, number>
    mentors: Mentor[]
  }
): string {
  const mode =
    row.recipient_mode === 'specific_mentors'
      ? 'specific_mentors'
      : row.recipient_mode
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
  let pending: number | null = null
  if (isSent && stats) {
    if (stats.mentors_pending != null) {
      pending = stats.mentors_pending
    } else if (Array.isArray(stats.pending_mentor_ids)) {
      pending = stats.pending_mentor_ids.length
    } else if (stats.mentors_emailed != null) {
      pending = Math.max(0, stats.mentors_emailed - (replied ?? 0))
    }
  }

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
  const year = sid != null ? (seasonYearById.get(sid) ?? sid) : null
  let text: string
  if (mode === 'all_at_practice_in_season') {
    text = `All At Practice mentors in season ${year ?? '—'}`
  } else if (mode === 'all_remote_in_season') {
    text = `All Remote mentors in season ${year ?? '—'}`
  } else {
    text = `All mentors in season ${year ?? '—'}`
  }
  if (isSent && count == null) {
    text += ' (sent — recipient count unavailable'
    return text + `${responseSummarySuffix()})`
  }
  if (sid != null || (count != null && count > 0)) {
    text += ` (${count} mentor${count === 1 ? '' : 's'} ${countLabel}${responseSummarySuffix()})`
  }
  return text
}

export function practiceLabelsForIds(
  ids: number[],
  labelForId: (id: number) => string
): Array<{ id: number; label: string }> {
  if (!Array.isArray(ids) || ids.length === 0) {
    return []
  }
  return ids.map((pid) => ({
    id: pid,
    label: labelForId(pid),
  }))
}

export function formatMentorName(mentor: {
  first_name?: string | null
  last_name?: string | null
  email?: string | null
  id?: number | null
  name?: string | null
}): string {
  if (mentor?.name?.trim()) return mentor.name.trim()
  const name = [mentor?.first_name, mentor?.last_name]
    .filter(Boolean)
    .join(' ')
    .trim()
  if (name) return name
  if (mentor?.email?.trim()) return mentor.email.trim()
  return mentor?.id != null ? `Mentor #${mentor.id}` : 'Unknown mentor'
}

export function pendingMentorsFromNonResponseReport(
  report: MentorNonResponseReport | null | undefined,
  emailId: number,
  practiceIds: number[]
): PendingMentorRow[] {
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

  const pendingLists = practices.map(
    (practice) => practice.pending_mentors ?? []
  )
  const mentorKey = (row: { mentor_id?: number; id?: number }) =>
    row.mentor_id ?? row.id

  let sharedIds = new Set(
    (pendingLists[0] ?? [])
      .map(mentorKey)
      .filter((id): id is number => id != null)
  )
  for (let i = 1; i < pendingLists.length; i += 1) {
    const practiceIdsSet = new Set(
      (pendingLists[i] ?? [])
        .map(mentorKey)
        .filter((id): id is number => id != null)
    )
    sharedIds = new Set([...sharedIds].filter((id) => practiceIdsSet.has(id)))
  }

  const rowById = new Map<
    number,
    {
      mentor_id?: number
      id?: number
      first_name?: string | null
      last_name?: string | null
      email?: string | null
      type?: string | null
      mentor_type?: string | null
    }
  >()
  for (const list of pendingLists) {
    for (const row of list) {
      const id = mentorKey(row)
      if (id != null && !rowById.has(id)) rowById.set(id, row)
    }
  }

  return [...sharedIds]
    .map((id) => rowById.get(id))
    .filter((row): row is NonNullable<typeof row> => Boolean(row))
    .sort(
      (a, b) =>
        (a.last_name ?? '').localeCompare(b.last_name ?? '') ||
        (a.first_name ?? '').localeCompare(b.first_name ?? '') ||
        (mentorKey(a) ?? 0) - (mentorKey(b) ?? 0)
    )
    .map((row) => ({
      id: mentorKey(row) as number,
      name: formatMentorName(row),
      email: row.email ?? '',
      type: row.type ?? row.mentor_type ?? '',
    }))
}

export function normalizePendingMentorRows(rows: unknown): PendingMentorRow[] {
  if (!Array.isArray(rows)) return []
  return rows
    .map((raw) => {
      const m = raw as {
        id?: number
        mentor_id?: number
        email?: string
        type?: string
        mentor_type?: string
        first_name?: string
        last_name?: string
        name?: string
      }
      return {
        id: m.id ?? m.mentor_id,
        name: formatMentorName(m),
        email: m.email ?? '',
        type: m.type ?? m.mentor_type ?? '',
      }
    })
    .filter((m): m is PendingMentorRow => m.id != null)
}

export function pendingMentorsForEmail(
  email: ScheduledEmail | null | undefined,
  mentors: Mentor[]
): PendingMentorRow[] {
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
      .filter((m): m is Mentor => Boolean(m))
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

export function sentEmailReplyStats(row: ScheduledEmail): {
  emailed: number
  replied: number
  selectedPractices: number
  pending: number
} | null {
  if (!row.task_completed_at) return null
  const stats = row.reply_stats
  if (!stats && row.recipients_emailed_count == null) return null
  const emailed = stats?.mentors_emailed ?? row.recipients_emailed_count ?? 0
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
    selectedPractices: stats?.mentors_selected_practices ?? 0,
    pending,
  }
}
