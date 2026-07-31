export type Id = number | string

export type Season = {
  id: number
  year: number
  is_current?: boolean
  head_coach?: number | null
}

export type Practice = {
  id: number
  date?: string | null
  season?: number | null
  season_year?: number | null
  nyrr_race?: string | null
  description?: string | null
  start_location?: string | null
  full_practice?: boolean
  show_to_mentors?: boolean
  [key: string]: unknown
}

export type Coach = {
  id: number
  first_name: string
  last_name: string
  email?: string
  cell?: string
  seasons?: number[]
  [key: string]: unknown
}

export type Mentor = {
  id: number
  first_name: string
  last_name: string
  email?: string
  cell_phone?: string
  type?: string
  pace?: string
  split_practice?: boolean
  seasons?: number[]
  [key: string]: unknown
}

export type TfkStaff = {
  id: number
  first_name: string
  last_name: string
  email?: string
  cell_phone?: string
  [key: string]: unknown
}

export type PublicMentorDirectoryRow = {
  id: number
  first_name: string
  last_name: string
  type: string
  pace: string
  assigned_count: number
  available_count: number
}

export type PublicMentorPracticeRow = {
  practice_id: number
  date?: string | null
  season_year?: number | null
  nyrr_race?: string | null
  full_practice?: boolean
  pace?: string
  attendance?: string | null
}

export type MentorPracticeRow = {
  practice_id: number
  date?: string | null
  season_id?: number | null
  season_year?: number | null
  nyrr_race?: string | null
  full_practice?: boolean
  status?: 'assigned' | 'available' | null
  pace?: string
  attendance?: string | null
}

export type ScheduleMentorRow = {
  mentor_id: number
  first_name?: string
  last_name?: string
  email?: string
  pace?: string
  mentor_type?: string
  selection_count?: number | null
  attendance?: string
}

export type ScheduleUnderfilledPaceGroup = {
  pace: string
  assigned_count: number
  slots_remaining: number
}

export type SchedulePracticeResultRow = {
  practice_id: number
  date?: string | null
  nyrr_race?: string
  assignments_by_pace?: Record<string, ScheduleMentorRow[]>
  available_by_pace?: Record<string, ScheduleMentorRow[]>
  underfilled_pace_groups?: ScheduleUnderfilledPaceGroup[]
}

export type ScheduleUnderfilledPractice = {
  practice_id: number
  date?: string | null
  nyrr_race?: string
  underfilled_pace_groups?: ScheduleUnderfilledPaceGroup[]
}

export type ScheduleRemoteMentorPractice = {
  practice_id: number
  date?: string | null
  nyrr_race?: string
  pace?: string
  attendance?: string
}

export type ScheduleRemoteMentor = {
  mentor_id: number
  first_name?: string
  last_name?: string
  email?: string
  pace?: string
  mentor_type?: string
  practices?: ScheduleRemoteMentorPractice[]
}

export type ScheduleAppliedError = {
  mentor_id?: number
  practice_id?: number
  action?: string
  detail?: string
}

export type ScheduleApplied = {
  assigned?: number
  available?: number
  errors?: ScheduleAppliedError[]
  closed_practice_ids?: number[]
}

export type MentorScheduleResult = {
  practices?: SchedulePracticeResultRow[]
  underfilled_practices?: ScheduleUnderfilledPractice[]
  remote_mentors?: ScheduleRemoteMentor[]
  summary?: {
    mentors_considered?: number
    mentors_assigned?: number
    assignment_rows?: number
    available_rows?: number
    remote_mentors?: number
    underfilled_practice_count?: number
    max_per_pace?: number
    max_per_month?: number
  }
  skipped_mentors?: unknown[]
  applied?: ScheduleApplied
}

export type PublicMentorDirectoryPractices = {
  mentor_id: number
  assigned_practices: PublicMentorPracticeRow[]
  available_practices: PublicMentorPracticeRow[]
}

export type PublicUpcomingPractice = {
  id: number
  date: string
  nyrr_race: string
  season_year: number | null
  full_practice: boolean
  description: string
}

