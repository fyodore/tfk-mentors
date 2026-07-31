import { useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  createPublicMentorSwapRequest,
  fetchPublicPracticeSwapOptions,
  fetchPublicUpcomingPractices,
} from '../api'
import { formatMentorDirectoryPracticeDate } from '../datetime.js'
import { PACE_GROUPS, paceSortKey } from '../paceHelpers.js'
import type {
  PublicPracticeSwapOptions,
  PublicSwapMentorOption,
  PublicUpcomingPractice,
} from '../types.js'

type PaceMentorGroup = {
  pace: string
  label: string
  mentors: PublicSwapMentorOption[]
}

function personName(row: PublicSwapMentorOption): string {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim()
}

function practiceLabel(practice: PublicUpcomingPractice): string {
  const when = practice.date
    ? formatMentorDirectoryPracticeDate(practice.date)
    : '—'
  const race = practice.nyrr_race?.trim()
  return race ? `${when} · ${race}` : when
}

function sortByLastName(list: PublicSwapMentorOption[]): PublicSwapMentorOption[] {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    return (a.first_name || '').localeCompare(b.first_name || '')
  })
}

function groupMentorsByPace(
  mentors: PublicSwapMentorOption[]
): PaceMentorGroup[] {
  const byPace = new Map<string, PublicSwapMentorOption[]>()
  for (const mentor of mentors) {
    const pace = mentor.pace?.trim() || ''
    const key = pace || '__none__'
    if (!byPace.has(key)) byPace.set(key, [])
    byPace.get(key)!.push(mentor)
  }

  const groups: PaceMentorGroup[] = []
  for (const pace of PACE_GROUPS) {
    if (!byPace.has(pace)) continue
    groups.push({
      pace,
      label: `Pace ${pace}`,
      mentors: sortByLastName(byPace.get(pace)!),
    })
    byPace.delete(pace)
  }

  for (const [pace, paceMentors] of [...byPace.entries()].sort(
    ([a], [b]) => paceSortKey(a) - paceSortKey(b) || a.localeCompare(b)
  )) {
    groups.push({
      pace,
      label: pace && pace !== '__none__' ? `Pace ${pace}` : 'No pace',
      mentors: sortByLastName(paceMentors),
    })
  }

  return groups
}

