import { apiPath } from './config.js'

const SEASON_LIST = apiPath('/api/season/')
const SERVER_CONFIG = apiPath('/api/config/')

/** @returns {Promise<{ time_zone: string }>} */
export async function fetchServerConfig() {
  const res = await fetch(SERVER_CONFIG, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @returns {string} */
function getCookie(name) {
  const row = document.cookie.split('; ').find((r) => r.startsWith(`${name}=`))
  if (!row) return ''
  return decodeURIComponent(row.slice(name.length + 1))
}

function csrfHeaders() {
  const token = getCookie('csrftoken')
  return token ? { 'X-CSRFToken': token } : {}
}

async function parseError(res) {
  let msg = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    if (body && typeof body === 'object') {
      if (typeof body.detail === 'string') msg = body.detail
      else if (body.non_field_errors?.[0]) msg = String(body.non_field_errors[0])
      else {
        const first = Object.entries(body).find(
          ([k, v]) => k !== 'detail' && Array.isArray(v) && v.length
        )
        if (first) msg = `${first[0]}: ${first[1][0]}`
        else if (typeof body.year === 'string') msg = body.year
      }
    }
  } catch {
    // ignore non-JSON bodies
  }
  return msg
}

/** @param {unknown} data */
export function normalizeSeasonList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

/** @type {Promise<ReturnType<typeof normalizeSeasonList>> | null} */
let seasonsListPromise = null

function invalidateSeasonsCache() {
  seasonsListPromise = null
}

export async function fetchSeasons() {
  if (!seasonsListPromise) {
    seasonsListPromise = (async () => {
      const res = await fetch(SEASON_LIST, { credentials: 'include' })
      if (!res.ok) throw new Error(await parseError(res))
      const data = await res.json()
      return normalizeSeasonList(data)
    })().catch((err) => {
      invalidateSeasonsCache()
      throw err
    })
  }
  return seasonsListPromise
}

/** @param {number | { year: number, head_coach?: number|null }} body */
export async function createSeason(body) {
  const payload = typeof body === 'number' ? { year: body } : body
  const res = await fetch(SEASON_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  invalidateSeasonsCache()
  return res.json()
}

/** @param {number|string} id @param {number | { year?: number, is_current?: boolean, head_coach?: number|null }} body */
export async function patchSeason(id, body) {
  const payload = typeof body === 'number' ? { year: body } : body
  const res = await fetch(`${SEASON_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  invalidateSeasonsCache()
  return res.json()
}

/** @param {number|string} id */
export async function setCurrentSeason(id) {
  return patchSeason(id, { is_current: true })
}

/** @param {number|string} id */
export async function deleteSeason(id) {
  const res = await fetch(`${SEASON_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
  invalidateSeasonsCache()
}

const PRACTICE_LIST = apiPath('/api/practice/')

/** @param {unknown} data */
export function normalizePracticeList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

export async function fetchPractices(params = {}) {
  const query = new URLSearchParams()
  if (params.season != null && params.season !== '') {
    query.set('season', String(params.season))
  }
  const suffix = query.toString() ? `?${query}` : ''
  const res = await fetch(`${PRACTICE_LIST}${suffix}`, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizePracticeList(data)
}

/** @param {Record<string, unknown>} body */
export async function createPractice(body) {
  const res = await fetch(PRACTICE_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id @param {Record<string, unknown>} body */
export async function patchPractice(id, body) {
  const res = await fetch(`${PRACTICE_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deletePractice(id) {
  const res = await fetch(`${PRACTICE_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

const COACH_LIST = apiPath('/api/coach/')
const TFK_STAFF_LIST = apiPath('/api/tfk-staff/')
const MENTOR_LIST = apiPath('/api/mentor/')
const COACH_PRACTICE_ASSIGNMENT_LIST = apiPath('/api/coach-practice-assignment/')
const MENTOR_PRACTICE_ASSIGNMENT_LIST = apiPath('/api/mentor-practice-assignment/')

/** @param {unknown} data */
export function normalizeCoachList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

/** List coaches from Django: `GET /api/coach/`. */
export async function fetchCoaches() {
  const res = await fetch(COACH_LIST, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeCoachList(data)
}

/** @param {Record<string, unknown>} body */
export async function createCoach(body) {
  const res = await fetch(COACH_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id @param {Record<string, unknown>} body */
export async function patchCoach(id, body) {
  const res = await fetch(`${COACH_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deleteCoach(id) {
  const res = await fetch(`${COACH_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

/** @param {unknown} data */
export function normalizeTfkStaffList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

/** List TFK staff from Django: `GET /api/tfk-staff/`. */
export async function fetchTfkStaff() {
  const res = await fetch(TFK_STAFF_LIST, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeTfkStaffList(data)
}

/** @param {Record<string, unknown>} body */
export async function createTfkStaff(body) {
  const res = await fetch(TFK_STAFF_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id @param {Record<string, unknown>} body */
export async function patchTfkStaff(id, body) {
  const res = await fetch(`${TFK_STAFF_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deleteTfkStaff(id) {
  const res = await fetch(`${TFK_STAFF_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

/** @param {File} file */
export async function importCoachesCsv(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${COACH_LIST}import-csv/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
    body: formData,
  })
  if (!res.ok && res.status !== 207) throw new Error(await parseError(res))
  return res.json()
}

/** @param {unknown} data */
export function normalizeMentorList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

export async function fetchMentors() {
  const res = await fetch(MENTOR_LIST, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeMentorList(data)
}

/** @param {number|string} id */
export async function fetchMentor(id) {
  const res = await fetch(`${MENTOR_LIST}${id}/`, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function fetchMentorPractices(id) {
  const res = await fetch(`${MENTOR_LIST}${id}/practices/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return Array.isArray(data) ? data : []
}

/** @param {Record<string, unknown>} body */
export async function createMentor(body) {
  const res = await fetch(MENTOR_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id @param {Record<string, unknown>} body */
export async function patchMentor(id, body) {
  const res = await fetch(`${MENTOR_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deleteMentor(id) {
  const res = await fetch(`${MENTOR_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

/** @param {File} file */
export async function importMentorsCsv(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${MENTOR_LIST}import-csv/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
    body: formData,
  })
  if (!res.ok && res.status !== 207) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function fetchPractice(id) {
  const res = await fetch(`${PRACTICE_LIST}${id}/`, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function fetchPracticeMentorReplies(id) {
  const res = await fetch(`${PRACTICE_LIST}${id}/mentor-replies/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} practiceId @param {{ mentor: number, pace: string }} body */
export async function createPracticeMentorReply(practiceId, body) {
  const res = await fetch(`${PRACTICE_LIST}${practiceId}/mentor-replies/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} practiceId @param {number|string} mentorId @param {string} pace */
export async function patchPracticeMentorPace(practiceId, mentorId, pace) {
  const res = await fetch(`${PRACTICE_LIST}${practiceId}/mentor-replies/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ mentor: mentorId, pace }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} practiceId @param {number|string} mentorId */
export async function makePracticeMentorAvailable(practiceId, mentorId) {
  const res = await fetch(`${PRACTICE_LIST}${practiceId}/mentor-replies/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ mentor: mentorId, attendance: 'available' }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/**
 * @param {number|string} practiceId
 * @param {{ outgoing_mentor: number, incoming_mentor: number }} body
 */
export async function swapPracticeMentor(practiceId, body) {
  const res = await fetch(`${PRACTICE_LIST}${practiceId}/swap-mentor/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} practiceId @param {number|string} mentorId */
export async function deletePracticeMentorReply(practiceId, mentorId) {
  const q = new URLSearchParams({ mentor: String(mentorId) })
  const res = await fetch(
    `${PRACTICE_LIST}${practiceId}/mentor-replies/?${q}`,
    {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        ...csrfHeaders(),
      },
    }
  )
  if (!res.ok && res.status !== 204) throw new Error(await parseError(res))
}

/** @param {unknown} data */
export function normalizeCoachPracticeAssignmentList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

export async function fetchCoachPracticeAssignments() {
  const res = await fetch(COACH_PRACTICE_ASSIGNMENT_LIST, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeCoachPracticeAssignmentList(data)
}

/** @param {Record<string, unknown>} body */
export async function createCoachPracticeAssignment(body) {
  const res = await fetch(COACH_PRACTICE_ASSIGNMENT_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deleteCoachPracticeAssignment(id) {
  const res = await fetch(`${COACH_PRACTICE_ASSIGNMENT_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

/** @param {unknown} data */
export function normalizeMentorPracticeAssignmentList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

export async function fetchMentorPracticeAssignments() {
  const res = await fetch(MENTOR_PRACTICE_ASSIGNMENT_LIST, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeMentorPracticeAssignmentList(data)
}

/** @param {Record<string, unknown>} body */
export async function createMentorPracticeAssignment(body) {
  const res = await fetch(MENTOR_PRACTICE_ASSIGNMENT_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deleteMentorPracticeAssignment(id) {
  const res = await fetch(`${MENTOR_PRACTICE_ASSIGNMENT_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

const SCHEDULED_EMAIL_LIST = apiPath('/api/scheduled-email/')

/** @param {unknown} data */
export function normalizeScheduledEmailList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

export async function fetchScheduledEmails() {
  const res = await fetch(SCHEDULED_EMAIL_LIST, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeScheduledEmailList(data)
}

/** @param {number|string} id */
export async function fetchScheduledEmail(id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function fetchScheduledEmailPendingMentors(id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/pending-mentors/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function previewScheduledEmailReplyReminders(id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/send-reply-reminders/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ dry_run: true }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function sendScheduledEmailNow(id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/send-now/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function sendScheduledEmailReplyReminders(id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/send-reply-reminders/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {Record<string, unknown>} body */
export async function createScheduledEmail(body) {
  const res = await fetch(SCHEDULED_EMAIL_LIST, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id @param {Record<string, unknown>} body */
export async function patchScheduledEmail(id, body) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deleteScheduledEmail(id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

const PRACTICE_REMINDER_EMAIL_LIST = apiPath('/api/practice-reminder-email/')

/** @param {unknown} data */
export function normalizePracticeReminderEmailList(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data
  if ('results' in data && Array.isArray(data.results)) return data.results
  return []
}

/** @param {number|string} [seasonId] */
export async function fetchPracticeReminderEmails(seasonId) {
  const query =
    seasonId != null && seasonId !== ''
      ? `?season=${encodeURIComponent(String(seasonId))}`
      : ''
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}${query}`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizePracticeReminderEmailList(data)
}

/** @param {number|string} id */
export async function fetchPracticeReminderEmail(id) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}${id}/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} seasonId */
export async function syncPracticeReminderEmails(seasonId) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}sync/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ season: Number(seasonId) }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} seasonId */
export async function refreshPracticeReminderEmailTemplates(seasonId) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}refresh-templates/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ season: Number(seasonId) }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id @param {Record<string, unknown>} body */
export async function patchPracticeReminderEmail(id, body) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}${id}/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function deletePracticeReminderEmail(id) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}${id}/`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...csrfHeaders(),
    },
  })
  if (!res.ok && res.status !== 204)
    throw new Error(await parseError(res))
}

/** @param {number|string} id */
export async function sendPracticeReminderEmailNow(id) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}${id}/send-now/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

const MENTOR_CELL_PHONE_REQUEST = apiPath('/api/mentor-cell-phone-request/')
const MENTOR_CELL_PHONE_UPDATE = apiPath('/api/mentor-cell-phone-update/')

/** @param {number|string|null|undefined} [seasonId] */
export async function fetchMentorCellPhoneRequests(seasonId) {
  const qs =
    seasonId !== undefined && seasonId !== null && seasonId !== ''
      ? `?season=${encodeURIComponent(String(seasonId))}`
      : ''
  const res = await fetch(`${MENTOR_CELL_PHONE_REQUEST}${qs}`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/**
 * @param {{ season?: number|string|null, dry_run?: boolean }} [body]
 */
export async function sendMentorCellPhoneRequests(body = {}) {
  const payload = {}
  if (body.season !== undefined && body.season !== null && body.season !== '') {
    payload.season = Number(body.season)
  }
  if (body.dry_run) payload.dry_run = true
  const res = await fetch(`${MENTOR_CELL_PHONE_REQUEST}send/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {string} token */
export async function fetchMentorCellPhoneUpdate(token) {
  const res = await fetch(
    `${MENTOR_CELL_PHONE_UPDATE}${encodeURIComponent(token)}/`,
    { credentials: 'include' }
  )
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    let body = null
    try {
      body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* ignore */
    }
    const err = new Error(detail)
    err.status = res.status
    err.body = body
    throw err
  }
  return res.json()
}

/**
 * @param {string} token
 * @param {{ cell_phone: string }} body
 */
export async function putMentorCellPhoneUpdate(token, body) {
  const res = await fetch(
    `${MENTOR_CELL_PHONE_UPDATE}${encodeURIComponent(token)}/`,
    {
      method: 'PUT',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...csrfHeaders(),
      },
      body: JSON.stringify(body),
    }
  )
  if (!res.ok) {
    const err = new Error(await parseError(res))
    err.status = res.status
    throw err
  }
  return res.json()
}

const AUTH_SESSION = apiPath('/api/auth/session/')

/** Bootstrap CSRF cookie and report whether the admin session is active. */
export async function checkAuthSession() {
  const res = await fetch(AUTH_SESSION, { credentials: 'include' })
  if (!res.ok) return false
  const data = await res.json()
  return data.authenticated === true
}

/** @param {string} password */
export async function loginSitePassword(password) {
  const res = await fetch(AUTH_SESSION, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

const MENTOR_EMAIL_REPLY = apiPath('/api/mentor-email-reply')

/** @param {string} token raw UUID from URL (?token= or path) */
export async function fetchMentorEmailReply(token) {
  const url = `${MENTOR_EMAIL_REPLY}/${encodeURIComponent(token)}/`
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/**
 * @param {string} token
 * @param {{
 *   replies: { practice: number, attendance: string, pace?: string }[],
 *   email_received_confirmed?: boolean,
 *   mentor_pace?: string
 * }} payload
 */
export async function putMentorEmailReply(token, payload) {
  const url = `${MENTOR_EMAIL_REPLY}/${encodeURIComponent(token)}/`
  const res = await fetch(url, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

const PRACTICE_ROSTER_REPORT = apiPath('/api/reports/practice-roster/')

/** @param {{ season?: number|string }} [params] */
export async function fetchPracticeRosterReport(params = {}) {
  const qs = new URLSearchParams()
  if (params.season != null && params.season !== '') {
    qs.set('season', String(params.season))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${PRACTICE_ROSTER_REPORT}${suffix}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

const MENTOR_NON_RESPONSE_REPORT = apiPath('/api/reports/mentor-non-responses/')

/** @param {{ season?: number|string }} [params] */
export async function fetchMentorNonResponseReport(params = {}) {
  const qs = new URLSearchParams()
  if (params.season != null && params.season !== '') {
    qs.set('season', String(params.season))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${MENTOR_NON_RESPONSE_REPORT}${suffix}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

const PRACTICE_ATTENDANCE_CURRENT = apiPath('/api/practice-attendance/current/')
const PRACTICE_ATTENDANCE_ARCHIVED = apiPath('/api/practice-attendance/archived/')

/** @returns {Promise<{ practice: object|null }>} */
export async function fetchCurrentPracticeAttendance() {
  const res = await fetch(PRACTICE_ATTENDANCE_CURRENT, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} id */
export async function fetchPracticeAttendance(id) {
  const res = await fetch(apiPath(`/api/practice-attendance/${id}/`), {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {{ season?: number|string }} [params] */
export async function fetchArchivedPracticeAttendance(params = {}) {
  const qs = new URLSearchParams()
  if (params.season != null && params.season !== '') {
    qs.set('season', String(params.season))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${PRACTICE_ATTENDANCE_ARCHIVED}${suffix}`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/**
 * @param {number|string} id
 * @param {{ attendance_comments?: string, mentors?: Array<{ mentor_id: number, show_up: string|null }> }} body
 */
export async function patchPracticeAttendance(id, body) {
  const res = await fetch(apiPath(`/api/practice-attendance/${id}/`), {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

const PUBLIC_MENTOR_DIRECTORY = apiPath('/api/public/mentor-directory/')

/** @returns {Promise<Array<{ id: number, first_name: string, last_name: string, type: string, pace: string, assigned_count: number, available_count: number }>>} */
export async function fetchPublicMentorDirectory() {
  const res = await fetch(PUBLIC_MENTOR_DIRECTORY)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} mentorId */
export async function fetchPublicMentorDirectoryPractices(mentorId) {
  const res = await fetch(
    apiPath(`/api/public/mentor-directory/${mentorId}/practices/`)
  )
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** @param {number|string} practiceId */
export async function fetchPublicPracticeMentorRoster(practiceId) {
  const res = await fetch(apiPath(`/api/public/practice/${practiceId}/mentors/`))
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/**
 * @param {number[]} practiceIds
 * @param {{ apply?: boolean, schedule?: object }} [options]
 */
export async function scheduleMentors(practiceIds, options = {}) {
  const body = {
    practice_ids: practiceIds,
    apply: Boolean(options.apply),
  }
  if (options.apply) {
    if (!options.schedule || typeof options.schedule !== 'object') {
      throw new Error('Preview schedule result is required to apply.')
    }
    body.schedule = options.schedule
  }
  const res = await fetch(apiPath('/api/practices/schedule-mentors/'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}
