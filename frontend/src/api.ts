import { apiPath } from './config.js'
import type {
  Coach,
  Id,
  JsonObject,
  Mentor,
  MentorSwapReport,
  MentorSwapRequestSummary,
  Practice,
  PracticeAttendanceCurrentResponse,
  PracticeAttendanceDetail,
  ArchivedPracticeAttendance,
  PublicMentorDirectoryPractices,
  PublicMentorDirectoryRow,
  PublicPracticeRoster,
  PublicPracticeSwapOptions,
  PublicUpcomingPractice,
  Season,
  ServerConfig,
} from './types.js'

export type { Id, JsonObject, Season, Practice, Mentor, Coach } from './types.js'

export class ApiError extends Error {
  status?: number
  body?: unknown

  constructor(message: string, options?: { status?: number; body?: unknown }) {
    super(message)
    this.name = 'ApiError'
    this.status = options?.status
    this.body = options?.body
  }
}

const SEASON_LIST = apiPath('/api/season/')
const SERVER_CONFIG = apiPath('/api/config/')

export async function fetchServerConfig(): Promise<ServerConfig> {
  const res = await fetch(SERVER_CONFIG, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

function getCookie(name: string): string {
  const row = document.cookie.split('; ').find((r) => r.startsWith(`${name}=`))
  if (!row) return ''
  return decodeURIComponent(row.slice(name.length + 1))
}

function csrfHeaders(): Record<string, string> {
  const token = getCookie('csrftoken')
  return token ? { 'X-CSRFToken': token } : {}
}

async function parseError(res: Response): Promise<string> {
  let msg = `${res.status} ${res.statusText}`
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object') {
      const obj = body as Record<string, unknown>
      if (typeof obj.detail === 'string') msg = obj.detail
      else if (Array.isArray(obj.non_field_errors) && obj.non_field_errors[0] != null) {
        msg = String(obj.non_field_errors[0])
      } else {
        const first = Object.entries(obj).find(
          ([k, v]) => k !== 'detail' && Array.isArray(v) && v.length
        )
        if (first) {
          const [key, values] = first
          msg = `${key}: ${String((values as unknown[])[0])}`
        } else if (typeof obj.year === 'string') msg = obj.year
      }
    }
  } catch {
    // ignore non-JSON bodies
  }
  return msg
}

function normalizeList<T = unknown>(data: unknown): T[] {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data)) return data as T[]
  if ('results' in data && Array.isArray((data as { results: unknown }).results)) {
    return (data as { results: T[] }).results
  }
  return []
}

export function normalizeSeasonList(data: unknown): Season[] {
  return normalizeList<Season>(data)
}

let seasonsListPromise: Promise<Season[]> | null = null

function invalidateSeasonsCache() {
  seasonsListPromise = null
}

