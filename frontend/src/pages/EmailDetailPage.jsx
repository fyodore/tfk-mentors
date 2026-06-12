import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  fetchMentors,
  fetchPractices,
  fetchScheduledEmail,
  fetchScheduledEmailPendingMentors,
  fetchSeasons,
  previewScheduledEmailReplyReminders,
  sendScheduledEmailReplyReminders,
} from '../api'
import { practiceLabelsForIds, recipientSummaryText, pendingMentorsForEmail, normalizePendingMentorRows, sentEmailReplyStats } from '../emailHelpers.js'
import { AppHeader } from '../components/AppHeader.jsx'
import { formatDateTime } from '../datetime.js'

function sortPracticesByDateAsc(list) {
  return [...list].sort((a, b) => {
    const ta = new Date(a.date).getTime()
    const tb = new Date(b.date).getTime()
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || a.id - b.id
  })
}

export default function EmailDetailPage() {
  const { id } = useParams()
  const emailId = Number.parseInt(String(id), 10)

  const [email, setEmail] = useState(null)
  const [practices, setPractices] = useState([])
  const [seasons, setSeasons] = useState([])
  const [mentors, setMentors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reminderBusy, setReminderBusy] = useState(false)
  const [reminderMessage, setReminderMessage] = useState(null)
  const [reminderError, setReminderError] = useState(null)
  const [pendingMentorsLoaded, setPendingMentorsLoaded] = useState([])
  const [pendingMentorsLoading, setPendingMentorsLoading] = useState(false)
  const [pendingMentorsLoadFailed, setPendingMentorsLoadFailed] = useState(false)

  const reloadEmail = async () => {
    const emailRow = await fetchScheduledEmail(emailId)
    setEmail(emailRow)
    return emailRow
  }

  const seasonYearById = useMemo(() => {
    const m = new Map()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  const practiceById = useMemo(() => {
    const m = new Map()
    for (const p of practices) m.set(p.id, p)
    return m
  }, [practices])

  const practiceLabel = (p) => {
    const when = formatDateTime(p.date)
    const year = seasonYearById.get(p.season) ?? p.season
    const race = p.nyrr_race?.trim()
    return `${when} · Season ${year}${race ? ` · ${race}` : ''}`
  }

  useEffect(() => {
    let cancelled = false
    if (Number.isNaN(emailId)) {
      setError('Invalid email id.')
      setLoading(false)
      return () => {
        cancelled = true
      }
    }

    setLoading(true)
    setError(null)
    Promise.all([
      fetchScheduledEmail(emailId),
      fetchPractices(),
      fetchSeasons(),
      fetchMentors(),
    ])
      .then(([emailRow, pList, sList, mList]) => {
        if (!cancelled) {
          setEmail(emailRow)
          setPractices(sortPracticesByDateAsc(pList))
          setSeasons(sList)
          setMentors(mList)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setEmail(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [emailId])

  const linkedPractices = useMemo(
    () =>
      practiceLabelsForIds(email?.practices ?? [], (pid) => {
        const p = practiceById.get(pid)
        return p ? practiceLabel(p) : `Practice #${pid}`
      }),
    [email?.practices, practiceById, seasonYearById]
  )

  const specificMentorNames = useMemo(() => {
    if (email?.recipient_mode !== 'specific_mentors') return []
    return (email.specific_mentors ?? []).map((mid) => {
      const m = mentors.find((x) => x.id === mid)
      return m ? `${m.first_name} ${m.last_name} · ${m.email}` : `Mentor #${mid}`
    })
  }, [email, mentors])

  const isSent = Boolean(email?.task_completed_at)
  const replyStats = email ? sentEmailReplyStats(email) : null
  const pendingMentorsFromEmail = useMemo(
    () => (email ? pendingMentorsForEmail(email, mentors) : []),
    [email, mentors]
  )
  const pendingMentors =
    pendingMentorsFromEmail.length > 0
      ? pendingMentorsFromEmail
      : pendingMentorsLoaded

  useEffect(() => {
    setPendingMentorsLoaded([])
    setPendingMentorsLoadFailed(false)
    setPendingMentorsLoading(false)
  }, [emailId])

  useEffect(() => {
    if (!email?.task_completed_at || !replyStats?.pending) return
    if (pendingMentorsFromEmail.length > 0) return

    let cancelled = false
    setPendingMentorsLoading(true)
    setPendingMentorsLoadFailed(false)

    async function loadPendingMentors() {
      try {
        const data = await fetchScheduledEmailPendingMentors(email.id)
        if (cancelled) return
        const rows = normalizePendingMentorRows(data?.pending_mentors)
        if (rows.length > 0) {
          setPendingMentorsLoaded(rows)
          return
        }
      } catch {
        if (cancelled) return
      }

      try {
        const preview = await previewScheduledEmailReplyReminders(email.id)
        if (cancelled) return
        const rows = normalizePendingMentorRows(preview?.pending_mentors)
        if (rows.length > 0) {
          setPendingMentorsLoaded(rows)
          return
        }
      } catch {
        if (cancelled) return
      }

      if (!cancelled) {
        setPendingMentorsLoadFailed(true)
      }
    }

    loadPendingMentors().finally(() => {
      if (!cancelled) setPendingMentorsLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [email, replyStats?.pending, pendingMentorsFromEmail.length])

  const handleSendReplyReminders = async () => {
    if (!email || !replyStats?.pending) return
    if (
      !window.confirm(
        `Send a reminder email to ${replyStats.pending} mentor${
          replyStats.pending === 1 ? '' : 's'
        } who ${replyStats.pending === 1 ? 'has' : 'have'} not replied?`
      )
    ) {
      return
    }
    setReminderBusy(true)
    setReminderMessage(null)
    setReminderError(null)
    try {
      const result = await sendScheduledEmailReplyReminders(email.id)
      await reloadEmail()
      const sent = result.sent ?? 0
      setReminderMessage(
        sent === 1
          ? 'Reminder sent to 1 mentor.'
          : `Reminders sent to ${sent} mentors.`
      )
    } catch (e) {
      setReminderError(e instanceof Error ? e.message : String(e))
    } finally {
      setReminderBusy(false)
    }
  }

  return (
    <>
      <AppHeader title="Email" />

      <main className="panel email-detail-panel">
        <p className="email-detail-back">
          <Link to="/emails" className="nav-back">
            ← Back to emails
          </Link>
        </p>

        {loading && <p className="muted">Loading…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && email && (
          <>
            <header className="email-detail-header">
              <h2>
                {isSent
                  ? `Sent · ${formatDateTime(email.task_completed_at)}`
                  : `Scheduled · ${formatDateTime(email.scheduled_send_at)}`}
              </h2>
              {isSent ? (
                <p className="muted">
                  Originally scheduled {formatDateTime(email.scheduled_send_at)}
                </p>
              ) : null}
            </header>

            <section className="email-detail-section">
              <h3>Recipients</h3>
              <p>{recipientSummaryText(email, { seasonYearById, mentors })}</p>
              {isSent && replyStats ? (
                <div className="email-reply-stats" aria-label="Reply summary">
                  <span className="email-reply-stat">
                    {replyStats.replied} mentor{replyStats.replied === 1 ? '' : 's'}{' '}
                    replied
                  </span>
                  <span className="email-reply-stat-sep" aria-hidden="true">
                    ·
                  </span>
                  <span className="email-reply-stat">
                    {replyStats.selectedPractices} selected practice
                    {replyStats.selectedPractices === 1 ? '' : 's'}
                  </span>
                  <span className="email-reply-stat-sep" aria-hidden="true">
                    ·
                  </span>
                  <span className="email-reply-stat">
                    {replyStats.pending} awaiting response
                  </span>
                </div>
              ) : null}
              {isSent && replyStats && replyStats.pending > 0 ? (
                <>
                  <div className="email-pending-mentors">
                    <h4 className="email-pending-mentors-heading">
                      Mentors awaiting response (
                      {pendingMentors.length || replyStats.pending})
                    </h4>
                    {pendingMentorsLoading ? (
                      <p className="muted email-pending-mentors-empty">
                        Loading mentors awaiting response…
                      </p>
                    ) : pendingMentors.length > 0 ? (
                      <ul className="email-detail-list email-pending-mentors-list">
                        {pendingMentors.map((m) => (
                          <li key={m.id}>
                            <strong>{m.name}</strong>
                            {m.email ? (
                              <span className="muted"> · {m.email}</span>
                            ) : null}
                            {m.type ? (
                              <span className="muted"> · {m.type}</span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : pendingMentorsLoadFailed ? (
                      <p className="muted email-pending-mentors-empty">
                        Could not load mentor names. Redeploy the backend, then
                        refresh this page.
                      </p>
                    ) : null}
                  </div>
                  <div className="email-detail-actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={reminderBusy}
                      onClick={handleSendReplyReminders}
                    >
                      {reminderBusy
                        ? 'Sending reminders…'
                        : `Send reminder to ${replyStats.pending} awaiting`}
                    </button>
                  </div>
                </>
              ) : null}
              {reminderMessage ? (
                <p className="email-detail-notice">{reminderMessage}</p>
              ) : null}
              {reminderError ? (
                <p className="error" role="alert">
                  {reminderError}
                </p>
              ) : null}
              {email.recipient_mode === 'specific_mentors' &&
              specificMentorNames.length > 0 ? (
                <ul className="email-detail-list">
                  {specificMentorNames.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              ) : null}
            </section>

            <section className="email-detail-section">
              <h3>Practices</h3>
              {linkedPractices.length === 0 ? (
                <p className="muted">No practices linked.</p>
              ) : (
                <ul className="email-detail-list">
                  {linkedPractices.map(({ id: pid, label }) => (
                    <li key={pid}>
                      <Link to={`/practices/${pid}`} className="nav-back">
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="email-detail-section">
              <h3>Email template</h3>
              <pre className="email-detail-body">{email.body_text || ''}</pre>
              <p className="muted email-detail-placeholders">
                Placeholders: <code>{'{{ first_name }}'}</code>,{' '}
                <code>{'{{ last_name }}'}</code>, <code>{'{{ year }}'}</code>,{' '}
                <code>{'{{ pace }}'}</code>, <code>{'{{ link }}'}</code>
              </p>
            </section>
          </>
        )}
      </main>
    </>
  )
}
