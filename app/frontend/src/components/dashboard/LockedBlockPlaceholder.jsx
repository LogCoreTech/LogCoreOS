const MESSAGES = {
  admin_only: 'Admin-only block',
  no_access: "You don't have access to this",
  not_found: 'Not found',
  owner_lost_access: "The dashboard owner no longer has access to this",
  // Used by Chat.jsx's dashboard-tool approval preview (2026-08-09) — this
  // block doesn't exist yet, so there's no real data to resolve.
  pending_approval: 'Pending approval — preview only',
}

// pending_approval isn't an access restriction like the others (🔒 would be
// misleading — nothing is locked, it's just not saved yet).
const ICONS = {
  pending_approval: '⏳',
}

export default function LockedBlockPlaceholder({ reason }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center gap-1 text-charcoal-400 dark:text-charcoal-500 p-3">
      <span className="text-xl">{ICONS[reason] || '🔒'}</span>
      <p className="text-xs">{MESSAGES[reason] || 'Unavailable'}</p>
    </div>
  )
}
