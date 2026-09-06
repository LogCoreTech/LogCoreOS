import { Link } from 'react-router-dom'

// Small 🗑 affordance placed next to a page's title, mirroring HelpButton's
// own shape — quick access to this module's own trashed items (2026-09-05,
// UX Polish Batch #5). `module` pre-filters the Trash page to this module's
// entries via its `?module=` query param.
export default function TrashLink({ module, className = '' }) {
  return (
    <Link
      to={`/trash?module=${module}`}
      title="View trash"
      aria-label="View trash"
      className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-charcoal-400 hover:text-orange-500 hover:bg-orange-500/10 transition-colors ${className}`}
    >
      🗑
    </Link>
  )
}