export type PublicPracticeCoach = {
  coach_id: number
  first_name: string
  last_name: string
  pace?: string
}

export type PublicPracticeMentor = {
  mentor_id: number
  first_name: string
  last_name: string
  pace?: string
  attendance?: string | null
}

export type PublicPracticeRoster = {
  practice_id: number
  description: string
  coaches: PublicPracticeCoach[]
  attending_mentors: PublicPracticeMentor[]
  available_mentors: PublicPracticeMentor[]
}

export type PublicSwapMentorOption = {
  mentor_id: number
  first_name: string
  last_name: string
  pace?: string
  type?: string
}

export type PublicPracticeSwapOptions = {
  practice_id: number
  date?: string | null
  nyrr_race?: string
  season_year?: number | null
  attending_mentors: PublicSwapMentorOption[]
  incoming_mentors: PublicSwapMentorOption[]
}

export type MentorSwapRequestSummary = {
  id: number
  status: 'pending' | 'approved' | 'rejected' | string
  token?: string
  practice_id: number
  practice_date?: string | null
  nyrr_race?: string
  season_year?: number | null
  outgoing_mentor: PublicSwapMentorOption
  incoming_mentor: PublicSwapMentorOption
  reject_comments?: string
  decided_at?: string | null
  created_at?: string | null
}

export type MentorSwapReport = {
  approved: MentorSwapRequestSummary[]
  rejected: MentorSwapRequestSummary[]
}

export type ReportPaceCount = {
  pace: string
  count: number
}

export type ReportRosterPerson = {
  role: string
  first_name?: string | null
  last_name?: string | null
  email?: string | null
  pace?: string | null
  mentor_id?: number
  mentor_type?: string | null
  attendance?: string | null
  available?: boolean
}

export type PracticeRosterReportRow = {
  id: number
  date?: string | null
  nyrr_race?: string
  season?: number | null
  season_year?: number | null
  full_practice?: boolean
  coaches?: ReportRosterPerson[]
  mentors?: ReportRosterPerson[]
  available_mentors?: ReportRosterPerson[]
  mentor_pace_counts?: ReportPaceCount[]
}

export type EmailResponsePaceCount = {
  pace: string
  emailed: number
  responded: number
  pending: number
}

export type MentorNonResponsePendingMentor = {
  mentor_id: number
  first_name?: string | null
  last_name?: string | null
  email?: string | null
  pace?: string | null
  mentor_type?: string | null
}

export type MentorNonResponsePractice = {
  id: number
  date?: string | null
  nyrr_race?: string
  season?: number | null
  season_year?: number | null
  full_practice?: boolean
  scheduled_email_id?: number | null
  scheduled_send_at?: string | null
  email_sent?: boolean
  mentors_emailed?: number
  mentors_responded?: number
  response_pace_counts?: EmailResponsePaceCount[]
  pending_mentors?: MentorNonResponsePendingMentor[]
}

export type MentorNonResponseReport = {
  summary?: {
    mentors_emailed?: number
    mentors_responded?: number
  }
  practices?: MentorNonResponsePractice[]
}

export type ScheduledEmailRecipientMode =
  | 'all_in_season'
  | 'all_at_practice_in_season'
  | 'all_remote_in_season'
  | 'specific_mentors'
  | string

export type PendingMentorRow = {
  id: number
  name: string
  email: string
  type: string
}

export type ScheduledEmailReplyStats = {
  mentors_emailed?: number
  mentors_replied?: number
  mentors_responded?: number
  mentors_selected_practices?: number
  mentors_pending?: number
  pending_mentor_ids?: number[]
  pending_mentors?: PendingMentorRow[]
}

export type ScheduledEmail = {
  id: number
  scheduled_send_at: string
  body_text?: string
  practices?: number[]
  recipient_mode?: ScheduledEmailRecipientMode
  recipient_season?: number | null
  specific_mentors?: number[]
  task_completed_at?: string | null
  recipients_emailed_count?: number | null
  reply_stats?: ScheduledEmailReplyStats | null
  pending_mentors?: PendingMentorRow[]
}

