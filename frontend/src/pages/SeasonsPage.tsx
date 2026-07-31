import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'

import {
  createSeason,
  deleteSeason,
  fetchCoaches,
  fetchSeasons,
  patchSeason,
  setCurrentSeason,
} from '../api'
import { AppHeader } from '../components/AppHeader.jsx'
import { Modal } from '../components/Modal.jsx'
import { sortSeasonsByYearDesc } from '../seasonHelpers.js'
import type { Coach, Season } from '../types.js'

type SeasonModal = 'create' | 'edit' | 'delete'

function sortSeasons(list: Season[]): Season[] {
  return sortSeasonsByYearDesc(list)
}

function sortCoaches(list: Coach[]): Coach[] {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    return (a.first_name || '').localeCompare(b.first_name || '')
  })
}

function coachLabel(coach: Coach): string {
  return `${coach.first_name ?? ''} ${coach.last_name ?? ''}`.trim()
}

export default function SeasonsPage() {
  const [seasons, setSeasons] = useState<Season[]>([])
  const [coaches, setCoaches] = useState<Coach[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [modal, setModal] = useState<SeasonModal | null>(null)
  const [activeSeason, setActiveSeason] = useState<Season | null>(null)
  const [formYear, setFormYear] = useState('')
  const [formHeadCoachId, setFormHeadCoachId] = useState('')
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)

  const coachById = useMemo(() => {
    const map = new Map<number, Coach>()
    for (const coach of coaches) map.set(coach.id, coach)
    return map
  }, [coaches])

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [seasonList, coachList] = await Promise.all([
          fetchSeasons(),
          fetchCoaches(),
        ])
        if (!cancelled) {
          setSeasons(sortSeasons(seasonList))
          setCoaches(sortCoaches(coachList))
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setSeasons([])
          setCoaches([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  function coachesForSeason(seasonId: number | null | undefined): Coach[] {
    if (!seasonId) return []
    return coaches.filter(
      (coach) =>
        Array.isArray(coach.seasons) && coach.seasons.includes(seasonId)
    )
  }

  function headCoachLabel(season: Season): string | null {
    if (!season.head_coach) return null
    const coach = coachById.get(season.head_coach)
    return coach ? coachLabel(coach) : `Coach #${season.head_coach}`
  }

  const openCreate = () => {
    setModalError('')
    setFormYear('')
    setFormHeadCoachId('')
    setActiveSeason(null)
    setModal('create')
  }

  const openEdit = (season: Season) => {
    setModalError('')
    setFormYear(String(season.year))
    setFormHeadCoachId(
      season.head_coach != null ? String(season.head_coach) : ''
    )
    setActiveSeason(season)
    setModal('edit')
  }

  const openDelete = (season: Season) => {
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

  const buildSeasonPayload = (year: number) => {
    const headCoachId = Number.parseInt(formHeadCoachId, 10)
    return {
      year,
      head_coach: Number.isNaN(headCoachId) ? null : headCoachId,
    }
  }

  const handleCreateSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setModalError('')
    const year = Number.parseInt(String(formYear), 10)
    if (Number.isNaN(year)) {
      setModalError('Year must be a number.')
      return
    }
    setBusy(true)
    try {
      const created = (await createSeason({ year })) as Season
      setSeasons((prev) => sortSeasons([...prev, created]))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleEditSubmit = async (e: FormEvent<HTMLFormElement>) => {
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
      const updated = (await patchSeason(
        activeSeason.id,
        buildSeasonPayload(year)
      )) as Season
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

  const handleSetCurrent = async (season: Season) => {
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

  const editSeasonCoaches = activeSeason
    ? coachesForSeason(activeSeason.id)
    : []

  function seasonFormFields(formId: string): ReactNode {
    return (
      <>
        <label className="field-label" htmlFor={`${formId}-year`}>
          Year
        </label>
        <input
          id={`${formId}-year`}
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

        {modal === 'edit' ? (
          <>
            <label className="field-label" htmlFor={`${formId}-head-coach`}>
              Head coach
            </label>
            <select
              id={`${formId}-head-coach`}
              className="field-input field-select"
              value={formHeadCoachId}
              onChange={(e) => setFormHeadCoachId(e.target.value)}
            >
              <option value="">None</option>
              {editSeasonCoaches.map((coach) => (
                <option key={coach.id} value={String(coach.id)}>
                  {coachLabel(coach)}
                </option>
              ))}
            </select>
            {editSeasonCoaches.length === 0 ? (
              <p className="muted">
                Assign coaches to this season first, then choose a head coach.
              </p>
            ) : null}
          </>
        ) : null}
      </>
    )
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
            {seasons.map((s) => {
              const headCoach = headCoachLabel(s)
              return (
                <li key={s.id}>
                  <div className="season-row-main">
                    <span className="season-label">Year</span>
                    <span className="year">{s.year}</span>
                    {s.is_current ? (
                      <span className="season-current-badge">Current season</span>
                    ) : null}
                    {headCoach ? (
                      <span className="muted">Head coach: {headCoach}</span>
                    ) : (
                      <span className="muted">No head coach</span>
                    )}
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
              )
            })}
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
          {seasonFormFields('create')}
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
          {seasonFormFields('edit')}
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
