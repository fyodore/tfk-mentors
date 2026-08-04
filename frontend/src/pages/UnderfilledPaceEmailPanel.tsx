import { useEffect, useMemo, useState } from 'react'

import {
  fetchSeasons,
  fetchUnderfilledPaceEmails,
  sendUnderfilledPaceEmails,
} from '../api'
import { formatDateTime } from '../datetime.js'
import {
  currentSeasonFromList,
  sortSeasonsByYearDesc,
} from '../seasonHelpers.js'
import type { Season, UnderfilledPaceEmailSendBatch } from '../types.js'

export default function UnderfilledPaceEmailPanel() {
  const [seasons, setSeasons] = useState<Season[]>([])
  const [seasonFilter, setSeasonFilter] = useState('')
  const [sends, setSends] = useState<UnderfilledPaceEmailSendBatch[]>([])
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
      const data = await fetchUnderfilledPaceEmails(seasonId || null)
      setSends(Array.isArray(data.sends) ? data.sends : [])
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : String(e))
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
        const data = await fetchUnderfilledPaceEmails(initial || null)
        if (cancelled) return
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
      const result = await sendUnderfilledPaceEmails({
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
    <div className="underfilled-pace-email-panel">
      <p className="muted">
        Email At Practice mentors whose profile pace group has fewer than 3
        assigned mentors at one or more upcoming practices. Recipients are built
        when you click send; each email includes a personal response link.
      </p>

      <div className="practices-filter">
        <label className="field-label" htmlFor="underfilled-pace-season-filter">
          Season
        </label>
        <select
          id="underfilled-pace-season-filter"
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

      <div className="practices-toolbar practices-toolbar-secondary">
        <button
          type="button"
          className="btn btn-primary"
          disabled={sending || !seasonFilter || loading}
          onClick={handleSend}
        >
          {sending ? 'Sending…' : 'Send underfilled pace emails'}
        </button>
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

      {!loading && (
        <section
          className="email-section"
          aria-labelledby="underfilled-pace-sends-heading"
        >
          <h3 id="underfilled-pace-sends-heading">Recent sends</h3>
          {sends.length === 0 ? (
            <p className="muted">No underfilled pace emails have been sent yet.</p>
          ) : (
            <ul className="practice-list">
              {sends.map((batch) => (
                <li key={batch.id} className="practice-row">
                  <div className="practice-row-main">
                    <span className="practice-date">
                      {formatDateTime(batch.sent_at)}
                    </span>
                    <span className="muted">
                      {batch.recipients_emailed_count} recipient
                      {batch.recipients_emailed_count === 1 ? '' : 's'}
                    </span>
                    {batch.season_year != null ? (
                      <span className="muted">Season {batch.season_year}</span>
                    ) : null}
                  </div>
                  {(batch.recipients ?? []).length > 0 ? (
                    <ul className="cell-phone-request-recipients">
                      {(batch.recipients ?? []).map((recipient) => (
                        <li key={recipient.mentor_id}>
                          {recipient.first_name} {recipient.last_name}
                          {recipient.responded_at
                            ? ` — responded (${recipient.response_type || 'yes'})`
                            : ' — pending'}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
