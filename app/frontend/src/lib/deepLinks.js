// Single source of truth for "module -> route" and "module -> its deep-link
// query param" so URL construction never has to be hand-maintained in more
// than one place (Layout.jsx's notification-bell navTarget() and the
// dashboard's nav_button block both go through this).

export const MODULE_ROUTES = {
  tasks: '/tasks',
  goals: '/goals',
  calendar: '/calendar',
  household: '/household',
  team: '/team',
  notes: '/notes',
  journal: '/journal',
  chat: '/chat',
  automations: '/automations',
  home: '/home',
  assets: '/assets',
  finance: '/finance',
  contacts: '/contacts',
  dashboard: '/',
}

// Query param each module's own page reads for a specific-record deep link.
// Only modules with an actual `useSearchParams` handler belong here —
// automations has no per-workflow detail view to land on yet.
const RECORD_PARAM = {
  tasks: 'task',
  calendar: 'event',
  notes: 'path',
  assets: 'asset',
  finance: 'book',
  contacts: 'contact',
}

export function deepLinkUrl(module, recordId) {
  const base = MODULE_ROUTES[module] || '/'
  const param = RECORD_PARAM[module]
  if (!recordId || !param) return base
  return `${base}?${param}=${encodeURIComponent(recordId)}`
}
