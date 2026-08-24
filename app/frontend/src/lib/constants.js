import { MODULE_PACKAGES } from './moduleRegistry'

export const CATEGORY_COLORS = {
  Religion:         'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  God:              'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  Family:           'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Job:              'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  LogCore:          'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
  'Personal Growth':'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
  Hobbies:          'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300',
}

export const DEFAULT_CAT_COLOR =
  'bg-charcoal-100 text-charcoal-700 dark:bg-charcoal-700 dark:text-charcoal-300'

export function catColor(cat) {
  return CATEGORY_COLORS[cat] || DEFAULT_CAT_COLOR
}

// ── Module registry ────────────────────────────────────────────────────────────
// Add future CORE (never converted) modules here — they appear in the drawer
// and Settings automatically. A CONVERTED module (module_packages/<id>/)
// needs no entry here at all — it's discovered automatically via
// moduleRegistry.js's import.meta.glob and merged into ALL_MODULES below.
const CORE_MODULES = [
  { id: 'dashboard',            to: '/',             icon: '⊞',          label: 'Dashboard'             },
  { id: 'tasks',                to: '/tasks',        icon: '✓',           label: 'Tasks'                 },
  { id: 'goals',                to: '/goals',        icon: '🎯',          label: 'Goals'                 },
  { id: 'calendar',             to: '/calendar',     icon: '📅',          label: 'Calendar'              },
  { id: 'household',            to: '/household',    icon: '🏠',          label: 'Household',  workspace: 'personal' },
  { id: 'notes',                to: '/notes',        icon: '📝',          label: 'Notes'                 },
  { id: 'chat',                 to: '/chat',         icon: '◈',           label: 'AI Chat'               },
  { id: 'automations',          to: '/automations',  icon: '⚡',          label: 'Automations'           },
  { id: 'automations_business', nav: false,                               label: 'Business Automations', workspace: 'business' },
  { id: 'home',                 to: '/home',         icon: '💡',          label: 'Smart Home', workspace: 'personal' },
  { id: 'team',                 to: '/team',         icon: '🧑‍🤝‍🧑',  label: 'Team',        workspace: 'business' },
  { id: 'assets',               to: '/assets',       icon: '🗂️',         label: 'Assets'                },
  { id: 'finance',              to: '/finance',      icon: '💵',          label: 'Finance'               },
  { id: 'contacts',             to: '/contacts',     icon: '👥',          label: 'Contacts'              },
]

export const ALL_MODULES = [
  ...CORE_MODULES,
  ...MODULE_PACKAGES.map(m => ({
    id: m.id, to: m.to, icon: m.icon, label: m.label, workspace: m.workspace,
  })),
]

export const DEFAULT_SHORTCUTS = ['dashboard', 'tasks', 'chat']

// Read shortcuts from the server-side user object for a specific workspace.
export function getShortcutsForUser(user, workspace = 'personal') {
  const saved = user?.shortcuts?.[workspace]
  if (Array.isArray(saved) && saved.length > 0) {
    const knownIds = new Set(ALL_MODULES.map(m => m.id))
    const valid = saved.filter(id => knownIds.has(id))
    if (valid.length > 0) return valid.slice(0, 4)
  }
  return [...DEFAULT_SHORTCUTS]
}

const PRIORITY_WEIGHTS = { High: 3, Medium: 2, Low: 1 }

// 1:1 port of priority_service.py's score_task() — category_weight (position
// in the user's own category-priority order) × priority_weight + urgency_bonus.
// Ported here (rather than relying solely on the backend's own GET
// /tasks/scored, which is pending/non-goal/own-tasks only) so Tasks.jsx can
// score every task it shows — including household/team assigned tasks and
// done/overdue ones — uniformly. Keep in sync with the Python original if the
// weights ever change; docs/PROJECT.md documents the same formula.
export function scoreTask(task, categoryOrder, todayStr) {
  const total = categoryOrder.length
  const catIdx = categoryOrder.indexOf(task.category || '')
  const catWeight = catIdx === -1 ? 0 : total - catIdx

  const priWeight = PRIORITY_WEIGHTS[task.priority] ?? 1

  let urgency = 0
  if (task.due_date) {
    if (task.due_date < todayStr) urgency = 10
    else if (task.due_date === todayStr) urgency = 5
    else {
      const weekOut = new Date(todayStr)
      weekOut.setDate(weekOut.getDate() + 7)
      const weekOutStr = `${weekOut.getFullYear()}-${String(weekOut.getMonth() + 1).padStart(2, '0')}-${String(weekOut.getDate()).padStart(2, '0')}`
      if (task.due_date <= weekOutStr) urgency = 2
    }
  }

  return catWeight * priWeight + urgency
}
