import { useEffect, useMemo, useState } from 'react'

import {
  createMentor,
  deleteMentor,
  fetchMentors,
  fetchSeasons,
  importMentorsCsv,
  patchMentor,
} from '../api'
import { AppHeader } from '../components/AppHeader.jsx'
import { Modal } from '../components/Modal.jsx'

const MENTOR_TYPES = ['At Practice', 'Remote']
const REMOTE_TYPE = 'Remote'
const PACE_TYPES = ['8-9', '9-10', '10-11', '11-12', '12-13', '13+']

function sortSeasonsByYearDesc(list) {
  return [...list].sort(
    (a, b) => Number(b.year) - Number(a.year) || b.id - a.id
  )
}

function sortMentors(list) {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    const fn = (a.first_name || '').localeCompare(b.first_name || '')
    if (fn !== 0) return fn
    return a.id - b.id
  })
}

function emptyMentorForm() {
  return {
    first_name: '',
    last_name: '',
    email: '',
    cell_phone: '',
    type: 'At Practice',
    pace: '8-9',
    split_practice: false,
    seasons: [],
  }
}

export default function MentorsPage() {
  const [mentors, setMentors] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [seasonFilter, setSeasonFilter] = useState('')
  const [emailFilter, setEmailFilter] = useState('')
  const [sortBy, setSortBy] = useState('last_name')

  const [modal, setModal] = useState(null)
  const [activeMentor, setActiveMentor] = useState(null)
  const [form, setForm] = useState(() => emptyMentorForm())
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)
  const [csvFile, setCsvFile] = useState(null)
  const [importMessage, setImportMessage] = useState('')
  const [importBusy, setImportBusy] = useState(false)

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

  const seasonYearById = useMemo(() => {
    const m = new Map()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  const filteredMentors = useMemo(() => {
    let next = mentors
    if (seasonFilter) {
      const seasonId = Number.parseInt(seasonFilter, 10)
      if (!Number.isNaN(seasonId)) {
        next = next.filter(
          (m) => Array.isArray(m.seasons) && m.seasons.includes(seasonId)
        )
      }
    }
    const emailNeedle = emailFilter.trim().toLowerCase()
    if (emailNeedle) {
      next = next.filter((m) =>
        String(m.email || '')
          .toLowerCase()
          .includes(emailNeedle)
      )
    }
    return [...next].sort((a, b) => {
      if (sortBy === 'email') {
        const cmp = String(a.email || '').localeCompare(String(b.email || ''))
        if (cmp !== 0) return cmp
      } else if (sortBy === 'season') {
        const seasonSortValue = (mentor) => {
          if (!Array.isArray(mentor.seasons) || mentor.seasons.length === 0) return Number.POSITIVE_INFINITY
          const years = mentor.seasons
            .map((id) => Number.parseInt(String(seasonYearById.get(id)), 10))
            .filter((y) => !Number.isNaN(y))
          if (years.length === 0) return Number.POSITIVE_INFINITY
          return Math.max(...years)
        }
        const aSeason = seasonSortValue(a)
        const bSeason = seasonSortValue(b)
        if (aSeason !== bSeason) return aSeason - bSeason
      }
      const ln = String(a.last_name || '').localeCompare(String(b.last_name || ''))
      if (ln !== 0) return ln
      const fn = String(a.first_name || '').localeCompare(String(b.first_name || ''))
      if (fn !== 0) return fn
      return a.id - b.id
    })
  }, [mentors, seasonFilter, emailFilter, sortBy, seasonYearById])

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [mList, sList] = await Promise.all([fetchMentors(), fetchSeasons()])
        if (!cancelled) {
          setMentors(sortMentors(mList))
          setSeasons(sortSeasonsByYearDesc(sList))
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setMentors([])
          setSeasons([])
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
    setActiveMentor(null)
    setModalError('')
  }

  const closeModal = () => {
    if (busy) return
    resetModal()
  }

  const openCreate = () => {
    setModalError('')
    setForm(emptyMentorForm())
    setActiveMentor(null)
    setModal('create')
  }

  const openImport = () => {
    setModalError('')
    setImportMessage('')
    setCsvFile(null)
    setModal('import')
  }

  const openEdit = (mentor) => {
    setModalError('')
    setActiveMentor(mentor)
    setForm({
      first_name: mentor.first_name ?? '',
      last_name: mentor.last_name ?? '',
      email: mentor.email ?? '',
      cell_phone: mentor.cell_phone ?? '',
      type: mentor.type ?? 'At Practice',
      pace:
        mentor.pace ??
        (mentor.type === REMOTE_TYPE ? '' : '8-9'),
      split_practice: Boolean(mentor.split_practice),
      seasons: Array.isArray(mentor.seasons)
        ? mentor.seasons.map((s) => String(s))
        : [],
    })
    setModal('edit')
  }

  const openDelete = (mentor) => {
    setModalError('')
    setActiveMentor(mentor)
    setModal('delete')
  }

  const buildPayload = () => {
    if (!form.first_name.trim()) return { error: 'First name is required.' }
    if (!form.last_name.trim()) return { error: 'Last name is required.' }
    if (!form.email.trim()) return { error: 'Email is required.' }
    const isRemote = form.type === REMOTE_TYPE
    if (!isRemote && !form.cell_phone.trim()) {
      return { error: 'Cell phone is required for At Practice mentors.' }
    }
    if (!isRemote && !form.pace) {
      return { error: 'Pace is required for At Practice mentors.' }
    }
    const seasons = form.seasons
      .map((s) => Number.parseInt(String(s), 10))
      .filter((s) => !Number.isNaN(s))
    return {
      payload: {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        cell_phone: form.cell_phone.trim(),
        type: form.type,
        pace: isRemote ? form.pace || '' : form.pace,
        split_practice: form.split_practice,
        seasons,
      },
    }
  }

  const handleCreateSubmit = async (e) => {
    e.preventDefault()
    setModalError('')
    const built = buildPayload()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      await createMentor(built.payload)
      const list = await fetchMentors()
      setMentors(sortMentors(list))
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
    if (!activeMentor) return
    const built = buildPayload()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      await patchMentor(activeMentor.id, built.payload)
      const list = await fetchMentors()
      setMentors(sortMentors(list))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!activeMentor) return
    setModalError('')
    setBusy(true)
    try {
      await deleteMentor(activeMentor.id)
      const list = await fetchMentors()
      setMentors(sortMentors(list))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleCsvUpload = async (e) => {
    e.preventDefault()
    if (!csvFile) return
    setImportBusy(true)
    setImportMessage('')
    setLoadError(null)
    try {
      const result = await importMentorsCsv(csvFile)
      const list = await fetchMentors()
      setMentors(sortMentors(list))
      setCsvFile(null)
      const errCount = Array.isArray(result.errors) ? result.errors.length : 0
      const seasonSummary = Object.entries(result.created_by_season || {})
        .sort((a, b) => Number(b[0]) - Number(a[0]))
        .map(([year, count]) => `${count} added to ${year}`)
        .join(', ')
      setImportMessage(
        `Upload complete. Created ${result.created ?? 0}, updated ${
          result.updated ?? 0
        }, skipped ${result.skipped ?? 0}${
          errCount ? `, errors ${errCount}` : ''
        }.${seasonSummary ? ` ${seasonSummary}.` : ''}`
      )
      if (errCount) setLoadError(result.errors.slice(0, 5).join(' | '))
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setImportBusy(false)
    }
  }

  const mentorFormFields = (formId) => (
    <>
      <label className="field-label" htmlFor={`${formId}-seasons`}>Seasons</label>
      <select
        id={`${formId}-seasons`}
        className="field-input field-select"
        value={form.seasons}
        onChange={(e) =>
          setForm((f) => ({
            ...f,
            seasons: Array.from(e.target.selectedOptions).map((o) => o.value),
          }))
        }
        multiple
        size={Math.min(Math.max(sortedSeasons.length, 3), 8)}
      >
        {sortedSeasons.map((s) => (
          <option key={s.id} value={String(s.id)}>{s.year}</option>
        ))}
      </select>

      <label className="field-label" htmlFor={`${formId}-first`}>First name</label>
      <input
        id={`${formId}-first`}
        type="text"
        className="field-input"
        value={form.first_name}
        onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
        maxLength={75}
        required
      />

      <label className="field-label" htmlFor={`${formId}-last`}>Last name</label>
      <input
        id={`${formId}-last`}
        type="text"
        className="field-input"
        value={form.last_name}
        onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
        maxLength={100}
        required
      />

      <label className="field-label" htmlFor={`${formId}-email`}>Email</label>
      <input
        id={`${formId}-email`}
        type="email"
        className="field-input"
        value={form.email}
        onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
        maxLength={100}
        required
      />

      <label className="field-label" htmlFor={`${formId}-cell`}>
        Cell phone{form.type === REMOTE_TYPE ? ' (optional)' : ''}
      </label>
      <input
        id={`${formId}-cell`}
        type="text"
        className="field-input"
        value={form.cell_phone}
        onChange={(e) => setForm((f) => ({ ...f, cell_phone: e.target.value }))}
        maxLength={20}
        required={form.type !== REMOTE_TYPE}
      />

      <label className="field-label" htmlFor={`${formId}-type`}>Type</label>
      <select
        id={`${formId}-type`}
        className="field-input field-select"
        value={form.type}
        onChange={(e) => {
          const nextType = e.target.value
          setForm((f) => ({
            ...f,
            type: nextType,
            pace:
              nextType === REMOTE_TYPE && f.type !== REMOTE_TYPE
                ? ''
                : f.pace || (nextType === REMOTE_TYPE ? '' : '8-9'),
          }))
        }}
        required
      >
        {MENTOR_TYPES.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>

      <label className="field-label" htmlFor={`${formId}-pace`}>
        Pace group{form.type === REMOTE_TYPE ? ' (optional)' : ''}
      </label>
      <select
        id={`${formId}-pace`}
        className="field-input field-select"
        value={form.pace}
        onChange={(e) => setForm((f) => ({ ...f, pace: e.target.value }))}
        required={form.type !== REMOTE_TYPE}
      >
        {form.type === REMOTE_TYPE ? (
          <option value="">None</option>
        ) : null}
        {PACE_TYPES.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>

      <label className="field-label checkbox-label">
        <input
          type="checkbox"
          checked={form.split_practice}
          onChange={(e) => setForm((f) => ({ ...f, split_practice: e.target.checked }))}
        />
        Split practice
      </label>
    </>
  )

  return (
    <>
      <AppHeader />

      <main className="panel mentors-panel">
        <div className="practices-toolbar">
          <h2>Mentors</h2>
          <div className="icon-btn-row">
            <button
              type="button"
              className="btn-icon-plus btn-icon-upload"
              aria-label="Import mentors CSV"
              title="Import mentors CSV"
              disabled={loading}
              onClick={openImport}
            >
              ↑
            </button>
            <button
              type="button"
              className="btn-icon-plus"
              aria-label="Add mentor"
              title="Add mentor"
              disabled={loading}
              onClick={openCreate}
            >
              +
            </button>
          </div>
        </div>

        <div className="practices-filter">
          <label className="field-label" htmlFor="mentor-season-filter">
            Filter by season
          </label>
          <select
            id="mentor-season-filter"
            className="field-input field-select"
            value={seasonFilter}
            onChange={(e) => setSeasonFilter(e.target.value)}
          >
            <option value="">All seasons</option>
            {sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>{s.year}</option>
            ))}
          </select>

          <label className="field-label" htmlFor="mentor-email-filter">
            Filter by email
          </label>
          <input
            id="mentor-email-filter"
            type="text"
            className="field-input"
            placeholder="Partial or full email"
            value={emailFilter}
            onChange={(e) => setEmailFilter(e.target.value)}
          />

          <label className="field-label" htmlFor="mentor-sort-by">
            Sort by
          </label>
          <select
            id="mentor-sort-by"
            className="field-input field-select"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="last_name">Last name</option>
            <option value="email">Email</option>
            <option value="season">Season</option>
          </select>
        </div>

        {loading && <p className="muted">Loading…</p>}
        {loadError && <p className="error" role="alert">{loadError}</p>}

        {!loading && !loadError && filteredMentors.length === 0 && (
          <p className="muted">
            {mentors.length === 0
              ? 'No mentors yet. Use + to add one.'
              : 'No mentors match this season filter.'}
          </p>
        )}

        {!loading && !loadError && filteredMentors.length > 0 && (
          <ul className="practice-list">
            {filteredMentors.map((m) => (
              <li key={m.id} className="practice-row">
                <div className="practice-row-main">
                  <span className="practice-date">{m.first_name} {m.last_name}</span>
                  <span className="practice-race muted">{m.email}</span>
                  <span className="muted">
                    {m.cell_phone} · {m.type}
                    {m.pace ? ` · Pace ${m.pace}` : ''}
                    {m.split_practice ? ' · Split practice' : ''} · Seasons{' '}
                    {Array.isArray(m.seasons) && m.seasons.length > 0
                      ? m.seasons.map((id) => seasonYearById.get(id) ?? id).join(', ')
                      : 'none'}
                  </span>
                </div>
                <div className="practice-row-actions">
                  <button type="button" className="btn btn-text" onClick={() => openEdit(m)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-text btn-text-danger"
                    onClick={() => openDelete(m)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>

      <Modal
        open={modal === 'import'}
        title="Import mentors CSV"
        onClose={closeModal}
        closeDisabled={importBusy}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={importBusy}
              onClick={closeModal}
            >
              Cancel
            </button>
            <button
              form="mentor-import-form"
              type="submit"
              className="btn btn-primary"
              disabled={!csvFile || importBusy}
            >
              {importBusy ? 'Uploading…' : 'Upload'}
            </button>
          </>
        }
      >
        <form id="mentor-import-form" className="modal-form-stack" onSubmit={handleCsvUpload}>
          <label className="field-label" htmlFor="mentor-csv-upload">
            Select CSV file
          </label>
          <input
            id="mentor-csv-upload"
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
          />
          <p className="muted">
            CSV format example columns:
            <code> email</code>, <code>season_year</code> (or <code>season</code>/<code>year</code>),
            <code> first_name</code>, <code>last_name</code>, <code>cell_phone</code> (or <code>cell</code>;
            required for At Practice; optional for Remote),
            <code> type</code>, <code>pace</code> (required for At Practice; optional
            for Remote), <code>split_practice</code>.
          </p>
          {importMessage ? (
            <p className="muted" role="status">
              {importMessage}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'create'}
        title="Add mentor"
        onClose={closeModal}
        closeDisabled={busy}
        footer={
          <>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={closeModal}>
              Cancel
            </button>
            <button form="mentor-create-form" type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form id="mentor-create-form" className="modal-form-stack" onSubmit={handleCreateSubmit}>
          {mentorFormFields('mc')}
          {modalError ? <p className="error modal-error" role="alert">{modalError}</p> : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'edit'}
        title="Edit mentor"
        onClose={closeModal}
        closeDisabled={busy}
        footer={
          <>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={closeModal}>
              Cancel
            </button>
            <button form="mentor-edit-form" type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form id="mentor-edit-form" className="modal-form-stack" onSubmit={handleEditSubmit}>
          {mentorFormFields('me')}
          {modalError ? <p className="error modal-error" role="alert">{modalError}</p> : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete mentor"
        onClose={closeModal}
        closeDisabled={busy}
        footer={
          <>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={closeModal}>
              Cancel
            </button>
            <button type="button" className="btn btn-danger" disabled={busy} onClick={handleDeleteConfirm}>
              {busy ? 'Deleting…' : 'Delete'}
            </button>
          </>
        }
      >
        <p className="delete-prompt">
          Delete mentor <strong>{activeMentor?.first_name} {activeMentor?.last_name}</strong>?
        </p>
        {modalError ? <p className="error modal-error" role="alert">{modalError}</p> : null}
      </Modal>
    </>
  )
}

