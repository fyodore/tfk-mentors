import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  deletePracticeReminderEmail,
  fetchPracticeReminderEmails,
  fetchPractices,
  fetchSeasons,
  patchPracticeReminderEmail,
  sendPracticeReminderEmailNow,
} from '../api'
import { currentSeasonFromList, sortSeasonsByYearDesc } from '../seasonHelpers.js'
import { Modal } from '../components/Modal.jsx'
import {
  buildQuarterTimeOptions,
  dateAndQuarterTimeToIso,
  formatDateTime,
  isoToDateAndQuarterTime,
} from '../datetime.js'

const DEFAULT_BODY = `Dear {{first_name}},

If you haven't done so, please join our facebook group: https://www.facebook.com/groups/{{year}}tfkmentors/.

{{practice_1_section}}

{{mentor_practice_1_notice}}

{{practice_2_section}}

{{mentor_practice_2_notice}}`

function isoToSendDateAndTime(iso) {
  const { date, time } = isoToDateAndQuarterTime(iso)
  return { sendDate: date, sendTime: time }
}

function sortPracticesByDateAsc(list) {
  return [...list].sort((a, b) => {
    const ta = new Date(a.date).getTime()
    const tb = new Date(b.date).getTime()
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || a.id - b.id
  })
}

export default function PracticeReminderEmailsPanel() {
  const [reminders, setReminders] = useState([])
  const [practices, setPractices] = useState([])
  const [seasons, setSeasons] = useState([])
  const [seasonFilter, setSeasonFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [modal, setModal] = useState(null)
  const [activeReminder, setActiveReminder] = useState(null)
  const [form, setForm] = useState({ sendDate: '', sendTime: '06:15', subject: '', body_text: DEFAULT_BODY })
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sendingId, setSendingId] = useState(null)

  const quarterTimeOptions = useMemo(() => buildQuarterTimeOptions(), [])

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

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

  const practiceLabel = (practiceId) => {
    const p = practiceById.get(practiceId)
    if (!p) return `Practice #${practiceId}`
    const when = formatDateTime(p.date)
    const year = seasonYearById.get(p.season) ?? p.season
    const race = p.nyrr_race?.trim()
    return `${when} · Season ${year}${race ? ` · ${race}` : ''}`
  }

  const upcomingReminders = useMemo(() => {
    return [...reminders]
      .filter((row) => !row.task_completed_at)
      .sort((a, b) => {
        const ta = new Date(a.scheduled_send_at).getTime()
        const tb = new Date(b.scheduled_send_at).getTime()
        return (
          (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || a.id - b.id
        )
      })
  }, [reminders])

  const sentReminders = useMemo(() => {
    return [...reminders]
      .filter((row) => Boolean(row.task_completed_at))
      .sort((a, b) => {
        const ta = new Date(a.task_completed_at).getTime()
        const tb = new Date(b.task_completed_at).getTime()
        return (
          (Number.isNaN(tb) ? 0 : tb) - (Number.isNaN(ta) ? 0 : ta) || b.id - a.id
        )
      })
  }, [reminders])

  async function reloadReminders(seasonId) {
    const sid = seasonId ?? seasonFilter
    if (!sid) {
      setReminders([])
      return
    }
    const list = await fetchPracticeReminderEmails(sid)
    setReminders(list)
  }

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [pList, sList] = await Promise.all([fetchPractices(), fetchSeasons()])
        if (cancelled) return
        setPractices(sortPracticesByDateAsc(pList))
        setSeasons(sList)
        const current = currentSeasonFromList(sList)
        const sid = current?.id != null ? String(current.id) : ''
        setSeasonFilter(sid)
        if (sid) {
          const list = await fetchPracticeReminderEmails(sid)
          if (!cancelled) setReminders(list)
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setReminders([])
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
    if (!seasonFilter || loading) return
    let cancelled = false

    reloadReminders(seasonFilter).catch((e) => {
      if (!cancelled) {
        setLoadError(e instanceof Error ? e.message : String(e))
      }
    })

    return () => {
      cancelled = true
    }
  }, [seasonFilter])

  function resetModal() {
    setModal(null)
    setActiveReminder(null)
    setModalError('')
  }

  function closeModal() {
    if (busy) return
    resetModal()
  }

  function openEdit(row) {
    setModalError('')
    setActiveReminder(row)
    const { sendDate, sendTime } = isoToSendDateAndTime(row.scheduled_send_at)
    setForm({
      sendDate,
      sendTime,
      subject: row.subject ?? '',
      body_text: row.body_text ?? DEFAULT_BODY,
    })
    setModal('edit')
  }

  function openDelete(row) {
    setModalError('')
    setActiveReminder(row)
    setModal('delete')
  }

  async function handleSaveEdit() {
    if (!activeReminder) return
    const scheduled_send_at = dateAndQuarterTimeToIso(form.sendDate, form.sendTime)
    if (!scheduled_send_at) {
      setModalError('Schedule date and time are required (15-minute times).')
      return
    }
    const subject = form.subject.trim()
    const body_text = form.body_text.trim()
    if (!subject) {
      setModalError('Subject is required.')
      return
    }
    if (!body_text) {
      setModalError('Email text is required.')
      return
    }
    setBusy(true)
    setModalError('')
    try {
      await patchPracticeReminderEmail(activeReminder.id, {
        scheduled_send_at,
        subject,
        body_text,
      })
      await reloadReminders()
      resetModal()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!activeReminder) return
    setBusy(true)
    setModalError('')
    try {
      await deletePracticeReminderEmail(activeReminder.id)
      await reloadReminders()
      resetModal()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleSendNow(row) {
    setSendingId(row.id)
    setLoadError(null)
    try {
      await sendPracticeReminderEmailNow(row.id)
      await reloadReminders()
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    } finally {
      setSendingId(null)
    }
  }

  function reminderSummary(row) {
    const after = practiceLabel(row.anchor_practice)
    const first = practiceLabel(row.practice_one)
    const second =
      row.practice_two != null ? practiceLabel(row.practice_two) : null
    return (
      <>
        <span className="practice-date">After {after}</span>
        <span className="muted">Covers {first}</span>
        {second ? <span className="muted">and {second}</span> : null}
      </>
    )
  }

  function renderUpcomingRow(row) {
    const sending = sendingId === row.id
    return (
      <li key={row.id} className="practice-row email-row">
        <div className="practice-row-main">
          {reminderSummary(row)}
          <span className="muted">
            Scheduled {formatDateTime(row.scheduled_send_at)}
          </span>
          <span className="muted">
            {row.recipient_count ?? 0} recipient
            {(row.recipient_count ?? 0) === 1 ? '' : 's'}
          </span>
        </div>
        <div className="practice-row-actions email-row-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={loading || sending || busy}
            onClick={() => handleSendNow(row)}
          >
            {sending ? 'Sending…' : 'Send now'}
          </button>
          <button
            type="button"
            className="btn btn-text"
            disabled={loading || sending || busy}
            onClick={() => openEdit(row)}
          >
            Edit
          </button>
          <button
            type="button"
            className="btn btn-text btn-text-danger"
            disabled={loading || sending || busy}
            onClick={() => openDelete(row)}
          >
            Delete
          </button>
        </div>
      </li>
    )
  }

  function renderSentRow(row) {
    return (
      <li key={row.id} className="practice-row email-row">
        <div className="practice-row-main">
          {reminderSummary(row)}
          <span className="practice-date">
            Sent · {formatDateTime(row.task_completed_at)}
          </span>
          <span className="muted">
            Originally scheduled {formatDateTime(row.scheduled_send_at)}
          </span>
          <span className="muted">
            {row.recipients_emailed_count ?? 0} recipient
            {(row.recipients_emailed_count ?? 0) === 1 ? '' : 's'} emailed
          </span>
        </div>
        <div className="practice-row-actions email-row-actions">
          <Link
            to={`/emails/practice-reminder/${row.id}`}
            className="btn btn-text"
          >
            View history
          </Link>
        </div>
      </li>
    )
  }

  return (
    <>
      <p className="muted">
        Practice reminders are generated automatically after each practice for the
        next session(s). They send at 6:15 AM the morning after the anchor practice
        unless you change the schedule. Each recipient gets a personalized email.
      </p>

      <div className="practices-toolbar practices-toolbar-secondary">
        <label className="season-filter-label">
          Season
          <select
            className="season-filter-select"
            value={seasonFilter}
            disabled={loading || busy}
            onChange={(e) => setSeasonFilter(e.target.value)}
          >
            {sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.year}
                {s.is_current ? ' (current)' : ''}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {loadError && (
        <p className="error" role="alert">
          {loadError}
        </p>
      )}

      {!loading && !loadError && (
        <div className="emails-split">
          <section className="email-section" aria-labelledby="reminder-upcoming-heading">
            <h3 id="reminder-upcoming-heading">Upcoming</h3>
            {upcomingReminders.length === 0 ? (
              <p className="muted">No upcoming practice reminders.</p>
            ) : (
              <ul className="practice-list">
                {upcomingReminders.map(renderUpcomingRow)}
              </ul>
            )}
          </section>

          <section className="email-section" aria-labelledby="reminder-sent-heading">
            <h3 id="reminder-sent-heading">Sent</h3>
            {sentReminders.length === 0 ? (
              <p className="muted">No sent practice reminders yet.</p>
            ) : (
              <ul className="practice-list">
                {sentReminders.map(renderSentRow)}
              </ul>
            )}
          </section>
        </div>
      )}

      <Modal
        open={modal === 'edit'}
        title="Edit practice reminder"
        onClose={closeModal}
        footer={
          <>
            <button type="button" className="btn btn-text" disabled={busy} onClick={closeModal}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={handleSaveEdit}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        {modalError ? (
          <p className="error" role="alert">
            {modalError}
          </p>
        ) : null}
        <div className="form-grid">
          <label>
            Send date
            <input
              type="date"
              value={form.sendDate}
              disabled={busy}
              onChange={(e) => setForm((f) => ({ ...f, sendDate: e.target.value }))}
            />
          </label>
          <label>
            Send time
            <select
              value={form.sendTime}
              disabled={busy}
              onChange={(e) => setForm((f) => ({ ...f, sendTime: e.target.value }))}
            >
              {quarterTimeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="form-block">
          Subject
          <input
            type="text"
            value={form.subject}
            disabled={busy}
            onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))}
          />
        </label>
        <label className="form-block">
          Email body template
          <textarea
            className="email-body-textarea"
            rows={16}
            value={form.body_text}
            disabled={busy}
            onChange={(e) => setForm((f) => ({ ...f, body_text: e.target.value }))}
          />
        </label>
        <p className="muted form-hint">
          Placeholders: {'{{first_name}}'}, {'{{last_name}}'}, {'{{year}}'},
          {' {{date_of_practice_1}}'}, {'{{date_of_practice_2}}'},
          {' {{practice_1_section}}'}, {'{{practice_2_section}}'},
          {' {{mentor_practice_1_notice}}'}, {'{{mentor_practice_2_notice}}'}.
          Coach and mentor lists are built automatically inside the section blocks.
        </p>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete practice reminder"
        onClose={closeModal}
        footer={
          <>
            <button type="button" className="btn btn-text" disabled={busy} onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary btn-danger"
              disabled={busy}
              onClick={handleDelete}
            >
              {busy ? 'Deleting…' : 'Delete'}
            </button>
          </>
        }
      >
        {modalError ? (
          <p className="error" role="alert">
            {modalError}
          </p>
        ) : null}
        <p>Delete this unsent practice reminder?</p>
      </Modal>
    </>
  )
}
