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
import { PracticeMentorSchedulerModal } from '../components/PracticeMentorScheduler.jsx'
import { AppHeader } from '../components/AppHeader.jsx'
import {
  buildQuarterTimeOptions,
  dateAndQuarterTimeToIso,
  formatDateTime,
  isoToDateAndQuarterTime,
} from '../datetime.js'
import {
  currentSeasonFromList,
  sortSeasonsByYearDesc,
  splitPracticesByUpcoming,
} from '../seasonHelpers.js'

function isoToPracticeDateAndTime(iso) {
  const { date, time } = isoToDateAndQuarterTime(iso)
  return { practiceDate: date, practiceTime: time }
}

function emptyPracticeForm(defaultSeasonId) {
  return {
    practiceDate: '',
    practiceTime: '09:00',
    nyrr_race: '',
    description: '',
    start_location: '',
    full_practice: true,
    show_to_mentors: false,
    season: defaultSeasonId === '' ? '' : String(defaultSeasonId),
  }
}

function resizeDescriptionTextarea(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function PracticeDescriptionField({ formId, value, onChange }) {
  useEffect(() => {
    const el = document.getElementById(`${formId}-description`)
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [formId, value])

  return (
    <>
      <label className="field-label" htmlFor={`${formId}-description`}>
        Description <span className="muted">(optional)</span>
      </label>
      <textarea
        id={`${formId}-description`}
        className="field-input field-textarea practice-description-textarea"
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          resizeDescriptionTextarea(e)
        }}
        onFocus={resizeDescriptionTextarea}
        rows={12}
        spellCheck
      />
    </>
  )
}

