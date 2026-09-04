import { useEffect } from 'react'

// Shared Escape-to-close behavior for modals (item #8 of the 2026-09-04 UX
// Polish Batch). No single shared <Modal> wrapper exists in this codebase —
// each modal hand-rolls its own .modal-overlay/.modal-card markup — so this
// ships as a hook every modal wires in individually rather than a wrapper
// refactor. When hasUnsavedChanges is true, Escape defers to the caller's own
// unsaved-changes warning (item #9) instead of closing directly, matching
// clicking outside or the X button.
export default function useEscapeToClose(onClose, { hasUnsavedChanges = false, onUnsavedAttempt } = {}) {
  useEffect(() => {
    function onKey(e) {
      if (e.key !== 'Escape') return
      if (hasUnsavedChanges && onUnsavedAttempt) {
        onUnsavedAttempt()
      } else {
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, hasUnsavedChanges, onUnsavedAttempt])
}
