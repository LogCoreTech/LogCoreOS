// Shared chrome for a small single-purpose form modal: title + close (✕),
// arbitrary body content (an input, a select, a description paragraph — or
// any mix), an inline error line, and a Cancel/Confirm footer. Extracted
// from Notes.jsx's six near-identical modals (new note, new folder, rename,
// move, delete note, delete folder), which differed only in title, body
// content, and the confirm button's label/variant/handler — the
// .modal-overlay/.modal-card shape, header, error line, and footer were
// byte-for-byte identical across all six.
//
// Deliberately does NOT wire up useEscapeToClose/useFocusTrap/useScrollLock
// or createPortal itself — callers with several mutually-exclusive modals
// backed by one `modal` state value (like Notes.jsx) already own that
// wiring once at the parent level against a single shared card ref, keyed
// off whether any modal is open, so re-adding it per-instance here would
// just duplicate it. Pass that shared ref in as `cardRef`.
export default function SimpleFormModal({
  cardRef,
  title,
  onClose,
  onCancel,
  onSubmit,
  submitLabel,
  submitBusyLabel,
  busy = false,
  submitDisabled = false,
  danger = false,
  error,
  children,
}) {
  return (
    <div className="modal-overlay">
      <div ref={cardRef} className="modal-card p-5 max-w-sm">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>
        {children}
        {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onCancel} className="btn-ghost flex-1">Cancel</button>
          <button
            onClick={onSubmit}
            disabled={submitDisabled}
            className={danger
              ? 'flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors'
              : 'btn-primary flex-1'}
          >
            {busy ? submitBusyLabel : submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
