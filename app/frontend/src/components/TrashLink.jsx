import { Link } from 'react-router-dom'

// Small 🗑 affordance placed next to a page's title, mirroring HelpButton's
// own shape — quick access to this module's own trashed items (2026-09-05,
// UX Polish Batch #5). `module` pre-filters the Trash page to this module's
// entries via its `?module=` query param.
//
// w-11 h-11 (44×44px) gives this a real WCAG/platform touch-target floor —
// same reasoning as SelectCheckbox.jsx: real box space in the flex layout,
// not a negative-margin "enlarge without shifting neighbors" trick, since
// that trick is a documented real bug elsewhere in this codebase (see
// SelectCheckbox.jsx's own comment). Unlike SelectCheckbox's tight list
// rows, this renders in a title row with generous gap-2 spacing, so the
// bigger box doesn't risk overlapping a neighbor.
export default function TrashLink({ module, className = '' }) {
  return (
    <Link
      to={`/trash?module=${module}`}
      title="View trash"
      aria-label="View trash"
      className={`inline-flex items-center justify-center w-11 h-11 rounded-full text-charcoal-400 hover:text-orange-500 hover:bg-orange-500/10 transition-colors ${className}`}
    >
      🗑
    </Link>
  )
}
