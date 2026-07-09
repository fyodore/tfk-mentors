import { useMemo, useState } from 'react'

import { scheduleMentors } from '../api'
import { Modal } from '../components/Modal.jsx'
import { formatDateTime } from '../datetime.js'
import { PACE_GROUPS } from '../paceHelpers.js'

function mentorName(row) {
  return `${row.first_name ?? ''} ${row.last_name ?? ''}`.trim() || '—'
}

function paceRows(byPace) {
  const rows = []
  for (const pace of PACE_GROUPS) {
    const mentors = byPace?.[pace]
    if (mentors?.length) {
      rows.push({ pace, mentors })
    }
  }
  for (const [pace, mentors] of Object.entries(byPace ?? {})) {
    if (!PACE_GROUPS.includes(pace) && mentors?.length) {
      rows.push({ pace, mentors })
    }
  }
  return rows
}

function ScheduleMentorList({ mentors, variant }) {
  if (!mentors?.length) return null
  return (
    <ul className={`schedule-mentor-list schedule-mentor-list-${variant}`}>
      {mentors.map((row) => (
        <li key={`${variant}-${row.mentor_id}-${row.pace}`}>
          <span className="schedule-mentor-name">{mentorName(row)}</span>
          <span className="muted schedule-mentor-meta">
            {row.pace}
            {row.selection_count != null ? ` · ${row.selection_count} selected` : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

function formatUnderfilledPaces(groups) {
  if (!groups?.length) return ''
  return groups
    .map(
      (group) =>
        `${group.pace} (${group.assigned_count}/${group.assigned_count + group.slots_remaining})`
    )
    .join(' · ')
}

function SchedulePracticeResult({ practice, maxPerPace = 4 }) {
  const assignmentRows = paceRows(practice.assignments_by_pace)
  const availableRows = paceRows(practice.available_by_pace)
  const underfilled = practice.underfilled_pace_groups ?? []
  const assignedTotal = assignmentRows.reduce(
    (sum, row) => sum + row.mentors.length,
    0
  )
  const availableTotal = availableRows.reduce(
    (sum, row) => sum + row.mentors.length,
    0
  )

  return (
    <article
      className={`schedule-practice-result${underfilled.length ? ' schedule-practice-result-underfilled' : ''}`}
    >
      <h4 className="schedule-practice-heading">
        {practice.date ? formatDateTime(practice.date) : '—'}
        {practice.nyrr_race?.trim() ? ` · ${practice.nyrr_race.trim()}` : ''}
      </h4>
      <p className="muted schedule-practice-summary">
        {assignedTotal} assigned
        {availableTotal > 0 ? ` · ${availableTotal} available` : ''}
      </p>
      {underfilled.length > 0 ? (
        <p className="schedule-underfilled-note" role="note">
          Needs more mentors: {formatUnderfilledPaces(underfilled)} (max {maxPerPace} per pace)
        </p>
      ) : null}
      {assignmentRows.length === 0 && availableRows.length === 0 ? (
        <p className="muted">No mentor assignments for this practice.</p>
      ) : null}
      {assignmentRows.map(({ pace, mentors }) => (
        <div key={`assign-${pace}`} className="schedule-pace-block">
          <h5 className="schedule-pace-heading">Assigned · {pace}</h5>
          <ScheduleMentorList mentors={mentors} variant="assigned" />
        </div>
      ))}
      {availableRows.map(({ pace, mentors }) => (
        <div key={`avail-${pace}`} className="schedule-pace-block">
          <h5 className="schedule-pace-heading">Available · {pace}</h5>
          <ScheduleMentorList mentors={mentors} variant="available" />
        </div>
      ))}
    </article>
  )
}

/**
 * @param {{
 *   practices: Array<{ id: number, date?: string, nyrr_race?: string }>,
 *   open: boolean,
 *   onClose: () => void,
 * }} props
 */
export function PracticeMentorSchedulerModal({ practices, open, onClose }) {
  const sortedPractices = useMemo(
    () =>
      [...practices].sort((a, b) => {
        const ta = a.date ? new Date(a.date).getTime() : 0
        const tb = b.date ? new Date(b.date).getTime() : 0
        return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb) || a.id - b.id
      }),
    [practices]
  )

  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [applied, setApplied] = useState(false)

  const allSelected =
    sortedPractices.length > 0 &&
    sortedPractices.every((practice) => selectedIds.has(practice.id))

  function togglePractice(practiceId) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(practiceId)) next.delete(practiceId)
      else next.add(practiceId)
      return next
    })
    setResult(null)
    setApplied(false)
    setError('')
  }

  function toggleAll() {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(sortedPractices.map((practice) => practice.id)))
    }
    setResult(null)
    setApplied(false)
    setError('')
  }

  async function runPreview() {
    const practiceIds = [...selectedIds]
    if (practiceIds.length === 0) {
      setError('Select at least one practice.')
      return
    }
    setBusy(true)
    setError('')
    setApplied(false)
    try {
      const data = await scheduleMentors(practiceIds)
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function runApply() {
    const practiceIds = [...selectedIds]
    if (practiceIds.length === 0) {
      setError('Select at least one practice.')
      return
    }
    const confirmed = window.confirm(
      'Apply this schedule? Assigned mentors will be added to practices and unassigned selections will move to available.'
    )
    if (!confirmed) return
    setBusy(true)
    setError('')
    try {
      const data = await scheduleMentors(practiceIds, { apply: true })
      setResult(data)
      setApplied(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function handleClose() {
    if (busy) return
    onClose()
  }

  return (
    <Modal
      open={open}
      title="Schedule mentors (first run)"
      onClose={handleClose}
      closeDisabled={busy}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={handleClose}
          >
            Close
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || selectedIds.size === 0}
            onClick={runPreview}
          >
            {busy && !applied ? 'Running…' : 'Preview schedule'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || selectedIds.size === 0 || !result}
            onClick={runApply}
          >
            {busy && applied ? 'Applying…' : 'Apply schedule'}
          </button>
        </>
      }
    >
      <div className="schedule-modal-body">
        <p className="muted schedule-intro">
          Select practices that mentors replied to. The algorithm uses their
          responses, groups by pace, assigns mentors who picked the fewest
          practices first, limits each mentor to two practices per month, and
          caps each pace group at four assigned mentors per practice. Unassigned
          selections move to available when a pace group still has room.
        </p>

        {sortedPractices.length === 0 ? (
          <p className="muted">No practices available for this season.</p>
        ) : (
          <div className="schedule-practice-picker">
            <label className="field-label checkbox-label schedule-select-all">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                disabled={busy}
              />
              Select all ({sortedPractices.length})
            </label>
            <ul className="schedule-practice-checklist">
              {sortedPractices.map((practice) => (
                <li key={practice.id}>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(practice.id)}
                      onChange={() => togglePractice(practice.id)}
                      disabled={busy}
                    />
                    <span>
                      {practice.date ? formatDateTime(practice.date) : '—'}
                      {practice.nyrr_race?.trim()
                        ? ` · ${practice.nyrr_race.trim()}`
                        : ''}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {result ? (
          <section className="schedule-results" aria-label="Schedule preview">
            <div className="schedule-summary">
              <p>
                <strong>{result.summary?.mentors_assigned ?? 0}</strong> mentors
                assigned across{' '}
                <strong>{result.summary?.assignment_rows ?? 0}</strong> slots
                {result.summary?.available_rows
                  ? ` · ${result.summary.available_rows} available`
                  : ''}
              </p>
              <p className="muted">
                Max {result.summary?.max_per_pace ?? 4} mentors per pace · max{' '}
                {result.summary?.max_per_month ?? 2} practices per mentor per
                month
              </p>
            </div>

            {(result.underfilled_practices ?? []).length > 0 ? (
              <section
                className="schedule-underfilled-section"
                aria-labelledby="schedule-underfilled-heading"
              >
                <h3 id="schedule-underfilled-heading" className="schedule-section-heading">
                  Practices needing more mentors
                </h3>
                <ul className="schedule-underfilled-list">
                  {result.underfilled_practices.map((practice) => (
                    <li key={practice.practice_id}>
                      <span className="schedule-underfilled-practice">
                        {practice.date ? formatDateTime(practice.date) : '—'}
                        {practice.nyrr_race?.trim()
                          ? ` · ${practice.nyrr_race.trim()}`
                          : ''}
                      </span>
                      <span className="schedule-underfilled-paces">
                        {formatUnderfilledPaces(practice.underfilled_pace_groups)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="schedule-practice-results">
              {(result.practices ?? []).map((practice) => (
                <SchedulePracticeResult
                  key={practice.practice_id}
                  practice={practice}
                  maxPerPace={result.summary?.max_per_pace ?? 4}
                />
              ))}
            </div>

            {(result.remote_mentors ?? []).length > 0 ? (
              <section
                className="schedule-remote-section"
                aria-labelledby="schedule-remote-heading"
              >
                <h3 id="schedule-remote-heading" className="schedule-section-heading">
                  Remote mentors who could attend
                </h3>
                <ul className="schedule-remote-list">
                  {result.remote_mentors.map((mentor) => (
                    <li key={mentor.mentor_id}>
                      <span className="schedule-mentor-name">{mentorName(mentor)}</span>
                      <span className="muted schedule-mentor-meta">
                        {mentor.email}
                        {mentor.pace ? ` · ${mentor.pace}` : ''}
                      </span>
                      <ul className="schedule-remote-practices">
                        {(mentor.practices ?? []).map((practice) => (
                          <li key={`${mentor.mentor_id}-${practice.practice_id}`}>
                            {practice.date ? formatDateTime(practice.date) : '—'}
                            {practice.nyrr_race?.trim()
                              ? ` · ${practice.nyrr_race.trim()}`
                              : ''}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {applied && result.applied ? (
              <p className="schedule-applied-note" role="status">
                Applied {result.applied.assigned ?? 0} assignments and{' '}
                {result.applied.available ?? 0} available moves.
                {(result.applied.errors ?? []).length > 0
                  ? ` ${result.applied.errors.length} issue(s) — check practice pages.`
                  : ''}
              </p>
            ) : null}
          </section>
        ) : null}
      </div>
    </Modal>
  )
}
