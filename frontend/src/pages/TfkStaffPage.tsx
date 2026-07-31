import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'

import {
  createTfkStaff,
  deleteTfkStaff,
  fetchTfkStaff,
  patchTfkStaff,
} from '../api'
import { AppHeader } from '../components/AppHeader.tsx'
import { Modal } from '../components/Modal.tsx'
import type { TfkStaff } from '../types.js'

type StaffModal = 'create' | 'edit' | 'delete'

type StaffFormState = {
  first_name: string
  last_name: string
  email: string
  cell_phone: string
}

type StaffPayload = {
  first_name: string
  last_name: string
  email: string
  cell_phone: string
}

function sortStaff(list: TfkStaff[]): TfkStaff[] {
  return [...list].sort((a, b) => {
    const ln = (a.last_name || '').localeCompare(b.last_name || '')
    if (ln !== 0) return ln
    const fn = (a.first_name || '').localeCompare(b.first_name || '')
    if (fn !== 0) return fn
    return a.id - b.id
  })
}

function emptyStaffForm(): StaffFormState {
  return {
    first_name: '',
    last_name: '',
    email: '',
    cell_phone: '',
  }
}

export default function TfkStaffPage() {
  const [staff, setStaff] = useState<TfkStaff[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [modal, setModal] = useState<StaffModal | null>(null)
  const [activeStaff, setActiveStaff] = useState<TfkStaff | null>(null)
  const [form, setForm] = useState<StaffFormState>(() => emptyStaffForm())
  const [modalError, setModalError] = useState('')
  const [busy, setBusy] = useState(false)

  const sortedStaff = useMemo(() => sortStaff(staff), [staff])

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const list = await fetchTfkStaff()
        if (!cancelled) setStaff(sortStaff(list))
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
          setStaff([])
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
    setActiveStaff(null)
    setModalError('')
  }

  const closeModal = () => {
    if (busy) return
    resetModal()
  }

  const openCreate = () => {
    setModalError('')
    setForm(emptyStaffForm())
    setActiveStaff(null)
    setModal('create')
  }

  const openEdit = (member: TfkStaff) => {
    setModalError('')
    setActiveStaff(member)
    setForm({
      first_name: member.first_name ?? '',
      last_name: member.last_name ?? '',
      email: member.email ?? '',
      cell_phone: member.cell_phone ?? '',
    })
    setModal('edit')
  }

  const openDelete = (member: TfkStaff) => {
    setModalError('')
    setActiveStaff(member)
    setModal('delete')
  }

  const buildPayload = (): { error: string } | { payload: StaffPayload } => {
    if (!form.first_name.trim()) return { error: 'First name is required.' }
    if (!form.last_name.trim()) return { error: 'Last name is required.' }
    if (!form.email.trim()) return { error: 'Email is required.' }
    return {
      payload: {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        cell_phone: form.cell_phone.trim(),
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
      const created = await createTfkStaff(built.payload)
      setStaff((prev) => sortStaff([...prev, created]))
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
    if (!activeStaff) return
    const built = buildPayload()
    if ('error' in built) {
      setModalError(built.error)
      return
    }
    setBusy(true)
    try {
      const updated = await patchTfkStaff(activeStaff.id, built.payload)
      setStaff((prev) =>
        sortStaff(prev.map((s) => (s.id === activeStaff.id ? updated : s)))
      )
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!activeStaff) return
    setModalError('')
    setBusy(true)
    try {
      await deleteTfkStaff(activeStaff.id)
      setStaff((prev) => prev.filter((s) => s.id !== activeStaff.id))
      resetModal()
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const staffFormFields = (formId: string): ReactNode => (
    <>
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
        Cell phone <span className="muted">(optional)</span>
      </label>
      <input
        id={`${formId}-cell`}
        type="text"
        className="field-input"
        value={form.cell_phone}
        onChange={(e) =>
          setForm((f) => ({ ...f, cell_phone: e.target.value }))
        }
        maxLength={20}
      />
    </>
  )

  return (
    <>
      <AppHeader />

      <main className="panel tfk-staff-panel">
        <div className="practices-toolbar">
          <h2>TFK Staff</h2>
          <button
            type="button"
            className="btn-icon-plus"
            aria-label="Add staff member"
            title="Add staff member"
            disabled={loading}
            onClick={openCreate}
          >
            +
          </button>
        </div>

        {loading && <p className="muted">Loading…</p>}
        {loadError && (
          <p className="error" role="alert">
            {loadError}
          </p>
        )}

        {!loading && !loadError && sortedStaff.length === 0 && (
          <p className="muted">No TFK staff yet. Use + to add one.</p>
        )}

        {!loading && !loadError && sortedStaff.length > 0 && (
          <ul className="practice-list">
            {sortedStaff.map((member) => (
              <li key={member.id} className="practice-row">
                <div className="practice-row-main">
                  <span className="practice-date">
                    {member.first_name} {member.last_name}
                  </span>
                  <span className="practice-race muted">{member.email}</span>
                  {member.cell_phone ? (
                    <span className="muted">{member.cell_phone}</span>
                  ) : null}
                </div>
                <div className="practice-row-actions">
                  <button
                    type="button"
                    className="btn btn-text"
                    onClick={() => openEdit(member)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-text btn-text-danger"
                    onClick={() => openDelete(member)}
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
        title="Add TFK staff"
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
              form="tfk-staff-create-form"
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
          id="tfk-staff-create-form"
          className="modal-form-stack"
          onSubmit={handleCreateSubmit}
        >
          {staffFormFields('tsc')}
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'edit'}
        title="Edit TFK staff"
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
              form="tfk-staff-edit-form"
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
          id="tfk-staff-edit-form"
          className="modal-form-stack"
          onSubmit={handleEditSubmit}
        >
          {staffFormFields('tse')}
          {modalError ? (
            <p className="error modal-error" role="alert">
              {modalError}
            </p>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={modal === 'delete'}
        title="Delete TFK staff"
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
          Delete staff member{' '}
          <strong>
            {activeStaff?.first_name} {activeStaff?.last_name}
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