export async function fetchSeasons(): Promise<Season[]> {
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

export async function createSeason(body: number | { year: number; head_coach?: number | null }) {
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

export async function patchSeason(id: Id, body: number | { year?: number; is_current?: boolean; head_coach?: number | null }) {
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

export async function setCurrentSeason(id: Id) {
  return patchSeason(id, { is_current: true })
}

export async function deleteSeason(id: Id) {
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

export function normalizePracticeList(data: unknown): Practice[] {
  return normalizeList<Practice>(data)
}

export async function fetchPractices(params: { season?: Id | null; lite?: boolean } = {}) {
  const query = new URLSearchParams()
  if (params.season != null && params.season !== '') {
    query.set('season', String(params.season))
  }
  if (params.lite) {
    query.set('lite', '1')
  }
  const suffix = query.toString() ? `?${query}` : ''
  const res = await fetch(`${PRACTICE_LIST}${suffix}`, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizePracticeList(data)
}

export async function createPractice(body: JsonObject) {
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

export async function patchPractice(id: Id, body: JsonObject) {
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

export async function deletePractice(id: Id) {
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

export function normalizeCoachList(data: unknown): Coach[] {
  return normalizeList<Coach>(data)
}

export async function fetchCoaches(): Promise<Coach[]> {
  const res = await fetch(COACH_LIST, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeCoachList(data)
}

export async function createCoach(body: JsonObject) {
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

export async function patchCoach(id: Id, body: JsonObject) {
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

export async function deleteCoach(id: Id) {
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

export function normalizeTfkStaffList(data: unknown): unknown[] {
  return normalizeList<unknown>(data)
}

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

export async function createTfkStaff(body: JsonObject) {
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

export async function patchTfkStaff(id: Id, body: JsonObject) {
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

export async function deleteTfkStaff(id: Id) {
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

export async function importCoachesCsv(file: File) {
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

export function normalizeMentorList(data: unknown): Mentor[] {
  return normalizeList<Mentor>(data)
}

export async function fetchMentors() {
  const res = await fetch(MENTOR_LIST, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeMentorList(data)
}

export async function fetchMentor(id: Id) {
  const res = await fetch(`${MENTOR_LIST}${id}/`, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchMentorPractices(id: Id) {
  const res = await fetch(`${MENTOR_LIST}${id}/practices/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return Array.isArray(data) ? data : []
}

export async function createMentor(body: JsonObject) {
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

export async function patchMentor(id: Id, body: JsonObject) {
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

export async function deleteMentor(id: Id) {
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

export async function importMentorsCsv(file: File) {
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

export async function fetchPractice(id: Id, params: { basic?: boolean } = {}) {
  const query = new URLSearchParams()
  if (params.basic) {
    query.set('basic', '1')
  }
  const suffix = query.toString() ? `?${query}` : ''
  const res = await fetch(`${PRACTICE_LIST}${id}/${suffix}`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPracticeMentorReplies(id: Id) {
  const res = await fetch(`${PRACTICE_LIST}${id}/mentor-replies/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function createPracticeMentorReply(practiceId: Id, body: { mentor: number; pace: string }) {
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

export async function patchPracticeMentorPace(practiceId: Id, mentorId: Id, pace: string) {
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

export async function makePracticeMentorAvailable(practiceId: Id, mentorId: Id) {
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

export async function swapPracticeMentor(practiceId: Id, body: { outgoing_mentor: number; incoming_mentor: number }) {
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

export async function deletePracticeMentorReply(practiceId: Id, mentorId: Id) {
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

export function normalizeCoachPracticeAssignmentList(data: unknown): unknown[] {
  return normalizeList<unknown>(data)
}

export async function fetchCoachPracticeAssignments() {
  const res = await fetch(COACH_PRACTICE_ASSIGNMENT_LIST, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeCoachPracticeAssignmentList(data)
}

export async function createCoachPracticeAssignment(body: JsonObject) {
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

export async function deleteCoachPracticeAssignment(id: Id) {
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

export function normalizeMentorPracticeAssignmentList(data: unknown): unknown[] {
  return normalizeList<unknown>(data)
}

export async function fetchMentorPracticeAssignments() {
  const res = await fetch(MENTOR_PRACTICE_ASSIGNMENT_LIST, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeMentorPracticeAssignmentList(data)
}

export async function createMentorPracticeAssignment(body: JsonObject) {
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

export async function deleteMentorPracticeAssignment(id: Id) {
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

export function normalizeScheduledEmailList(data: unknown): unknown[] {
  return normalizeList<unknown>(data)
}

export async function fetchScheduledEmails() {
  const res = await fetch(SCHEDULED_EMAIL_LIST, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  const data = await res.json()
  return normalizeScheduledEmailList(data)
}

export async function fetchScheduledEmail(id: Id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchScheduledEmailPendingMentors(id: Id) {
  const res = await fetch(`${SCHEDULED_EMAIL_LIST}${id}/pending-mentors/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function previewScheduledEmailReplyReminders(id: Id) {
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

export async function sendScheduledEmailNow(id: Id) {
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

export async function sendScheduledEmailReplyReminders(id: Id) {
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

export async function createScheduledEmail(body: JsonObject) {
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

export async function patchScheduledEmail(id: Id, body: JsonObject) {
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

export async function deleteScheduledEmail(id: Id) {
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

export function normalizePracticeReminderEmailList(data: unknown): unknown[] {
  return normalizeList<unknown>(data)
}

export async function fetchPracticeReminderEmails(seasonId: Id) {
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

export async function fetchPracticeReminderEmail(id: Id) {
  const res = await fetch(`${PRACTICE_REMINDER_EMAIL_LIST}${id}/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function syncPracticeReminderEmails(seasonId: Id) {
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

export async function refreshPracticeReminderEmailTemplates(seasonId: Id) {
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

export async function patchPracticeReminderEmail(id: Id, body: JsonObject) {
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

export async function deletePracticeReminderEmail(id: Id) {
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

export async function sendPracticeReminderEmailNow(id: Id) {
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

export async function fetchMentorCellPhoneRequests(seasonId: Id) {
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

export async function sendMentorCellPhoneRequests(body: { season?: Id | null; dry_run?: boolean } = {}) {
  const payload: JsonObject = {}
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

export async function fetchMentorCellPhoneUpdate(token: string) {
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
    throw new ApiError(detail, { status: res.status, body })
  }
  return res.json()
}

export async function putMentorCellPhoneUpdate(token: string, body: { cell_phone: string }) {
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
    throw new ApiError(await parseError(res), { status: res.status })
  }
  return res.json()
}

const AUTH_SESSION = apiPath('/api/auth/session/')

export async function checkAuthSession(): Promise<boolean> {
  const res = await fetch(AUTH_SESSION, { credentials: 'include' })
  if (!res.ok) return false
  const data = await res.json()
  return data.authenticated === true
}

export async function loginSitePassword(password: string) {
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

export async function fetchMentorEmailReply(token: string) {
  const url = `${MENTOR_EMAIL_REPLY}/${encodeURIComponent(token)}/`
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function putMentorEmailReply(token: string, payload: { replies: { practice: number; attendance: string; pace?: string }[]; email_received_confirmed?: boolean; mentor_pace?: string }) {
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

export async function fetchPracticeRosterReport(params: { season?: Id | null } = {}) {
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

export async function fetchMentorNonResponseReport(params: { season?: Id | null } = {}) {
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

export async function fetchCurrentPracticeAttendance(): Promise<PracticeAttendanceCurrentResponse> {
  const res = await fetch(PRACTICE_ATTENDANCE_CURRENT, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPracticeAttendance(id: Id): Promise<PracticeAttendanceDetail> {
  const res = await fetch(apiPath(`/api/practice-attendance/${id}/`), {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchArchivedPracticeAttendance(
  params: { season?: Id | null } = {}
): Promise<ArchivedPracticeAttendance[]> {
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

export async function patchPracticeAttendance(
  id: Id,
  body: {
    attendance_comments?: string
    mentors?: Array<{ mentor_id: number; show_up: string | null }>
  }
): Promise<PracticeAttendanceDetail> {
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

export async function fetchPublicMentorDirectory(): Promise<PublicMentorDirectoryRow[]> {
  const res = await fetch(PUBLIC_MENTOR_DIRECTORY)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPublicMentorDirectoryPractices(mentorId: Id): Promise<PublicMentorDirectoryPractices> {
  const res = await fetch(
    apiPath(`/api/public/mentor-directory/${mentorId}/practices/`)
  )
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPublicUpcomingPractices(): Promise<PublicUpcomingPractice[]> {
  const res = await fetch(apiPath('/api/public/practices/upcoming/'))
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPublicPracticeMentorRoster(practiceId: Id): Promise<PublicPracticeRoster> {
  const res = await fetch(apiPath(`/api/public/practice/${practiceId}/mentors/`))
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPublicPracticeSwapOptions(
  practiceId: Id
): Promise<PublicPracticeSwapOptions> {
  const res = await fetch(apiPath(`/api/public/practice/${practiceId}/swap-options/`))
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function createPublicMentorSwapRequest(body: {
  practice: Id
  outgoing_mentor: Id
  incoming_mentor: Id
}): Promise<MentorSwapRequestSummary & { email?: JsonObject }> {
  const res = await fetch(apiPath('/api/public/mentor-swap-request/'), {
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

export async function fetchPublicMentorSwapRequest(
  token: string
): Promise<MentorSwapRequestSummary> {
  const res = await fetch(
    apiPath(`/api/public/mentor-swap-request/${encodeURIComponent(token)}/`)
  )
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function approvePublicMentorSwapRequest(token: string): Promise<{
  already_decided?: boolean
  status?: string
  message?: string
  detail?: string
  [key: string]: unknown
}> {
  const res = await fetch(
    apiPath(`/api/public/mentor-swap-request/${encodeURIComponent(token)}/approve/`)
  )
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function rejectPublicMentorSwapRequest(
  token: string,
  comments: string
): Promise<{
  already_decided?: boolean
  status?: string
  message?: string
  reports_url?: string
  [key: string]: unknown
}> {
  const res = await fetch(
    apiPath(`/api/public/mentor-swap-request/${encodeURIComponent(token)}/reject/`),
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...csrfHeaders(),
      },
      body: JSON.stringify({ comments }),
    }
  )
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchMentorSwapReport(params: { season?: Id | null } = {}): Promise<MentorSwapReport> {
  const qs = new URLSearchParams()
  if (params.season != null && params.season !== '') {
    qs.set('season', String(params.season))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${apiPath('/api/reports/mentor-swaps/')}${suffix}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function scheduleMentors(practiceIds: number[], options: { apply?: boolean; schedule?: JsonObject } = {}) {
  const body: JsonObject = {
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
