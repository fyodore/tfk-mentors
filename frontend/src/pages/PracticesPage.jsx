import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  createPractice,
  deletePractice,
  fetchPractices,
  fetchSeasons,
  patchPractice,
} from '../api'
import { Modal } from '../components/Modal.jsx'
import {
  buildQuarterTimeOptions,
  dateAndQuarterTimeToIso,
  formatDateTime,
  isoToDateAndQuarterTime,
} from '../datetime.js'

function sortSeasonsByYearDesc(list) {
  return [...list].sort(
    (a, b) => Number(b.year) - Number(a.year) || b.id - a.id
  )
}

function sortPracticesByDateDesc(list) {
  return [...list].sort((a, b) => {
    const ta = new Date(a.date).getTime()
    const tb = new Date(b.date).getTime()
    return (Number.isNaN(tb) ? 0 : tb) - (Number.isNaN(ta) ? 0 : ta) || b.id - a.id
  })
}

const pad2 = (n) => String(n).padStart(2, '0')

function isoToPracticeDateAndTime(iso) {
  const { date, time } = isoToDateAndQuarterTime(iso)
  return { practiceDate: date, practiceTime: time }
}

function emptyPracticeForm(defaultSeasonId) {
  return {
    practiceDate: '',
    practiceTime: '09:00',
    nyrr_race: '',
    full_practice: true,
    season: defaultSeasonId === '' ? '' : String(defaultSeasonId),
  }
}

