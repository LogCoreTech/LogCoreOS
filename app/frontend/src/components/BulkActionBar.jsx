import { createPortal } from 'react-dom'

// Shared bulk-action bar (UX Polish Batch #4) — one component, both
// surfaces, controlled purely by Tailwind breakpoints (no JS viewport
// detection anywhere else in this codebase, so none introduced here
// either). Mobile: fixed to the bottom, z-50 + safe-area padding, matching
// Layout.jsx's own "More" module drawer convention so it sits above the
// z-40 bottom nav — portaled to document.body like Toast/ConfirmDialog,
// since a `fixed` element nested inside any ancestor with backdrop-filter/
// transform (a real, previously-hit bug in this exact codebase — see
// ConfirmDialog.jsx's own docstring) would otherwise resolve against that
// ancestor's box instead of the true viewport. Desktop: a sticky top
// toolbar instead — thumb reach doesn't matter there, no bottom nav to
// clear, and `position: sticky` doesn't share the portal-or-not concern
// `fixed` does, so it renders inline.
export default function BulkActionBar({ count, onCancel, actions }) {
  if (count === 0) return null

  const buttons = actions.map((action) => (
    <button
      key={action.label}
      type="button"
      onClick={action.onClick}
      disabled={action.busy}
      className={
        action.variant === 'danger'
          ? 'btn-ghost text-sm text-red-500 hover:text-red-600'
          : 'btn-ghost text-sm'
      }
    >
      {action.label}
    </button>
  ))

  return (
    <>
      {createPortal(
        <div className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white dark:bg-charcoal-950 border-t border-charcoal-200 dark:border-charcoal-800 pb-[env(safe-area-inset-bottom)]">
          <div className="flex items-center justify-between gap-2 px-4 py-3">
            <button type="button" onClick={onCancel} className="text-sm text-charcoal-500 dark:text-charcoal-400">
              Cancel
            </button>
            <span className="text-sm font-medium">{count} selected</span>
            <div className="flex gap-1">{buttons}</div>
          </div>
        </div>,
        document.body
      )}

      {/* Desktop: sticky top toolbar */}
      <div className="hidden md:flex sticky top-0 z-20 items-center justify-between gap-2 card px-4 py-2.5">
        <span className="text-sm font-medium">{count} selected</span>
        <div className="flex gap-2">
          {buttons}
          <button type="button" onClick={onCancel} className="btn-ghost text-sm">
            Cancel
          </button>
        </div>
      </div>
    </>
  )
}
