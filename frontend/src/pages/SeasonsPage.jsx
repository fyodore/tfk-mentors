import { useEffect, useState } from 'react'

import { createSeason, deleteSeason, fetchSeasons, patchSeason, setCurrentSeason } from '../api'
import { AppHeader } from '../components/AppHeader.jsx'
import { Modal } from '../components/Modal.jsx'
import { sortSeasonsByYearDesc } from '../seasonHelpers.js'

function sortSeasons(list) {
  return sortSeasonsByYearDesc(list)
}

export default function SeasonsPage() {
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [modal, setModal] = useState(null)
  const [activeSeason, setActiveSeason] = useState(null)
  const [formYear, setFormYear] = useState('')
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const list = await fetchSeasons()
        if (!cancelled) setSeasons(sortSeasons(list))
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
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

  const openCreate = () => {
    setModalError('')
    setFormYear('')
    setActiveSeason(null)
    setModal('create')
  }

  const openEdit = (season) => {
    setModalError('')
    setFormYear(String(season.year))
    setActiveSeason(season)
    setModal('edit')
  }

  const openDelete = (season) => {
    setModalError('')
    setActiveSeason(season)
    setModal('delete')
  }

  const resetModal = () => {
    setModal(null)
    setActiveSeason(null)
    setModalError('')
  }

  const closeModal = () => {
    if (busy) return
    resetModal()
  }

  const handleCreateSubmit = async (e) => {
    e.preventDefault()
    setModalError('')
    const year = Number.parseInt(String(formYear), 10)
    if (Number.isNaN(year)) {
      setModalError('Year must be a number.')
      return
    }
    setBusy(true)
    try {
      const created = await createSeason(year)
      setSeasons((prev) => sortSeasons([...prev, created]))
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
    if (!activeSeason) return
    const year = Number.parseInt(String(formYear), 10)
    if (Number.isNaN(year)) {
      setModalError('Year must be a number.')
      return
    }
    setBusy(true)
    try {
      const updated = await patchSeason(activeSeason.id, year)
      setSeasons((prev) =>
        sortSeasons([...prev.filter((s) => s.id !== activeSeason.id), updated])
      )
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!activeSeason) return
    setModalError('')
    setBusy(true)
    try {
      await deleteSeason(activeSeason.id)
      setSeasons((prev) => prev.filter((s) => s.id !== activeSeason.id))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleSetCurrent = async (season) => {
    if (season.is_current) return
    setLoadError(null)
    setBusy(true)
    try {
      await setCurrentSeason(season.id)
      const list = await fetchSeasons()
      setSeasons(sortSeasons(list))
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <AppHeader />

      <main className="panel seasons-panel">
        <div className="seasons-toolbar">
          <h2>Seasons</h2>
          <button
            type="button"
            className="btn-icon-plus"
            aria-label="Create season"
            title="Create season"
            disabled={loading}
            onClick={openCreate}
          >
            +
          </button>
        </div>

        {loading && <p className="muted">Loading…</p>}
        {loadError && (
          <p className="error" role="alert">
            Could not load seasons: {loadError}
          </p>
        )}

        {!loading && !loadError && seasons.length === 0 && (
          <p className="muted">No seasons yet. Create one to get started.</p>
        )}

        {!loading && !loadError && seasons.length > 0 && (
          <ul className="season-list">
            {seasons.map((s) => (
              <li key={s.id}>
                <div className="season-row-main">
                  <span className="season-label">Year</span>
                  <span className="year">{s.year}</span>
                  {s.is_current ? (
                    <span className="season-current-badge">Current season</span>
                  ) : null}
                </div>
                <div className="season-row-actions">
                  {!s.is_current ? (
                    <button
                      type="button"
                      className="btn btn-text"
                      disabled={busy}
                      onClick={() => handleSetCurrent(s)}
                    >
                      Set as current
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn-text"
                    disabled={busy}
                    onClick={() => openEdit(s)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-text btn-text-danger"
                    disabled={busy}
                    onClick={() => openDelete(s)}
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
        open={modal === 'create'}
        title="Create season"
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
              form="season-create-form"
              type="submit"
              className="btn btn-primary"
              disabled={busy}
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form id="season-create-form" onSubmit={handleCreateSubmit}>
          <label className="field-label" htmlFor="create-year">
            Year
          </label>
          <input
            id="create-year"
            name="year"
            type="number"
            className="field-input"
            value={formYear}
            onChange={(e) => setFormYear(e.target.value)}
            min={1900}
            max={2100}
            step={1}
            required
            autoFocus
          />
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'edit'}
        title="Edit season"
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
              form="season-edit-form"
              type="submit"
              className="btn btn-primary"
              disabled={busy}
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form id="season-edit-form" onSubmit={handleEditSubmit}>
          <label className="field-label" htmlFor="edit-year">
            Year
          </label>
          <input
            id="edit-year"
            name="year"
            type="number"
            className="field-input"
            value={formYear}
            onChange={(e) => setFormYear(e.target.value)}
            min={1900}
            max={2100}
            step={1}
            required
            autoFocus
          />
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete season"
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
          Delete season <strong>{activeSeason?.year}</strong>? This cannot be
          undone.
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
