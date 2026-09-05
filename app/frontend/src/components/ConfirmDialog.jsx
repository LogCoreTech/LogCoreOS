import { useEffect, useRef, useState } from 'react'
import useEscapeToClose from '../lib/useEscapeToClose'
import useFocusTrap from '../lib/useFocusTrap'

// Shared confirmation dialog (item #7 of the 2026-09-04 UX Polish Batch) —
// replaces the app's 34 raw confirm()/window.confirm() call sites with one
// styled, accessible component. Modeled on GlobalSearch.jsx's own
// .modal-overlay/.modal-card shape (mobile-safe bottom-sheet, dark-mode
// themed).
//
// Two variants: plain Yes/No/Cancel (default, everything except account
// deletion), and a stricter "type X to confirm" variant (requireTypedText)
// used ONLY for account deletion — the confirm button stays disabled until
// the typed value matches exactly.
//
// Parent conditionally mounts this (`{confirmOpen && <ConfirmDialog .../>}`),
// matching every other modal in this codebase — there's no internal `open`
// prop to manage.
export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  requireTypedText = null, // e.g. "DELETE" — null means the plain variant
  onConfirm,
  onCancel,
}) {
  const [typedValue, setTypedValue] = useState('')
  const confirmBtnRef = useRef(null)
  const inputRef = useRef(null)
  const cardRef = useRef(null)

  useEscapeToClose(onCancel)
  useFocusTrap(cardRef)

  useEffect(() => {
    if (requireTypedText) inputRef.current?.focus()
    else confirmBtnRef.current?.focus()
  }, [requireTypedText])

  const typedMatches = !requireTypedText || typedValue === requireTypedText
  const titleId = 'confirm-dialog-title'

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        ref={cardRef}
        className="modal-card max-w-sm"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={e => e.stopPropagation()}
      >
        <h2 id={titleId} className="font-semibold mb-2">
          {title}
        </h2>
        {message && (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4 whitespace-pre-line">{message}</p>
        )}

        {requireTypedText && (
          <div className="mb-4">
            <label className="block text-xs text-charcoal-500 dark:text-charcoal-400 mb-1">
              Type <span className="font-mono font-semibold">{requireTypedText}</span> to confirm
            </label>
            <input
              ref={inputRef}
              className="input w-full"
              value={typedValue}
              onChange={e => setTypedValue(e.target.value)}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
            />
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="min-h-[44px] px-4 py-2 rounded-lg text-sm font-medium text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-800"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmBtnRef}
            onClick={onConfirm}
            disabled={!typedMatches}
            className={`min-h-[44px] px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed ${
              danger ? 'bg-red-600 hover:bg-red-500' : 'bg-orange-500 hover:bg-orange-400'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