export default function PracticesPage() {
  const [practices, setPractices] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [seasonFilter, setSeasonFilter] = useState('')

  const [modal, setModal] = useState(null)
  const [schedulerOpen, setSchedulerOpen] = useState(false)
  const [activePractice, setActivePractice] = useState(null)
  const [form, setForm] = useState(() => emptyPracticeForm(''))
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)

  const sortedSeasons = useMemo(
    () => sortSeasonsByYearDesc(seasons),
    [seasons]
  )

  const currentSeason = useMemo(
    () => currentSeasonFromList(seasons),
    [seasons]
  )

  const defaultSeasonId = currentSeason?.id ?? sortedSeasons[0]?.id ?? ''

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
          setPractices(pList)
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
    if (!seasonFilter) return []
    const id = Number.parseInt(seasonFilter, 10)
    if (Number.isNaN(id)) return []
    return practices.filter((p) => p.season === id)
  }, [practices, seasonFilter])

  const { upcoming: upcomingPractices, past: pastPractices } = useMemo(
    () => splitPracticesByUpcoming(filteredPractices),
    [filteredPractices]
  )

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
      description: practice.description ?? '',
      start_location: practice.start_location ?? '',
      full_practice: Boolean(practice.full_practice),
      show_to_mentors: Boolean(practice.show_to_mentors),
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
        description: form.description.trim(),
        start_location: form.start_location.trim(),
        full_practice: form.full_practice,
        show_to_mentors: form.show_to_mentors,
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
      setPractices((prev) => [...prev, created])
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
        prev.map((p) => (p.id === activePractice.id ? updated : p))
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

  function renderPracticeRow(p) {
    return (
      <li key={p.id} className="practice-row">
        <div className="practice-row-main">
          <span className="practice-date">
            {p.date ? formatDateTime(p.date) : '—'}
          </span>
          <span className="practice-race">
            {p.nyrr_race?.trim() ? (
              p.nyrr_race
            ) : (
              <span className="muted">No race name</span>
            )}
          </span>
          <span className="muted">
            Season {seasonYearById.get(p.season) ?? p.season}
            {p.full_practice ? ' · Full practice' : ' · Partial'}
          </span>
          {p.description?.trim() ? (
            <span className="muted practice-description-preview">
              {p.description.trim()}
            </span>
          ) : null}
          {p.start_location?.trim() ? (
            <span className="muted">Start: {p.start_location.trim()}</span>
          ) : null}
        </div>
        <div className="practice-row-actions">
          <Link className="btn btn-text" to={`/practices/${p.id}`}>
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
    )
  }

  const selectedSeasonYear =
    seasonFilter !== ''
      ? seasonYearById.get(Number.parseInt(seasonFilter, 10))
      : null

  return (
    <>
      <AppHeader />

      <main className="panel practices-panel">
        <div className="practices-toolbar">
          <h2>Practices</h2>
          <div className="practices-toolbar-actions">
            <button
              type="button"
              className="btn btn-secondary practices-schedule-btn"
              disabled={loading || filteredPractices.length === 0}
              onClick={() => setSchedulerOpen(true)}
            >
              Schedule mentors
            </button>
            <button
              type="button"
              className="btn-icon-plus"
              aria-label="Add practice"
              title="Add practice"
              disabled={loading || sortedSeasons.length === 0}
              onClick={openCreate}
            >
              +
            </button>
          </div>
        </div>

        <div className="practices-filter">
          <label className="field-label" htmlFor="season-filter">
            Season
          </label>
          <select
            id="season-filter"
            className="field-input field-select"
            value={seasonFilter}
            onChange={(e) => setSeasonFilter(e.target.value)}
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
          {currentSeason && seasonFilter === String(currentSeason.id) ? (
            <p className="muted practices-filter-note">
              Showing the current season by default.
            </p>
          ) : null}
        </div>

        {loading && <p className="muted">Loading…</p>}
        {loadError && (
          <p className="error" role="alert">
            {loadError}
          </p>
        )}

        {!loading && !loadError && sortedSeasons.length === 0 && (
          <p className="muted">
            Create a season first, then add practices for that season.
          </p>
        )}

        {!loading &&
          !loadError &&
          seasonFilter &&
          filteredPractices.length === 0 && (
            <p className="muted">
              No practices yet for season {selectedSeasonYear ?? '—'}. Use + to
              add one.
            </p>
          )}

        {!loading && !loadError && upcomingPractices.length > 0 && (
          <section className="practices-section" aria-label="Upcoming practices">
            <ul className="practice-list">
              {upcomingPractices.map((p) => renderPracticeRow(p))}
            </ul>
          </section>
        )}

        {!loading &&
          !loadError &&
          seasonFilter &&
          upcomingPractices.length === 0 &&
          pastPractices.length > 0 && (
            <p className="muted">No upcoming practices for this season.</p>
          )}

        {!loading && !loadError && pastPractices.length > 0 && (
          <section
            className="practices-section practices-past-section"
            aria-labelledby="past-practices-heading"
          >
            <h3 id="past-practices-heading" className="practices-section-heading">
              Past practices
            </h3>
            <ul className="practice-list">
              {pastPractices.map((p) => renderPracticeRow(p))}
            </ul>
          </section>
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
                {s.is_current ? ' (current)' : ''}
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

          <PracticeDescriptionField
            formId="pc"
            value={form.description}
            onChange={(description) =>
              setForm((f) => ({ ...f, description }))
            }
          />

          <label className="field-label" htmlFor="pc-start-location">
            Start location <span className="muted">(optional)</span>
          </label>
          <input
            id="pc-start-location"
            type="text"
            className="field-input"
            value={form.start_location}
            onChange={(e) =>
              setForm((f) => ({ ...f, start_location: e.target.value }))
            }
            maxLength={255}
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

          <label className="field-label checkbox-label">
            <input
              type="checkbox"
              checked={form.show_to_mentors}
              onChange={(e) =>
                setForm((f) => ({ ...f, show_to_mentors: e.target.checked }))
              }
            />
            Show to mentors
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
                {s.is_current ? ' (current)' : ''}
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

          <PracticeDescriptionField
            formId="pe"
            value={form.description}
            onChange={(description) =>
              setForm((f) => ({ ...f, description }))
            }
          />

          <label className="field-label" htmlFor="pe-start-location">
            Start location <span className="muted">(optional)</span>
          </label>
          <input
            id="pe-start-location"
            type="text"
            className="field-input"
            value={form.start_location}
            onChange={(e) =>
              setForm((f) => ({ ...f, start_location: e.target.value }))
            }
            maxLength={255}
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

          <label className="field-label checkbox-label">
            <input
              type="checkbox"
              checked={form.show_to_mentors}
              onChange={(e) =>
                setForm((f) => ({ ...f, show_to_mentors: e.target.checked }))
              }
            />
            Show to mentors
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

      <PracticeMentorSchedulerModal
        practices={filteredPractices}
        open={schedulerOpen}
        onClose={() => setSchedulerOpen(false)}
        onApplied={async () => {
          try {
            const pList = await fetchPractices()
            setPractices(pList)
          } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e))
          }
        }}
      />
    </>
  )
}
