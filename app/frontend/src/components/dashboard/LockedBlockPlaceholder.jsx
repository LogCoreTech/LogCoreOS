const MESSAGES = {
  admin_only: 'Admin-only block',
  no_access: "You don't have access to this",
  not_found: 'Not found',
  owner_lost_access: "The dashboard owner no longer has access to this",
}

export default function LockedBlockPlaceholder({ reason }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center gap-1 text-charcoal-400 dark:text-charcoal-500 p-3">
      <span className="text-xl">🔒</span>
      <p className="text-xs">{MESSAGES[reason] || 'Unavailable'}</p>
    </div>
  )
}
