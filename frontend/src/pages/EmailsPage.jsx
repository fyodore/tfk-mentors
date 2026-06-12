import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  createScheduledEmail,
  deleteScheduledEmail,
  fetchMentors,
  fetchPractices,
  fetchScheduledEmailPendingMentors,
  fetchScheduledEmails,
  fetchSeasons,
  patchScheduledEmail,
  sendScheduledEmailNow,
} from '../api'
import { normalizePendingMentorRows, pendingMentorsForEmail, recipientSummaryText, scheduledRecipientCount, sentEmailReplyStats } from '../emailHelpers.js'
import { AppHeader } from '../components/AppHeader.jsx'
import { Modal } from '../components/Modal.jsx'
import {
  buildQuarterTimeOptions,
  dateAndQuarterTimeToIso,
  formatDateTime,
  isoToDateAndQuarterTime,
} from '../datetime.js'

const DEFAULT_BODY = `Hi {{ first_name }} {{ last_name }},

Thank you for being a mentor for the {{ year }} NYC Marathon season.

Please confirm which practices you can attend using this personal link:
{{ link }}

Your fastest pace group for these sessions is {{ pace }} min/mile.

Thanks,
Your friendly Mentor Coordinator Ted`

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

function createEmptyEmailForm(defaultSeasonId) {
  return {
    sendDate: '',
    sendTime: '09:00',
    body_text: DEFAULT_BODY,
    practices: [],
    recipient_mode: 'all_in_season',
    recipient_season: defaultSeasonId === '' ? '' : String(defaultSeasonId),
    specific_mentors: [],
  }
}

