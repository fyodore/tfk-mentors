import { useEffect, useMemo, useState } from 'react'

import {
  createCoach,
  deleteCoach,
  fetchCoaches,
  fetchSeasons,
  importCoachesCsv,
  patchCoach,
} from '../api'
import { AppHeader } from '../components/AppHeader.jsx'
import { Modal } from '../components/Modal.jsx'
import {
  currentSeasonFromList,
  sortSeasonsByYearDesc,
} from '../seasonHelpers.js'

function sortCoaches(list) {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    const fn = (a.first_name || '').localeCompare(b.first_name || '')
    if (fn !== 0) return fn
    return a.id - b.id
  })
}

function emptyCoachForm() {
  return {
    first_name: '',
    last_name: '',
    email: '',
    cell: '',
    seasons: [],
  }
}

export default function CoachesPage() {
  const [coaches, setCoaches] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [seasonFilter, setSeasonFilter] = useState('')
  const [emailFilter, setEmailFilter] = useState('')
  const [sortBy, setSortBy] = useState('last_name')

  const [modal, setModal] = useState(null)
  const [activeCoach, setActiveCoach] = useState(null)
  const [form, setForm] = useState(() => emptyCoachForm())
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

  const filteredCoaches = useMemo(() => {
    let next = coaches
    if (seasonFilter) {
      const seasonId = Number.parseInt(seasonFilter, 10)
      if (!Number.isNaN(seasonId)) {
        next = next.filter(
          (c) => Array.isArray(c.seasons) && c.seasons.includes(seasonId)
        )
      }
    }
    const emailNeedle = emailFilter.trim().toLowerCase()
    if (emailNeedle) {
      next = next.filter((c) =>
        String(c.email || '')
          .toLowerCase()
          .includes(emailNeedle)
      )
    }
    return [...next].sort((a, b) => {
      if (sortBy === 'email') {
        const cmp = String(a.email || '').localeCompare(String(b.email || ''))
        if (cmp !== 0) return cmp
      } else if (sortBy === 'season') {
        const seasonSortValue = (coach) => {
          if (!Array.isArray(coach.seasons) || coach.seasons.length === 0) return Number.POSITIVE_INFINITY
          const years = coach.seasons
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
  }, [coaches, seasonFilter, emailFilter, sortBy, seasonYearById])

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [cList, sList] = await Promise.all([
          fetchCoaches(),
          fetchSeasons(),
        ])
        if (!cancelled) {
          setCoaches(sortCoaches(cList))
          const orderedSeasons = sortSeasonsByYearDesc(sList)
          setSeasons(orderedSeasons)
          const current = currentSeasonFromList(orderedSeasons)
          if (current) {
            setSeasonFilter(String(current.id))
          }
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setCoaches([])
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
    setActiveCoach(null)
    setModalError('')
  }

  const closeModal = () => {
    if (busy) return
    resetModal()
  }

  const openCreate = () => {
    setModalError('')
    setForm(emptyCoachForm())
    setActiveCoach(null)
    setModal('create')
  }

  const openImport = () => {
    setModalError('')
    setImportMessage('')
    setCsvFile(null)
    setModal('import')
  }

  const openEdit = (coach) => {
    setModalError('')
    setActiveCoach(coach)
    setForm({
      first_name: coach.first_name ?? '',
      last_name: coach.last_name ?? '',
      email: coach.email ?? '',
      cell: coach.cell ?? '',
      seasons: Array.isArray(coach.seasons)
        ? coach.seasons.map((s) => String(s))
        : [],
    })
    setModal('edit')
  }

  const openDelete = (coach) => {
    setModalError('')
    setActiveCoach(coach)
    setModal('delete')
  }

  const buildPayload = () => {
    if (!form.first_name.trim()) return { error: 'First name is required.' }
    if (!form.last_name.trim()) return { error: 'Last name is required.' }
    if (!form.email.trim()) return { error: 'Email is required.' }
    const seasons = form.seasons
      .map((s) => Number.parseInt(String(s), 10))
      .filter((s) => !Number.isNaN(s))
    return {
      payload: {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        cell: form.cell.trim(),
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
      await createCoach(built.payload)
      const list = await fetchCoaches()
      setCoaches(sortCoaches(list))
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
    if (!activeCoach) return
    const built = buildPayload()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      await patchCoach(activeCoach.id, built.payload)
      const list = await fetchCoaches()
      setCoaches(sortCoaches(list))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!activeCoach) return
    setModalError('')
    setBusy(true)
    try {
      await deleteCoach(activeCoach.id)
      const list = await fetchCoaches()
      setCoaches(sortCoaches(list))
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
      const result = await importCoachesCsv(csvFile)
      const list = await fetchCoaches()
      setCoaches(sortCoaches(list))
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
      if (errCount) {
        setLoadError(result.errors.slice(0, 5).join(' | '))
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setImportBusy(false)
    }
  }

  const coachFormFields = (formId) => (
    <>
      <label className="field-label" htmlFor={`${formId}-seasons`}>
        Seasons
      </label>
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
          <option key={s.id} value={String(s.id)}>
            {s.year}
          </option>
        ))}
      </select>

      <label className="field-label" htmlFor={`${formId}-first`}>
        First name
      </label>
      <input
        id={`${formId}-first`}
        type="text"
        className="field-input"
        value={form.first_name}
        onChange={(e) =>
          setForm((f) => ({ ...f, first_name: e.target.value }))
        }
        maxLength={75}
        required
      />

      <label className="field-label" htmlFor={`${formId}-last`}>
        Last name
      </label>
      <input
        id={`${formId}-last`}
        type="text"
        className="field-input"
        value={form.last_name}
        onChange={(e) =>
          setForm((f) => ({ ...f, last_name: e.target.value }))
        }
        maxLength={100}
        required
      />

      <label className="field-label" htmlFor={`${formId}-email`}>
        Email
      </label>
      <input
        id={`${formId}-email`}
        type="email"
        className="field-input"
        value={form.email}
        onChange={(e) =>
          setForm((f) => ({ ...f, email: e.target.value }))
        }
        maxLength={100}
        required
      />

      <label className="field-label" htmlFor={`${formId}-cell`}>
        Cell <span className="muted">(optional)</span>
      </label>
      <input
        id={`${formId}-cell`}
        type="text"
        className="field-input"
        value={form.cell}
        onChange={(e) =>
          setForm((f) => ({ ...f, cell: e.target.value }))
        }
        maxLength={20}
      />
    </>
  )

  return (
    <>
      <AppHeader />

      <main className="panel coaches-panel">
        <div className="practices-toolbar">
          <h2>Coaches</h2>
          <div className="icon-btn-row">
            <button
              type="button"
              className="btn-icon-plus btn-icon-upload"
              aria-label="Import coaches CSV"
              title="Import coaches CSV"
              disabled={loading}
              onClick={openImport}
            >
              ↑
            </button>
            <button
              type="button"
              className="btn-icon-plus"
              aria-label="Add coach"
              title="Add coach"
              disabled={loading}
              onClick={openCreate}
            >
              +
            </button>
          </div>
        </div>

        <div className="practices-filter">
          <label className="field-label" htmlFor="coach-season-filter">
            Filter by season
          </label>
          <select
            id="coach-season-filter"
            className="field-input field-select"
            value={seasonFilter}
            onChange={(e) => setSeasonFilter(e.target.value)}
          >
            <option value="">All seasons</option>
            {sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.year}
                {s.is_current ? ' (current)' : ''}
              </option>
            ))}
          </select>

          <label className="field-label" htmlFor="coach-email-filter">
            Filter by email
          </label>
          <input
            id="coach-email-filter"
            type="text"
            className="field-input"
            placeholder="Partial or full email"
            value={emailFilter}
            onChange={(e) => setEmailFilter(e.target.value)}
          />

          <label className="field-label" htmlFor="coach-sort-by">
            Sort by
          </label>
          <select
            id="coach-sort-by"
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
        {loadError && (
          <p className="error" role="alert">
            {loadError}
          </p>
        )}

        {!loading && !loadError && filteredCoaches.length === 0 && (
          <p className="muted">
            {coaches.length === 0
              ? 'No coaches yet. Use + to add one.'
              : 'No coaches match this season filter.'}
          </p>
        )}

        {!loading && !loadError && filteredCoaches.length > 0 && (
          <ul className="practice-list">
            {filteredCoaches.map((c) => (
              <li key={c.id} className="practice-row">
                <div className="practice-row-main">
                  <span className="practice-date">
                    {c.first_name} {c.last_name}
                  </span>
                  <span className="practice-race muted">{c.email}</span>
                  <span className="muted">
                    {c.cell ? `${c.cell} · ` : ''}
                    Seasons{' '}
                    {Array.isArray(c.seasons) && c.seasons.length > 0
                      ? c.seasons
                          .map((id) => seasonYearById.get(id) ?? id)
                          .join(', ')
                      : 'none'}
                  </span>
                </div>
                <div className="practice-row-actions">
                  <button
                    type="button"
                    className="btn btn-text"
                    onClick={() => openEdit(c)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-text btn-text-danger"
                    onClick={() => openDelete(c)}
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
        title="Import coaches CSV"
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
              form="coach-import-form"
              type="submit"
              className="btn btn-primary"
              disabled={!csvFile || importBusy}
            >
              {importBusy ? 'Uploading…' : 'Upload'}
            </button>
          </>
        }
      >
        <form id="coach-import-form" className="modal-form-stack" onSubmit={handleCsvUpload}>
          <label className="field-label" htmlFor="coach-csv-upload">
            Select CSV file
          </label>
          <input
            id="coach-csv-upload"
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
          />
          <p className="muted">
            CSV format: <code>email</code>, <code>season_year</code> (or
            <code> season</code>/<code>year</code>), optional
            <code> first_name</code>, <code>last_name</code>, <code>cell</code>.
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
        title="Add coach"
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
              form="coach-create-form"
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
          id="coach-create-form"
          className="modal-form-stack"
          onSubmit={handleCreateSubmit}
        >
          {coachFormFields('cc')}
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'edit'}
        title="Edit coach"
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
              form="coach-edit-form"
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
          id="coach-edit-form"
          className="modal-form-stack"
          onSubmit={handleEditSubmit}
        >
          {coachFormFields('ce')}
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete coach"
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
          Delete coach{' '}
          <strong>
            {activeCoach?.first_name} {activeCoach?.last_name}
          </strong>
          ?
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
