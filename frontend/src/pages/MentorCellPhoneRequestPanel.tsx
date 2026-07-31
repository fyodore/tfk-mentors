import { useEffect, useMemo, useState } from 'react'

import {
  fetchMentorCellPhoneRequests,
  fetchSeasons,
  sendMentorCellPhoneRequests,
} from '../api'
import { formatDateTime } from '../datetime.js'
import {
  currentSeasonFromList,
  sortSeasonsByYearDesc,
} from '../seasonHelpers.js'
import type {
  MentorCellPhoneMissingMentor,
  MentorCellPhoneRequestSendBatch,
  Season,
} from '../types.js'

export default function MentorCellPhoneRequestPanel() {
  const [seasons, setSeasons] = useState<Season[]>([])
  const [seasonFilter, setSeasonFilter] = useState('')
  const [missingMentors, setMissingMentors] = useState<MentorCellPhoneMissingMentor[]>(
    []
  )
  const [sends, setSends] = useState<MentorCellPhoneRequestSendBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [sendMessage, setSendMessage] = useState('')

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

  async function load(seasonId: string) {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await fetchMentorCellPhoneRequests(seasonId || null)
      setMissingMentors(
        Array.isArray(data.missing_mentors) ? data.missing_mentors : []
      )
      setSends(Array.isArray(data.sends) ? data.sends : [])
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : String(e))
      setMissingMentors([])
      setSends([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    Promise.resolve().then(async () => {
      try {
        const seasonList = await fetchSeasons()
        if (cancelled) return
        const ordered = sortSeasonsByYearDesc(seasonList)
        setSeasons(ordered)
        const current = currentSeasonFromList(ordered)
        const initial = current ? String(current.id) : ''
        setSeasonFilter(initial)
        setLoading(true)
        setLoadError(null)
        const data = await fetchMentorCellPhoneRequests(initial || null)
        if (cancelled) return
        setMissingMentors(
          Array.isArray(data.missing_mentors) ? data.missing_mentors : []
        )
        setSends(Array.isArray(data.sends) ? data.sends : [])
      } catch (e: unknown) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSeasonChange(value: string) {
    setSeasonFilter(value)
    setSendMessage('')
    await load(value)
  }

  async function handleSend() {
    setSending(true)
    setSendMessage('')
    setLoadError(null)
    try {
      const result = await sendMentorCellPhoneRequests({
        season: seasonFilter || null,
      })
      setSendMessage(
        `Sent ${result.sent ?? 0} email${(result.sent ?? 0) === 1 ? '' : 's'}.`
      )
      await load(seasonFilter)
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="cell-phone-request-panel">
      <p className="muted">
        Mentors assigned to at least one practice in the selected season who do
        not have a cell phone on their profile. Each send creates a unique
        one-time link per mentor.
      </p>

      <div className="practices-filter">
        <label className="field-label" htmlFor="cell-phone-season-filter">
          Season
        </label>
        <select
          id="cell-phone-season-filter"
          className="field-input field-select"
          value={seasonFilter}
          onChange={(e) => handleSeasonChange(e.target.value)}
          disabled={sortedSeasons.length === 0}
        >
          {sortedSeasons.length === 0 ? (
            <option value="">No seasons</option>
          ) : (
            sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.year}
                {s.is_current ? ' (current)' : ''}
              </option>
            ))
          )}
        </select>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {loadError && (
        <p className="error" role="alert">
          {loadError}
        </p>
      )}
      {sendMessage && (
        <p className="success" role="status">
          {sendMessage}
        </p>
      )}

      {!loading && !loadError && (
        <>
          <section
            className="email-section"
            aria-labelledby="missing-cell-heading"
          >
            <div className="practices-toolbar practices-toolbar-secondary">
              <h3 id="missing-cell-heading">
                Missing cell phone ({missingMentors.length})
              </h3>
              <button
                type="button"
                className="btn btn-primary"
                disabled={sending || missingMentors.length === 0}
                onClick={handleSend}
              >
                {sending ? 'Sending…' : 'Send cell phone request emails'}
              </button>
            </div>
            {missingMentors.length === 0 ? (
              <p className="muted">
                No assigned mentors are missing a cell phone for this season.
              </p>
            ) : (
              <ul className="practice-list">
                {missingMentors.map((mentor) => (
                  <li key={mentor.id} className="practice-row">
                    <div className="practice-row-main">
                      <span className="practice-date">
                        {mentor.first_name} {mentor.last_name}
                      </span>
                      <span className="muted">{mentor.email}</span>
                      <span className="muted">{mentor.type}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section
            className="email-section"
            aria-labelledby="cell-phone-sends-heading"
          >
            <h3 id="cell-phone-sends-heading">Recent sends</h3>
            {sends.length === 0 ? (
              <p className="muted">No cell phone request emails sent yet.</p>
            ) : (
              <ul className="practice-list">
                {sends.map((batch) => {
                  const completed = (batch.recipients || []).filter(
                    (row) => row.used_at
                  ).length
                  return (
                    <li key={batch.id} className="practice-row">
                      <div className="practice-row-main">
                        <span className="practice-date">
                          {batch.sent_at
                            ? formatDateTime(batch.sent_at)
                            : '—'}
                        </span>
                        <span className="muted">
                          {batch.recipients_emailed_count} emailed
                          {batch.season_year
                            ? ` · Season ${batch.season_year}`
                            : ''}
                          {` · ${completed} completed`}
                        </span>
                        {(batch.recipients || []).length > 0 ? (
                          <ul className="cell-phone-request-recipients">
                            {(batch.recipients || []).map((row) => (
                              <li key={`${batch.id}-${row.mentor_id}`}>
                                {row.first_name} {row.last_name}
                                {row.used_at ? (
                                  <span className="muted"> — completed</span>
                                ) : (
                                  <span className="muted"> — pending</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}
