import './Modal.css'

export function Modal({
  open,
  title,
  children,
  footer,
  onClose,
  closeDisabled = false,
}) {
  if (!open) return null

  return (
    <div className="modal-root" aria-hidden={false}>
      <div className="modal-backdrop" />
      <div
        role="dialog"
        aria-modal
        aria-labelledby="modal-heading"
        className="modal-panel"
      >
        <div className="modal-head">
          <h3 id="modal-heading">{title}</h3>
          <button
            type="button"
            className="modal-icon-btn"
            aria-label="Close"
            disabled={closeDisabled}
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  )
}