export default function PracticesPage() {
  const [practices, setPractices] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [seasonFilter, setSeasonFilter] = useState('')

  const [modal, setModal] = useState(null)
  const [activePractice, setActivePractice] = useState(null)
  const [form, setForm] = useState(() => emptyPracticeForm(''))
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

  const defaultSeasonId = sortedSeasons[0]?.id ?? ''

  const quarterTimeOptions = useMemo(() => buildQuarterTimeOptions(), [])

  const seasonYearById = useMemo(() => {
    const m = new Map()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [pList, sList] = await Promise.all([
          fetchPractices(),
          fetchSeasons(),
        ])
        if (!cancelled) {
          setPractices(sortPracticesByDateDesc(pList))
          setSeasons(sortSeasonsByYearDesc(sList))
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setPractices([])
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

  const filteredPractices = useMemo(() => {
    if (!seasonFilter) return practices
    const id = Number.parseInt(seasonFilter, 10)
    return practices.filter((p) => p.season === id)
  }, [practices, seasonFilter])

  const resetModal = () => {
    setModal(null)
    setActivePractice(null)
    setModalError('')
  }

  const closeModal = () => {
    if (busy) return
    resetModal()
  }

  const openCreate = () => {
    setModalError('')
    setForm(emptyPracticeForm(defaultSeasonId))
    setActivePractice(null)
    setModal('create')
  }

  const openEdit = (practice) => {
    setModalError('')
    setActivePractice(practice)
    const { practiceDate, practiceTime } = isoToPracticeDateAndTime(
      practice.date
    )
    setForm({
      practiceDate,
      practiceTime,
      nyrr_race: practice.nyrr_race ?? '',
      full_practice: Boolean(practice.full_practice),
      season: String(practice.season ?? ''),
    })
    setModal('edit')
  }

  const openDelete = (practice) => {
    setModalError('')
    setActivePractice(practice)
    setModal('delete')
  }

  const buildPayload = () => {
    const iso = dateAndQuarterTimeToIso(form.practiceDate, form.practiceTime)
    if (!iso) return { error: 'Please set a valid date and time.' }
    const seasonId = Number.parseInt(form.season, 10)
    if (Number.isNaN(seasonId)) return { error: 'Please select a season.' }
    return {
      payload: {
        date: iso,
        nyrr_race: form.nyrr_race.trim(),
        full_practice: form.full_practice,
        season: seasonId,
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
      const created = await createPractice(built.payload)
      setPractices((prev) => sortPracticesByDateDesc([...prev, created]))
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
    if (!activePractice) return
    const built = buildPayload()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      const updated = await patchPractice(activePractice.id, built.payload)
      setPractices((prev) =>
        sortPracticesByDateDesc([
          ...prev.filter((p) => p.id !== activePractice.id),
          updated,
        ])
      )
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!activePractice) return
    setModalError('')
    setBusy(true)
    try {
      await deletePractice(activePractice.id)
      setPractices((prev) => prev.filter((p) => p.id !== activePractice.id))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1>TFK Mentors</h1>
        <p className="tagline">
          <Link to="/" className="nav-back">
            Home
          </Link>
          <span aria-hidden> · </span>
          <Link to="/mentors" className="nav-back">
            Mentors
          </Link>
          <span aria-hidden> · </span>
          <Link to="/seasons" className="nav-back">
            Seasons
          </Link>
          <span aria-hidden> · </span>
          <Link to="/coaches" className="nav-back">
            Coaches
          </Link>
          <span aria-hidden> · </span>
          <Link to="/emails" className="nav-back">
            Emails
          </Link>
          <span aria-hidden> · </span>
          Practices
        </p>
      </header>

      <main className="panel practices-panel">
        <div className="practices-toolbar">
          <h2>Practices</h2>
          <button
            type="button"
            className="btn-icon-plus"
            aria-label="Add practice"
            title="Add practice"
            disabled={loading}
            onClick={openCreate}
          >
            +
          </button>
        </div>

        <div className="practices-filter">
          <label className="field-label" htmlFor="season-filter">
            Filter by season
          </label>
          <select
            id="season-filter"
            className="field-input field-select"
            value={seasonFilter}
            onChange={(e) => setSeasonFilter(e.target.value)}
          >
            <option value="">All seasons</option>
            {sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.year}
              </option>
            ))}
          </select>
        </div>

        {loading && <p className="muted">Loading…</p>}
        {loadError && (
          <p className="error" role="alert">
            {loadError}
          </p>
        )}

        {!loading && !loadError && filteredPractices.length === 0 && (
          <p className="muted">
            {practices.length === 0
              ? 'No practices yet. Use + to add one.'
              : 'No practices match this season filter.'}
          </p>
        )}

        {!loading && !loadError && filteredPractices.length > 0 && (
          <ul className="practice-list">
            {filteredPractices.map((p) => (
              <li key={p.id} className="practice-row">
                <div className="practice-row-main">
                  <span className="practice-date">
                    {p.date
                      ? formatDateTime(p.date)
                      : '—'}
                  </span>
                  <span className="practice-race">
                    {p.nyrr_race?.trim()
                      ? p.nyrr_race
                      : <span className="muted">No race name</span>}
                  </span>
                  <span className="muted">
                    Season {seasonYearById.get(p.season) ?? p.season}
                    {p.full_practice ? ' · Full practice' : ' · Partial'}
                  </span>
                </div>
                <div className="practice-row-actions">
                  <Link
                    className="btn btn-text"
                    to={`/practices/${p.id}`}
                  >
                    View
                  </Link>
                  <button
                    type="button"
                    className="btn btn-text"
                    onClick={() => openEdit(p)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-text btn-text-danger"
                    onClick={() => openDelete(p)}
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
        title="Add practice"
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
              form="practice-create-form"
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
          id="practice-create-form"
          className="modal-form-stack"
          onSubmit={handleCreateSubmit}
        >
          <label className="field-label" htmlFor="pc-season">
            Season
          </label>
          <select
            id="pc-season"
            className="field-input field-select"
            value={form.season}
            onChange={(e) =>
              setForm((f) => ({ ...f, season: e.target.value }))
            }
            required
          >
            <option value="" disabled>
              Select season
            </option>
            {sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.year}
              </option>
            ))}
          </select>

          <div className="practice-datetime-row">
            <div>
              <label className="field-label" htmlFor="pc-practice-date">
                Date
              </label>
              <input
                id="pc-practice-date"
                type="date"
                className="field-input"
                value={form.practiceDate}
                onChange={(e) =>
                  setForm((f) => ({ ...f, practiceDate: e.target.value }))
                }
                required
              />
            </div>
            <div>
              <label className="field-label" htmlFor="pc-practice-time">
                Time <span className="muted">(15 min)</span>
              </label>
              <select
                id="pc-practice-time"
                className="field-input field-select"
                value={form.practiceTime}
                onChange={(e) =>
                  setForm((f) => ({ ...f, practiceTime: e.target.value }))
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

          <label className="field-label" htmlFor="pc-race">
            NYRR race <span className="muted">(optional)</span>
          </label>
          <input
            id="pc-race"
            type="text"
            className="field-input"
            value={form.nyrr_race}
            onChange={(e) =>
              setForm((f) => ({ ...f, nyrr_race: e.target.value }))
            }
            maxLength={150}
          />

          <label className="field-label checkbox-label">
            <input
              type="checkbox"
              checked={form.full_practice}
              onChange={(e) =>
                setForm((f) => ({ ...f, full_practice: e.target.checked }))
              }
            />
            Full practice
          </label>

          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'edit'}
        title="Edit practice"
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
              form="practice-edit-form"
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
          id="practice-edit-form"
          className="modal-form-stack"
          onSubmit={handleEditSubmit}
        >
          <label className="field-label" htmlFor="pe-season">
            Season
          </label>
          <select
            id="pe-season"
            className="field-input field-select"
            value={form.season}
            onChange={(e) =>
              setForm((f) => ({ ...f, season: e.target.value }))
            }
            required
          >
            {sortedSeasons.map((s) => (
              <option key={s.id} value={String(s.id)}>
                {s.year}
              </option>
            ))}
          </select>

          <div className="practice-datetime-row">
            <div>
              <label className="field-label" htmlFor="pe-practice-date">
                Date
              </label>
              <input
                id="pe-practice-date"
                type="date"
                className="field-input"
                value={form.practiceDate}
                onChange={(e) =>
                  setForm((f) => ({ ...f, practiceDate: e.target.value }))
                }
                required
              />
            </div>
            <div>
              <label className="field-label" htmlFor="pe-practice-time">
                Time <span className="muted">(15 min)</span>
              </label>
              <select
                id="pe-practice-time"
                className="field-input field-select"
                value={form.practiceTime}
                onChange={(e) =>
                  setForm((f) => ({ ...f, practiceTime: e.target.value }))
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

          <label className="field-label" htmlFor="pe-race">
            NYRR race <span className="muted">(optional)</span>
          </label>
          <input
            id="pe-race"
            type="text"
            className="field-input"
            value={form.nyrr_race}
            onChange={(e) =>
              setForm((f) => ({ ...f, nyrr_race: e.target.value }))
            }
            maxLength={150}
          />

          <label className="field-label checkbox-label">
            <input
              type="checkbox"
              checked={form.full_practice}
              onChange={(e) =>
                setForm((f) => ({ ...f, full_practice: e.target.checked }))
              }
            />
            Full practice
          </label>

          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete practice"
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
          Delete this practice on{' '}
          <strong>
            {activePractice?.date
              ? formatDateTime(activePractice.date)
              : '—'}
          </strong>
          {activePractice?.nyrr_race ? (
            <>
              {' '}
              ({activePractice.nyrr_race})?
            </>
          ) : (
            '?'
          )}
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
