import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  fetchPracticeReminderEmail,
  fetchPractices,
  fetchSeasons,
} from '../api'
import { AppHeader } from '../components/AppHeader.tsx'
import { formatDateTime } from '../datetime.js'
import type {
  Practice,
  PracticeReminderEmail,
  Season,
} from '../types.js'

function sortPracticesByDateAsc(list: Practice[]) {
  return [...list].sort((a, b) => {
    const ta = new Date(a.date ?? '').getTime()
    const tb = new Date(b.date ?? '').getTime()
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || a.id - b.id
  })
}

export default function PracticeReminderDetailPage() {
  const { id } = useParams()
  const reminderId = Number.parseInt(String(id), 10)

  const [reminder, setReminder] = useState<PracticeReminderEmail | null>(null)
  const [practices, setPractices] = useState<Practice[]>([])
  const [seasons, setSeasons] = useState<Season[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedRecordId, setExpandedRecordId] = useState<number | null>(null)

  const seasonYearById = useMemo(() => {
    const m = new Map<number, number>()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  const practiceById = useMemo(() => {
    const m = new Map<number, Practice>()
    for (const p of practices) m.set(p.id, p)
    return m
  }, [practices])

  const practiceLabel = (practiceId: number) => {
    const p = practiceById.get(practiceId)
    if (!p) return `Practice #${practiceId}`
    const when = formatDateTime(p.date)
    const year = seasonYearById.get(p.season ?? -1) ?? p.season
    const race = p.nyrr_race?.trim()
    return `${when} · Season ${year}${race ? ` · ${race}` : ''}`
  }

  useEffect(() => {
    let cancelled = false
    if (Number.isNaN(reminderId)) {
      setError('Invalid practice reminder id.')
      setLoading(false)
      return () => {
        cancelled = true
      }
    }

    setLoading(true)
    setError(null)
    Promise.all([
      fetchPracticeReminderEmail(reminderId),
      fetchPractices(),
      fetchSeasons(),
    ])
      .then(([row, pList, sList]) => {
        if (!cancelled) {
          setReminder(row)
          setPractices(sortPracticesByDateAsc(pList))
          setSeasons(sList)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setReminder(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [reminderId])

  const sendRecords = reminder?.send_records ?? []

  return (
    <>
      <AppHeader />

      <main className="panel emails-panel">
        <Link to="/emails" className="nav-back">
          ← Emails
        </Link>

        <h2>Practice reminder</h2>

        {loading && <p className="muted">Loading…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && reminder && (
          <>
            <div className="email-detail-meta">
              <p>
                <strong>After practice:</strong>{' '}
                {practiceLabel(reminder.anchor_practice)}
              </p>
              <p>
                <strong>Covers:</strong> {practiceLabel(reminder.practice_one)}
                {reminder.practice_two != null
                  ? ` and ${practiceLabel(reminder.practice_two)}`
                  : ''}
              </p>
              <p>
                <strong>Sent:</strong> {formatDateTime(reminder.task_completed_at)}
              </p>
              <p>
                <strong>Originally scheduled:</strong>{' '}
                {formatDateTime(reminder.scheduled_send_at)}
              </p>
              <p>
                <strong>Recipients emailed:</strong>{' '}
                {reminder.recipients_emailed_count ?? sendRecords.length}
              </p>
            </div>

            <section aria-labelledby="send-history-heading">
              <h3 id="send-history-heading">Send history</h3>
              {sendRecords.length === 0 ? (
                <p className="muted">No send records stored.</p>
              ) : (
                <ul className="practice-list">
                  {sendRecords.map((record) => {
                    const name = `${record.recipient_first_name || ''} ${record.recipient_last_name || ''}`.trim()
                    const expanded = expandedRecordId === record.id
                    return (
                      <li key={record.id} className="practice-row email-row">
                        <div className="practice-row-main">
                          <span className="practice-date">
                            {name || record.recipient_email}
                          </span>
                          <span className="muted">{record.recipient_email}</span>
                          <span className="muted">{record.recipient_kind}</span>
                          <span className="muted">{record.rendered_subject}</span>
                        </div>
                        <div className="practice-row-actions email-row-actions">
                          <button
                            type="button"
                            className="btn btn-text"
                            onClick={() =>
                              setExpandedRecordId(expanded ? null : record.id)
                            }
                          >
                            {expanded ? 'Hide email' : 'View email'}
                          </button>
                        </div>
                        {expanded ? (
                          <pre className="email-history-body">{record.rendered_body}</pre>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>
          </>
        )}
      </main>
    </>
  )
}
