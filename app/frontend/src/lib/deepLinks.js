// Single source of truth for "module -> route" and "module -> its deep-link
// query param" so URL construction never has to be hand-maintained in more
// than one place (Layout.jsx's notification-bell navTarget() and the
// dashboard's nav_button block both go through this).

import { MODULE_PACKAGES } from './moduleRegistry'

const _CORE_MODULE_ROUTES = {
  tasks: '/tasks',
  goals: '/goals',
  calendar: '/calendar',
  household: '/household',
  team: '/team',
  notes: '/notes',
  chat: '/chat',
  automations: '/automations',
  home: '/home',
  assets: '/assets',
  finance: '/finance',
  contacts: '/contacts',
  dashboard: '/',
}

// A converted module needs no entry here — its route is discovered from its
// own manifest.js (moduleRegistry.js), same as constants.js's ALL_MODULES.
export const MODULE_ROUTES = {
  ..._CORE_MODULE_ROUTES,
  ...Object.fromEntries(MODULE_PACKAGES.map(m => [m.id, m.to])),
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
  dashboard: 'id',
  chat: 'chat_id',
}

// Sections/sub-pages a module exposes beyond its own bare landing page.
// Finance and Automations expose theirs via a `?view=` query param their own
// page already reads (Finance.jsx / Automations.jsx); Settings has no
// query-param views at all — its pages are real distinct routes, so its
// "sections" are just those routes directly, handled as a special case in
// deepLinkUrl below rather than forcing it through the `?view=` shape.
// `adminOnly` entries are a UI nicety (skip offering routes the dashboard
// owner can't reach themselves) — actual access is still enforced by each
// route's own <AdminOnly> guard, not by anything here.
export const MODULE_SECTIONS = {
  finance: [
    { value: 'overview', label: 'Overview' },
    { value: 'transactions', label: 'Transactions' },
    { value: 'budgets', label: 'Budgets' },
    { value: 'recurring', label: 'Recurring' },
    { value: 'invoices', label: 'Invoices' },
    { value: 'reports', label: 'Reports' },
  ],
  automations: [
    { value: 'inbox', label: 'Inbox' },
  ],
  settings: [
    { value: '/settings/appearance', label: 'Appearance' },
    { value: '/settings/notifications', label: 'Notifications' },
    { value: '/settings/shortcuts', label: 'Shortcuts' },
    { value: '/settings/account', label: 'Account' },
    { value: '/settings/admin', label: 'Admin Settings', adminOnly: true },
    { value: '/settings/admin/users', label: 'Admin Settings → Users & Roles', adminOnly: true },
    { value: '/settings/admin/ai', label: 'Admin Settings → AI', adminOnly: true },
    { value: '/settings/admin/general', label: 'Admin Settings → General', adminOnly: true },
    { value: '/settings/admin/team', label: 'Admin Settings → Team', adminOnly: true },
    { value: '/settings/admin/household', label: 'Admin Settings → Household', adminOnly: true },
    { value: '/settings/admin/hosting', label: 'Admin Settings → Hosting', adminOnly: true },
    { value: '/settings/admin/mod-store', label: 'Admin Settings → Mod Store', adminOnly: true },
  ],
}

export function deepLinkUrl(module, recordId, section) {
  // Settings isn't a real module (no ALL_MODULES entry, no require_module
  // gate) and its sections are already full paths, not a query-param view —
  // handled entirely separately from the record-based modules below.
  if (module === 'settings') return section || '/settings'
  const base = MODULE_ROUTES[module] || '/'
  if (section) return `${base}?view=${encodeURIComponent(section)}`
  const param = RECORD_PARAM[module]
  if (!recordId || !param) return base
  return `${base}?${param}=${encodeURIComponent(recordId)}`
}
