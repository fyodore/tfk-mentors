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
  full_practice?: boolean
  show_to_mentors?: boolean
  description?: string | null
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