export type ScheduledEmailPendingMentorsResponse = {
  pending_mentors?: Array<
    PendingMentorRow & {
      mentor_id?: number
      first_name?: string
      last_name?: string
      mentor_type?: string
    }
  >
}

export type SendEmailResult = {
  sent?: number
  recipients?: number
}

export type ServerConfig = {
  time_zone: string
}

export type AttendanceShowUp = 'attended' | 'missed' | 'found_replacement'

export type PracticeAttendanceMentor = {
  mentor_id: number
  first_name?: string | null
  last_name?: string | null
  pace?: string | null
  show_up?: AttendanceShowUp | null
  swapped_out?: boolean
}

export type PracticeAttendanceDetail = {
  practice_id: number
  date: string
  nyrr_race?: string
  description?: string
  start_location?: string
  season_id?: number | null
  season_year?: number | null
  full_practice?: boolean
  attendance_comments?: string
  assigned_mentors?: PracticeAttendanceMentor[]
  is_current_window?: boolean
}

export type PracticeAttendanceCurrentResponse = {
  practice: PracticeAttendanceDetail | null
}

export type ArchivedPracticeAttendance = {
  practice_id: number
  date: string
  nyrr_race?: string
  season_id?: number | null
  season_year?: number | null
  assigned_count: number
  attended_count: number
  missed_count: number
  found_replacement_count?: number
  unset_count: number
  assigned_mentors?: PracticeAttendanceMentor[]
}

export type JsonObject = Record<string, unknown>

export type CsvImportResult = {
  created?: number
  updated?: number
  skipped?: number
  errors?: string[]
  created_by_season?: Record<string, number>
}

export type MentorEmailReplyPractice = {
  id: number
  date: string
  nyrr_race: string
  full_practice: boolean
  season_id: number
  attendance?: string | null
  pace?: string
}

export type MentorEmailReplyMentor = {
  id: number
  first_name: string
  last_name: string
  email?: string
  cell_phone?: string
  type?: string
  pace?: string
  split_practice?: boolean
  season_years?: number[]
}

export type MentorEmailReplyResponse = {
  mentor: MentorEmailReplyMentor
  season_year?: number | null
  assigned_pace?: string
  scheduled_send_at?: string
  practices: MentorEmailReplyPractice[]
  pace_choices: string[]
  email_received_confirmed?: boolean
  shows_partial_month?: boolean
  selection_closed?: boolean
  has_practice_selection?: boolean
}

export type MentorEmailReplyPutPayload = {
  replies: { practice: number; attendance: string; pace?: string }[]
  email_received_confirmed?: boolean
  mentor_pace?: string
  cell_phone?: string
}

export type MentorCellPhoneMissingMentor = {
  id: number
  first_name: string
  last_name: string
  email?: string
  type?: string
  cell_phone?: string
}

export type MentorCellPhoneRequestRecipient = {
  mentor_id: number
  first_name: string
  last_name: string
  email?: string
  used_at?: string | null
}

export type MentorCellPhoneRequestSendBatch = {
  id: number
  sent_at?: string | null
  recipients_emailed_count: number
  season_id?: number | null
  season_year?: number | null
  recipients?: MentorCellPhoneRequestRecipient[]
}

export type MentorCellPhoneRequestsResponse = {
  missing_mentors: MentorCellPhoneMissingMentor[]
  sends: MentorCellPhoneRequestSendBatch[]
}

export type MentorCellPhoneSendResult = {
  sent?: number
  recipients?: number
  subject?: string
  send_id?: number
  sent_at?: string
}

export type MentorCellPhoneUpdateGetResponse = {
  token?: string
  first_name?: string
  last_name?: string
  email?: string
  detail?: string
  already_used?: boolean
  already_complete?: boolean
}

export type MentorCellPhoneUpdatePutResponse = {
  detail?: string
  completed?: boolean
}
