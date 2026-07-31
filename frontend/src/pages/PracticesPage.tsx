import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from 'react'
import { Link } from 'react-router-dom'

import {
  createPractice,
  deletePractice,
  fetchPractice,
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
import type { Practice, Season } from '../types.js'

type PracticeModal = 'create' | 'edit' | 'delete'

type PracticeFormState = {
  practiceDate: string
  practiceTime: string
  nyrr_race: string
  description: string
  start_location: string
  full_practice: boolean
  show_to_mentors: boolean
  season: string
}

type PracticePayload = {
  date: string
  nyrr_race: string
  description: string
  start_location: string
  full_practice: boolean
  show_to_mentors: boolean
  season: number
}

function isoToPracticeDateAndTime(iso: string | null | undefined) {
  const { date, time } = isoToDateAndQuarterTime(iso ?? '')
  return { practiceDate: date, practiceTime: time }
}

function emptyPracticeForm(defaultSeasonId: number | string): PracticeFormState {
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

function resizeDescriptionTextarea(event: ChangeEvent<HTMLTextAreaElement> | FocusEvent) {
  const el = event.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function PracticeDescriptionField({
  formId,
  value,
  onChange,
}: {
  formId: string
  value: string
  onChange: (value: string) => void
}) {
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
  const [practices, setPractices] = useState<Practice[]>([])
  const [seasons, setSeasons] = useState<Season[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [seasonFilter, setSeasonFilter] = useState('')

  const [modal, setModal] = useState<PracticeModal | null>(null)
  const [schedulerOpen, setSchedulerOpen] = useState(false)
  const [activePractice, setActivePractice] = useState<Practice | null>(null)
  const [form, setForm] = useState<PracticeFormState>(() => emptyPracticeForm(''))
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showToMentorsBusyIds, setShowToMentorsBusyIds] = useState<Set<number>>(
    () => new Set()
  )
  const [showToMentorsBulkBusy, setShowToMentorsBulkBusy] = useState(false)
  const showAllUpcomingRef = useRef<HTMLInputElement | null>(null)

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
    const m = new Map<number, number>()
    for (const s of seasons) m.set(s.id, s.year)
    return m
  }, [seasons])

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoadError(null)
      try {
        const sList = await fetchSeasons()
        if (cancelled) return
        const orderedSeasons = sortSeasonsByYearDesc(sList)
        setSeasons(orderedSeasons)
        const current = currentSeasonFromList(orderedSeasons)
        const initialId = current?.id ?? orderedSeasons[0]?.id
        if (initialId != null) {
          setSeasonFilter(String(initialId))
        } else {
          setLoading(false)
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setSeasons([])
          setLoading(false)
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!seasonFilter) {
      setPractices([])
      return
    }

    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const pList = await fetchPractices({ season: seasonFilter })
        if (!cancelled) {
          setPractices(pList)
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setPractices([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [seasonFilter])

  const filteredPractices = practices

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

  const openEdit = async (practice: Practice) => {
    setModalError('')
    setActivePractice(practice)
    setModal('edit')
    setBusy(true)
    try {
      const full = await fetchPractice(practice.id, { basic: true })
      const { practiceDate, practiceTime } = isoToPracticeDateAndTime(full.date)
      setForm({
        practiceDate,
        practiceTime,
        nyrr_race: full.nyrr_race ?? '',
        description: full.description ?? '',
        start_location: full.start_location ?? '',
        full_practice: Boolean(full.full_practice),
        show_to_mentors: Boolean(full.show_to_mentors),
        season: String(full.season ?? ''),
      })
      setActivePractice(full)
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
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
    } finally {
      setBusy(false)
    }
  }

  const openDelete = (practice: Practice) => {
    setModalError('')
    setActivePractice(practice)
    setModal('delete')
  }

  const buildPayload = ():
    | { error: string }
    | { payload: PracticePayload } => {
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

  const handleCreateSubmit = async (e: FormEvent<HTMLFormElement>) => {
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
      if (String(created.season) === seasonFilter) {
        setPractices((prev) => [...prev, created])
      }
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
    if (!activePractice) return
    const built = buildPayload()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      const updated = await patchPractice(activePractice.id, built.payload)
      setPractices((prev) => {
        if (String(updated.season) !== seasonFilter) {
          return prev.filter((p) => p.id !== activePractice.id)
        }
        return prev.map((p) => (p.id === activePractice.id ? updated : p))
      })
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

  const upcomingShowToMentorsState = useMemo(() => {
    if (upcomingPractices.length === 0) {
      return { all: false, some: false, none: true }
    }
    const shown = upcomingPractices.filter((p) => p.show_to_mentors).length
    return {
      all: shown === upcomingPractices.length,
      some: shown > 0 && shown < upcomingPractices.length,
      none: shown === 0,
    }
  }, [upcomingPractices])

  useEffect(() => {
    const el = showAllUpcomingRef.current
    if (!el) return
    el.indeterminate = upcomingShowToMentorsState.some
  }, [upcomingShowToMentorsState.some])

  async function setPracticeShowToMentors(
    practice: Practice,
    showToMentors: boolean
  ): Promise<Practice> {
    if (Boolean(practice.show_to_mentors) === showToMentors) return practice
    const updated = await patchPractice(practice.id, {
      show_to_mentors: showToMentors,
    })
    setPractices((prev) =>
      prev.map((row) => (row.id === practice.id ? { ...row, ...updated } : row))
    )
    return updated
  }

  async function togglePracticeShowToMentors(practice: Practice) {
    const next = !Boolean(practice.show_to_mentors)
    setShowToMentorsBusyIds((prev) => new Set(prev).add(practice.id))
    setLoadError(null)
    try {
      await setPracticeShowToMentors(practice, next)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setShowToMentorsBusyIds((prev) => {
        const nextIds = new Set(prev)
        nextIds.delete(practice.id)
        return nextIds
      })
    }
  }

  async function setUpcomingShowToMentors(showToMentors: boolean) {
    const targets = upcomingPractices.filter(
      (p) => Boolean(p.show_to_mentors) !== showToMentors
    )
    if (targets.length === 0) return
    setShowToMentorsBulkBusy(true)
    setLoadError(null)
    try {
      const results = await Promise.all(
        targets.map((practice) =>
          patchPractice(practice.id, { show_to_mentors: showToMentors })
        )
      )
      const byId = new Map(results.map((row) => [row.id, row]))
      setPractices((prev) =>
        prev.map((row) => {
          const updated = byId.get(row.id)
          return updated ? { ...row, ...updated } : row
        })
      )
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
      try {
        const refreshed = await fetchPractices({ season: seasonFilter })
        setPractices(refreshed)
      } catch {
        /* keep local state if refresh also fails */
      }
    } finally {
      setShowToMentorsBulkBusy(false)
    }
  }

  function renderPracticeRow(p: Practice): ReactNode {
    const showBusy =
      showToMentorsBusyIds.has(p.id) || showToMentorsBulkBusy
    return (
      <li key={p.id} className="practice-row practices-list-row">
        <div className="practice-row-main">
          <span className="practice-date">
            {p.date ? formatDateTime(p.date) : '—'}
          </span>
          {p.nyrr_race?.trim() ? (
            <span className="practice-race">{p.nyrr_race}</span>
          ) : null}
        </div>
        <div className="practice-row-visibility">
          <label className="practice-show-to-mentors-toggle">
            <input
              type="checkbox"
              checked={Boolean(p.show_to_mentors)}
              disabled={showBusy || busy}
              onChange={() => togglePracticeShowToMentors(p)}
            />
            <span>Show to mentors</span>
          </label>
          <span
            className={
              p.show_to_mentors
                ? 'practice-show-to-mentors-status is-shown'
                : 'practice-show-to-mentors-status muted'
            }
          >
            {p.show_to_mentors ? 'Visible to mentors' : 'Hidden from mentors'}
          </span>
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
        <div className="muted practices-list-meta">
          <span>
            Season{' '}
            {p.season != null
              ? (seasonYearById.get(p.season) ?? p.season)
              : '—'}
            {p.full_practice ? ' · Full practice' : ' · Partial'}
          </span>
          {p.start_location?.trim() ? (
            <span>Start: {p.start_location.trim()}</span>
          ) : null}
        </div>
        {p.description?.trim() ? (
          <div className="muted practice-description-preview practices-list-description">
            {p.description.trim()}
          </div>
        ) : null}
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
              disabled={loading || upcomingPractices.length === 0}
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
            <div className="practices-show-mentors-toolbar">
              <label className="practice-show-to-mentors-toggle practices-show-all-toggle">
                <input
                  type="checkbox"
                  ref={showAllUpcomingRef}
                  checked={upcomingShowToMentorsState.all}
                  disabled={showToMentorsBulkBusy || busy}
                  onChange={(e) => setUpcomingShowToMentors(e.target.checked)}
                />
                <span>Show all upcoming to mentors</span>
              </label>
              <p className="muted practices-show-mentors-hint">
                Check or uncheck individual practices below to override.
              </p>
            </div>
            <ul className="practice-list practices-page-list">
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
            <ul className="practice-list practices-page-list">
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
        panelClassName="modal-panel-practice"
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
        panelClassName="modal-panel-practice"
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
        practices={upcomingPractices.map((p) => ({
          id: p.id,
          date: p.date ?? undefined,
          nyrr_race: p.nyrr_race ?? undefined,
        }))}
        open={schedulerOpen}
        onClose={() => setSchedulerOpen(false)}
        onApplied={async () => {
          try {
            const pList = await fetchPractices({ season: seasonFilter })
            setPractices(pList)
          } catch (e) {
            setLoadError(e instanceof Error ? e.message : String(e))
            throw e
          }
        }}
      />
    </>
  )
}