export default function EmailsPage() {
  const [emails, setEmails] = useState([])
  const [practices, setPractices] = useState([])
  const [seasons, setSeasons] = useState([])
  const [mentors, setMentors] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [modal, setModal] = useState(null)
  const [activeEmail, setActiveEmail] = useState(null)
  const [form, setForm] = useState(() => createEmptyEmailForm(''))
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sendingEmailId, setSendingEmailId] = useState(null)
  const [pendingMentorsByEmailId, setPendingMentorsByEmailId] = useState({})

  const sortedSeasons = useMemo(
    () =>
      [...seasons].sort(
        (a, b) => Number(b.year) - Number(a.year) || b.id - a.id
      ),
    [seasons]
  )

  const quarterTimeOptions = useMemo(() => buildQuarterTimeOptions(), [])

  const mentorsSorted = useMemo(() => {
    return [...mentors].sort((a, b) => {
      const ln = (a.last_name || '').localeCompare(b.last_name || '')
      if (ln !== 0) return ln
      return (a.first_name || '').localeCompare(b.first_name || '')
    })
  }, [mentors])

  const seasonYearById = useMemo(() => {
    const m = new Map()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  const practicesSorted = useMemo(
    () => sortPracticesByDateAsc(practices),
    [practices]
  )

  const practiceLabel = (p) => {
    const when = formatDateTime(p.date)
    const year = seasonYearById.get(p.season) ?? p.season
    const race = p.nyrr_race?.trim()
    return `${when} · Season ${year}${race ? ` · ${race}` : ''}`
  }

  const upcomingEmails = useMemo(() => {
    return [...emails]
      .filter((e) => !e.task_completed_at)
      .sort((a, b) => {
        const ta = new Date(a.scheduled_send_at).getTime()
        const tb = new Date(b.scheduled_send_at).getTime()
        return (
          (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) ||
          a.id - b.id
        )
      })
  }, [emails])

  const sentEmails = useMemo(() => {
    return [...emails]
      .filter((e) => Boolean(e.task_completed_at))
      .sort((a, b) => {
        const ta = new Date(a.task_completed_at).getTime()
        const tb = new Date(b.task_completed_at).getTime()
        return (
          (Number.isNaN(tb) ? 0 : tb) - (Number.isNaN(ta) ? 0 : ta) ||
          b.id - a.id
        )
      })
  }, [emails])

  useEffect(() => {
    let cancelled = false

    async function loadMissingPendingMentors() {
      const rowsNeedingFetch = sentEmails.filter((row) => {
        const stats = sentEmailReplyStats(row)
        if (!stats || stats.pending <= 0) return false
        return pendingMentorsForEmail(row, mentors).length === 0
      })

      if (rowsNeedingFetch.length === 0) return

      const results = await Promise.allSettled(
        rowsNeedingFetch.map(async (row) => {
          const data = await fetchScheduledEmailPendingMentors(row.id)
          return {
            id: row.id,
            mentors: normalizePendingMentorRows(data?.pending_mentors),
          }
        })
      )

      if (cancelled) return

      setPendingMentorsByEmailId((prev) => {
        const next = { ...prev }
        for (const result of results) {
          if (result.status !== 'fulfilled') continue
          next[result.value.id] = result.value.mentors
        }
        return next
      })
    }

    loadMissingPendingMentors()

    return () => {
      cancelled = true
    }
  }, [sentEmails, mentors])

  async function reloadAll() {
    const [eList, pList, sList, mList] = await Promise.all([
      fetchScheduledEmails(),
      fetchPractices(),
      fetchSeasons(),
      fetchMentors(),
    ])
    setEmails(eList)
    setPractices(pList)
    setSeasons(sList)
    setMentors(mList)
    setPendingMentorsByEmailId({})
  }

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [eList, pList, sList, mList] = await Promise.all([
          fetchScheduledEmails(),
          fetchPractices(),
          fetchSeasons(),
          fetchMentors(),
        ])
        if (!cancelled) {
          setEmails(eList)
          setPractices(pList)
          setSeasons(sList)
          setMentors(mList)
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setEmails([])
          setPractices([])
          setSeasons([])
          setMentors([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  const resetModal = () => {
    setModal(null)
    setActiveEmail(null)
    setModalError('')
  }

  const closeModal = () => {
    if (busy) return
    resetModal()
  }

  const openCreate = () => {
    setModalError('')
    setActiveEmail(null)
    setForm(createEmptyEmailForm(sortedSeasons[0]?.id ?? ''))
    setModal('create')
  }

  const openEdit = (emailRow) => {
    setModalError('')
    setActiveEmail(emailRow)
    const mode =
      emailRow.recipient_mode === 'specific_mentors'
        ? 'specific_mentors'
        : 'all_in_season'
    const { sendDate, sendTime } = isoToSendDateAndTime(
      emailRow.scheduled_send_at
    )
    setForm({
      sendDate,
      sendTime,
      body_text: emailRow.body_text ?? '',
      practices: Array.isArray(emailRow.practices)
        ? emailRow.practices.map((id) => String(id))
        : [],
      recipient_mode: mode,
      recipient_season:
        emailRow.recipient_season != null
          ? String(emailRow.recipient_season)
          : '',
      specific_mentors: Array.isArray(emailRow.specific_mentors)
        ? emailRow.specific_mentors.map((id) => String(id))
        : [],
    })
    setModal('edit')
  }

  const openDelete = (emailRow) => {
    setModalError('')
    setActiveEmail(emailRow)
    setModal('delete')
  }

  const buildPayloadFromForm = () => {
    const scheduled_send_at = dateAndQuarterTimeToIso(
      form.sendDate,
      form.sendTime
    )
    if (!scheduled_send_at) {
      return { error: 'Schedule date and time are required (15-minute times).' }
    }
    const body_text = form.body_text.trim()
    if (!body_text) return { error: 'Email text is required.' }
    const practiceIds = form.practices
      .map((id) => Number.parseInt(String(id), 10))
      .filter((id) => !Number.isNaN(id))

    /** @type {{ recipient_mode: string, recipient_season: number|null, specific_mentors: number[] }} */
    let recipientsPayload
    if (form.recipient_mode === 'all_in_season') {
      const sid = Number.parseInt(String(form.recipient_season), 10)
      if (Number.isNaN(sid)) {
        return {
          error: 'Select a season when sending to all mentors in that season.',
        }
      }
      recipientsPayload = {
        recipient_mode: 'all_in_season',
        recipient_season: sid,
        specific_mentors: [],
      }
    } else {
      const mentorIds = form.specific_mentors
        .map((id) => Number.parseInt(String(id), 10))
        .filter((id) => !Number.isNaN(id))
      if (mentorIds.length === 0) {
        return { error: 'Select at least one mentor for specific-mentor sends.' }
      }
      recipientsPayload = {
        recipient_mode: 'specific_mentors',
        recipient_season: null,
        specific_mentors: mentorIds,
      }
    }

    return {
      payload: {
        scheduled_send_at,
        body_text,
        practices: practiceIds,
        ...recipientsPayload,
      },
    }
  }

  const handleCreateSubmit = async (e) => {
    e.preventDefault()
    setModalError('')
    const built = buildPayloadFromForm()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      await createScheduledEmail(built.payload)
      await reloadAll()
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleEditSubmit = async (e) => {
    e.preventDefault()
    setModalError('')
    if (!activeEmail) return
    const built = buildPayloadFromForm()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      await patchScheduledEmail(activeEmail.id, built.payload)
      await reloadAll()
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!activeEmail) return
    setModalError('')
    setBusy(true)
    try {
      await deleteScheduledEmail(activeEmail.id)
      await reloadAll()
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleSendNow = async (row) => {
    const count = scheduledRecipientCount(row, mentors)
    if (
      !window.confirm(
        `Send this email now to ${count} mentor${count === 1 ? '' : 's'}?\n` +
          `Scheduled: ${formatDateTime(row.scheduled_send_at)}`
      )
    ) {
      return
    }
    setLoadError(null)
    setSendingEmailId(row.id)
    try {
      const result = await sendScheduledEmailNow(row.id)
      await reloadAll()
      const sent = result.sent ?? result.recipients ?? count
      window.alert(
        sent === 1
          ? 'Email sent to 1 mentor.'
          : `Email sent to ${sent} mentors.`
      )
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setSendingEmailId(null)
    }
  }

  const handleMarkSent = async (row) => {
    if (
      !window.confirm(
        `Mark this email as sent?\nScheduled: ${formatDateTime(row.scheduled_send_at)}`
      )
    ) {
      return
    }
    setLoadError(null)
    try {
      await patchScheduledEmail(row.id, {
        task_completed_at: new Date().toISOString(),
      })
      await reloadAll()
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    }
  }

  const emailFormFields = (formId) => (
    <>
      <span className="field-label">Send date &amp; time</span>
      <div className="practice-datetime-row">
        <div>
          <label className="field-label" htmlFor={`${formId}-send-date`}>
            Date
          </label>
          <input
            id={`${formId}-send-date`}
            type="date"
            className="field-input"
            value={form.sendDate}
            onChange={(e) =>
              setForm((f) => ({ ...f, sendDate: e.target.value }))
            }
            required
          />
        </div>
        <div>
          <label className="field-label" htmlFor={`${formId}-send-time`}>
            Time <span className="muted">(15 min)</span>
          </label>
          <select
            id={`${formId}-send-time`}
            className="field-input field-select"
            value={form.sendTime}
            onChange={(e) =>
              setForm((f) => ({ ...f, sendTime: e.target.value }))
            }
            required
          >
            {quarterTimeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="recipient-fieldset">
        <legend className="field-label">Recipients</legend>
        <label className="radio-row">
          <input
            type="radio"
            name={`${formId}-recipient`}
            checked={form.recipient_mode === 'all_in_season'}
            onChange={() =>
              setForm((f) => ({ ...f, recipient_mode: 'all_in_season' }))
            }
          />
          All mentors in a season
        </label>
        <label className="radio-row">
          <input
            type="radio"
            name={`${formId}-recipient`}
            checked={form.recipient_mode === 'specific_mentors'}
            onChange={() =>
              setForm((f) => ({ ...f, recipient_mode: 'specific_mentors' }))
            }
          />
          Specific mentors only
        </label>
      </fieldset>

      {form.recipient_mode === 'all_in_season' ? (
        <>
          <label className="field-label" htmlFor={`${formId}-recipient-season`}>
            Season (all mentors linked to this season)
          </label>
          <select
            id={`${formId}-recipient-season`}
            className="field-input field-select"
            value={form.recipient_season}
            onChange={(e) =>
              setForm((f) => ({ ...f, recipient_season: e.target.value }))
            }
            required
          >
            <option value="">Select season…</option>
            {sortedSeasons.map((s) => {
              const n = mentors.filter(
                (m) => Array.isArray(m.seasons) && m.seasons.includes(s.id)
              ).length
              return (
                <option key={s.id} value={String(s.id)}>
                  {s.year}
                  {` (${n} mentor${n === 1 ? '' : 's'})`}
                </option>
              )
            })}
          </select>
        </>
      ) : (
        <>
          <label className="field-label" htmlFor={`${formId}-mentors`}>
            Mentors to email
          </label>
          <select
            id={`${formId}-mentors`}
            className="field-input field-select email-mentor-multiselect"
            value={form.specific_mentors}
            onChange={(e) => {
              setForm((f) => ({
                ...f,
                specific_mentors: Array.from(e.target.selectedOptions).map(
                  (o) => o.value
                ),
              }))
            }}
            multiple
            size={Math.min(Math.max(mentorsSorted.length, 4), 12)}
          >
            {mentorsSorted.map((m) => (
              <option key={m.id} value={String(m.id)}>
                {m.last_name}, {m.first_name} · {m.email} · {m.type}
              </option>
            ))}
          </select>
          <p className="muted">
            Hold Ctrl (Windows) or ⌘ (Mac) to select multiple mentors.
          </p>
        </>
      )}

      <label className="field-label" htmlFor={`${formId}-practices`}>
        Practices in this email
      </label>
      <select
        id={`${formId}-practices`}
        className="field-input field-select"
        value={form.practices}
        onChange={(e) =>
          setForm((f) => ({
            ...f,
            practices: Array.from(e.target.selectedOptions).map((o) => o.value),
          }))
        }
        multiple
        size={Math.min(Math.max(practicesSorted.length, 4), 10)}
      >
        {practicesSorted.map((p) => (
          <option key={p.id} value={String(p.id)}>
            {practiceLabel(p)}
          </option>
        ))}
      </select>

      <label className="field-label" htmlFor={`${formId}-body`}>
        Email text (template)
      </label>
      <textarea
        id={`${formId}-body`}
        className="field-input field-textarea"
        rows={10}
        value={form.body_text}
        onChange={(e) =>
          setForm((f) => ({ ...f, body_text: e.target.value }))
        }
        spellCheck
      />
      <p className="muted">
        Per-mentor placeholders:{' '}
        <code>{'{{ first_name }}'}</code>,{' '}
        <code>{'{{ last_name }}'}</code>,{' '}
        <code>{'{{ year }}'}</code> (scheduled season),{' '}
        <code>{'{{ pace }}'}</code>,{' '}
        <code>{'{{ link }}'}</code> (unique reply URL).
      </p>
    </>
  )

  function recipientSummary(row) {
    return (
      <span className="muted">
        {recipientSummaryText(row, { seasonYearById, mentors })}
      </span>
    )
  }

  function practicesSummary(ids) {
    if (!Array.isArray(ids) || ids.length === 0) {
      return <span className="muted">No practices linked.</span>
    }
    return (
      <ul className="email-practice-inline-list">
        {ids.map((pid) => {
          const p = practices.find((x) => x.id === pid)
          const label = p ? practiceLabel(p) : `Practice #${pid}`
          return (
            <li key={pid}>
              <Link to={`/practices/${pid}`} className="nav-back">
                {label}
              </Link>
            </li>
          )
        })}
      </ul>
    )
  }

  function renderUpcomingEmailCard(row) {
    const sending = sendingEmailId === row.id
    return (
      <li key={row.id} className="practice-row email-row">
        <div className="practice-row-main">
          <span className="practice-date">
            Scheduled · {formatDateTime(row.scheduled_send_at)}
          </span>
          <div className="email-recipients-block">
            <span className="muted email-practices-label">Recipients</span>
            {recipientSummary(row)}
          </div>
          <div className="email-practices-block">
            <span className="muted email-practices-label">Practices</span>
            {practicesSummary(row.practices)}
          </div>
          <p className="email-body-preview muted">
            {(row.body_text || '').split('\n')[0]}
            {(row.body_text || '').includes('\n') ? ' …' : ''}
          </p>
        </div>
        <div className="practice-row-actions email-row-actions">
          <button
            type="button"
            className="btn btn-text"
            disabled={loading || sending || sendingEmailId != null}
            onClick={() => handleSendNow(row)}
          >
            {sending ? 'Sending…' : 'Send now'}
          </button>
          <button
            type="button"
            className="btn btn-text"
            disabled={loading || sending || sendingEmailId != null}
            onClick={() => handleMarkSent(row)}
          >
            Mark sent
          </button>
          <button
            type="button"
            className="btn btn-text"
            disabled={loading || sending || sendingEmailId != null}
            onClick={() => openEdit(row)}
          >
            Edit
          </button>
          <button
            type="button"
            className="btn btn-text btn-text-danger"
            disabled={loading || sending || sendingEmailId != null}
            onClick={() => openDelete(row)}
          >
            Delete
          </button>
        </div>
      </li>
    )
  }

  function renderSentEmailCard(row) {
    const replyStats = sentEmailReplyStats(row)
    const pendingMentorsFromRow = pendingMentorsForEmail(row, mentors)
    const pendingMentors =
      pendingMentorsFromRow.length > 0
        ? pendingMentorsFromRow
        : (pendingMentorsByEmailId[row.id] ?? [])
    return (
      <li key={row.id} className="practice-row email-row">
        <div className="practice-row-main">
          <span className="practice-date">
            Sent · {formatDateTime(row.task_completed_at)}
          </span>
          <span className="muted">
            Originally scheduled {formatDateTime(row.scheduled_send_at)}
          </span>
          <div className="email-recipients-block">
            <span className="muted email-practices-label">Recipients</span>
            {recipientSummary(row)}
          </div>
          {replyStats ? (
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
          {replyStats && replyStats.pending > 0 && pendingMentors.length > 0 ? (
            <p className="email-awaiting-mentors">
              <span className="email-awaiting-mentors-label">Awaiting:</span>{' '}
              {pendingMentors.map((m) => m.name).join(', ')}
            </p>
          ) : null}
        </div>
        <div className="practice-row-actions email-row-actions">
          <Link to={`/emails/${row.id}`} className="btn btn-text">
            View
          </Link>
          <button
            type="button"
            className="btn btn-text"
            disabled={loading}
            onClick={() => openEdit(row)}
          >
            Edit
          </button>
          <button
            type="button"
            className="btn btn-text btn-text-danger"
            disabled={loading}
            onClick={() => openDelete(row)}
          >
            Delete
          </button>
        </div>
      </li>
    )
  }

  function renderEmailCard(row, { allowMarkSent }) {
    if (allowMarkSent) {
      return renderUpcomingEmailCard(row)
    }
    return renderSentEmailCard(row)
  }

  return (
    <>
      <AppHeader />

      <main className="panel emails-panel">
        <div className="practices-toolbar">
          <h2>Emails</h2>
          <button
            type="button"
            className="btn-icon-plus"
            aria-label="Schedule email"
            title="Schedule email"
            disabled={loading}
            onClick={openCreate}
          >
            +
          </button>
        </div>

        <p className="muted">
          Upcoming messages can be sent manually with <strong>Send now</strong>, sent
          later on schedule, or marked complete with <strong>Mark sent</strong> if
          you sent them outside this app.
        </p>

        {loading && <p className="muted">Loading…</p>}
        {loadError && (
          <p className="error" role="alert">
            {loadError}
          </p>
        )}

        {!loading && !loadError && (
          <div className="emails-split">
            <section className="email-section" aria-labelledby="upcoming-heading">
              <h3 id="upcoming-heading">Upcoming</h3>
              {upcomingEmails.length === 0 ? (
                <p className="muted">No scheduled emails.</p>
              ) : (
                <ul className="practice-list">
                  {upcomingEmails.map((row) =>
                    renderEmailCard(row, { allowMarkSent: true })
                  )}
                </ul>
              )}
            </section>

            <section className="email-section" aria-labelledby="sent-heading">
              <h3 id="sent-heading">Sent / completed</h3>
              {sentEmails.length === 0 ? (
                <p className="muted">No completed sends yet.</p>
              ) : (
                <ul className="practice-list">
                  {sentEmails.map((row) =>
                    renderEmailCard(row, { allowMarkSent: false })
                  )}
                </ul>
              )}
            </section>
          </div>
        )}
      </main>

      <Modal
        open={modal === 'create'}
        title="Schedule email"
        panelClassName="modal-panel-wide"
        onClose={closeModal}
        closeDisabled={busy}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              form="email-create-form"
              type="submit"
              className="btn btn-primary"
              disabled={busy}
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form
          id="email-create-form"
          className="modal-form-stack"
          onSubmit={handleCreateSubmit}
        >
          {emailFormFields('ec')}
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'edit'}
        title="Edit scheduled email"
        panelClassName="modal-panel-wide"
        onClose={closeModal}
        closeDisabled={busy}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              form="email-edit-form"
              type="submit"
              className="btn btn-primary"
              disabled={busy}
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form
          id="email-edit-form"
          className="modal-form-stack"
          onSubmit={handleEditSubmit}
        >
          {activeEmail?.task_completed_at ? (
            <p className="muted">
              Completed at {formatDateTime(activeEmail.task_completed_at)} — you can
              still edit template and practices if needed.
            </p>
          ) : null}
          {emailFormFields('ee')}
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete scheduled email"
        onClose={closeModal}
        closeDisabled={busy}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={handleDeleteConfirm}
            >
              {busy ? 'Deleting…' : 'Delete'}
            </button>
          </>
        }
      >
        <p className="delete-prompt">
          Delete this scheduled email (
          {activeEmail ? formatDateTime(activeEmail.scheduled_send_at) : ''})?
        </p>
        {modalError ? (
          <p className="error modal-error" role="alert">
            {modalError}
          </p>
        ) : null}
      </Modal>
    </>
  )
}