export function MentorDirectoryRequestSwapTab() {
  const [practices, setPractices] = useState<PublicUpcomingPractice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [practiceId, setPracticeId] = useState('')
  const [options, setOptions] = useState<PublicPracticeSwapOptions | null>(null)
  const [optionsLoading, setOptionsLoading] = useState(false)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [outgoingId, setOutgoingId] = useState('')
  const [incomingId, setIncomingId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.resolve().then(async () => {
      setLoading(true)
      setError(null)
      try {
        const rows = await fetchPublicUpcomingPractices()
        if (!cancelled) setPractices(Array.isArray(rows) ? rows : [])
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setPractices([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!practiceId) {
      setOptions(null)
      setOptionsError(null)
      setOutgoingId('')
      setIncomingId('')
      return undefined
    }

    let cancelled = false
    Promise.resolve().then(async () => {
      setOptionsLoading(true)
      setOptionsError(null)
      setOutgoingId('')
      setIncomingId('')
      setSuccessMessage(null)
      try {
        const data = await fetchPublicPracticeSwapOptions(practiceId)
        if (!cancelled) setOptions(data)
      } catch (e) {
        if (!cancelled) {
          setOptions(null)
          setOptionsError(e instanceof Error ? e.message : String(e))
        }
      } finally {
        if (!cancelled) setOptionsLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [practiceId])

  const attendingGroups = useMemo(
    () => groupMentorsByPace(options?.attending_mentors ?? []),
    [options]
  )
  const incomingGroups = useMemo(
    () => groupMentorsByPace(options?.incoming_mentors ?? []),
    [options]
  )

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!practiceId || !outgoingId || !incomingId || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    setSuccessMessage(null)
    try {
      await createPublicMentorSwapRequest({
        practice: Number(practiceId),
        outgoing_mentor: Number(outgoingId),
        incoming_mentor: Number(incomingId),
      })
      setSuccessMessage(
        'Swap request submitted. The requested mentor will receive an email to approve or reject.'
      )
      setOutgoingId('')
      setIncomingId('')
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <p className="muted">Loading practices…</p>
  if (error) {
    return (
      <p className="error" role="alert">
        {error}
      </p>
    )
  }
  if (practices.length === 0) {
    return (
      <p className="muted">
        No upcoming practices are available for swap requests.
      </p>
    )
  }

  return (
    <div className="mentor-directory-request-swap">
      <p className="muted mentor-directory-request-swap-intro">
        Request a mentor swap for an upcoming practice. The replacement mentor
        will get an email to approve or reject.
      </p>

      <form
        className="mentor-directory-request-swap-form"
        onSubmit={handleSubmit}
      >
        <label className="field-label" htmlFor="swap-practice-select">
          Practice
        </label>
        <select
          id="swap-practice-select"
          className="field-input field-select"
          value={practiceId}
          onChange={(e) => setPracticeId(e.target.value)}
          required
        >
          <option value="">Select a practice</option>
          {practices.map((practice) => (
            <option key={practice.id} value={practice.id}>
              {practiceLabel(practice)}
            </option>
          ))}
        </select>

        {practiceId ? (
          <>
            {optionsLoading ? <p className="muted">Loading mentors…</p> : null}
            {optionsError ? (
              <p className="error" role="alert">
                {optionsError}
              </p>
            ) : null}

            {options ? (
              <>
                <label className="field-label" htmlFor="swap-outgoing-select">
                  Mentor to replace
                </label>
                <select
                  id="swap-outgoing-select"
                  className="field-input field-select"
                  value={outgoingId}
                  onChange={(e) => setOutgoingId(e.target.value)}
                  required
                >
                  <option value="">Select attending mentor</option>
                  {attendingGroups.map((group) => (
                    <optgroup key={group.pace} label={group.label}>
                      {group.mentors.map((mentor) => (
                        <option key={mentor.mentor_id} value={mentor.mentor_id}>
                          {personName(mentor)}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                {(options.attending_mentors ?? []).length === 0 ? (
                  <p className="muted">
                    No mentors are attending this practice.
                  </p>
                ) : null}

                <label className="field-label" htmlFor="swap-incoming-select">
                  Mentor to swap in
                </label>
                <select
                  id="swap-incoming-select"
                  className="field-input field-select"
                  value={incomingId}
                  onChange={(e) => setIncomingId(e.target.value)}
                  required
                >
                  <option value="">Select replacement mentor</option>
                  {incomingGroups.map((group) => (
                    <optgroup key={group.pace} label={group.label}>
                      {group.mentors.map((mentor) => (
                        <option key={mentor.mentor_id} value={mentor.mentor_id}>
                          {personName(mentor)}
                          {mentor.type === 'Remote' ? ' (Remote)' : ''}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                {(options.incoming_mentors ?? []).length === 0 ? (
                  <p className="muted">
                    No eligible replacement mentors (season mentors with a pace
                    who are not attending).
                  </p>
                ) : null}

                <div className="mentor-directory-request-swap-actions">
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={
                      submitting ||
                      !outgoingId ||
                      !incomingId ||
                      (options.attending_mentors ?? []).length === 0 ||
                      (options.incoming_mentors ?? []).length === 0
                    }
                  >
                    {submitting ? 'Submitting…' : 'Send swap request'}
                  </button>
                </div>
              </>
            ) : null}
          </>
        ) : null}

        {submitError ? (
          <p className="error" role="alert">
            {submitError}
          </p>
        ) : null}
        {successMessage ? (
          <p className="mentor-directory-request-swap-success" role="status">
            {successMessage}
          </p>
        ) : null}
      </form>
    </div>
  )
}
