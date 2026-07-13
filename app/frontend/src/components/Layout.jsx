import { useEffect, useRef, useState } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import { ALL_MODULES, getShortcutsForUser } from '../lib/constants'
import { suggestions as sugApi, assets as assetsApi, finance as financeApi } from '../lib/api'

const ADMIN_NAV = { to: '/admin', icon: '⬡', label: 'Admin' }

function NotifBell() {
  const [notifs, setNotifs] = useState([])
  const [open, setOpen] = useState(false)
  const panelRef = useRef(null)
  const navigate = useNavigate()
  const { workspace, switchWorkspace } = useWorkspace()

  // Navigation actions rendered as a View → button. open_inbox may need a
  // workspace switch first (e.g. business inbox ping while in personal).
  function navTarget(action) {
    if (action?.type === 'open_asset') return `/assets?asset=${action.asset_id}`
    if (action?.type === 'open_inbox') return `/automations?view=inbox&inbox=${action.inbox_id || ''}`
    if (action?.type === 'open_admin_banking') return '/admin'
    if (action?.type === 'open_finance_book') return `/finance?book=${action.book_id || ''}`
    return null
  }

  function openTarget(n) {
    markRead(n.id)
    setOpen(false)
    if (n.action.type === 'open_inbox' && n.action.workspace && n.action.workspace !== workspace) {
      switchWorkspace(n.action.workspace)
    }
    navigate(navTarget(n.action))
  }

  function load() {
    // Guard against a non-array response (e.g. an error object) — `list || []`
    // would keep a truthy object and crash notifs.filter below.
    sugApi.notifications().then(list => setNotifs(Array.isArray(list) ? list : [])).catch(() => {})
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])

  // Close panel when clicking outside
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const unread = (Array.isArray(notifs) ? notifs : []).filter(n => !n.read).length

  function markRead(id) {
    sugApi.markRead(id).catch(() => {})
    setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n))
  }

  async function respond(n, accept) {
    // Optimistically resolve the request notification
    setNotifs(prev => prev.map(x => x.id === n.id ? { ...x, status: 'resolved', read: true } : x))
    try {
      if (n.action?.type === 'finance_share') await financeApi.respondShare(n.id, accept)
      else await assetsApi.respondShare(n.id, accept)
    } catch { /* keep resolved locally */ }
    load()
  }

  function clearAll() {
    sugApi.clearAll().catch(() => {})
    setNotifs(prev => prev.map(n => ({ ...n, read: true })))
    setOpen(false)
  }

  function fmt(iso) {
    try {
      const d = new Date(iso)
      const now = new Date()
      const diff = Math.floor((now - d) / 60000)
      if (diff < 1) return 'just now'
      if (diff < 60) return `${diff}m ago`
      if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
      return d.toLocaleDateString()
    } catch { return '' }
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(o => !o)}
        className="relative p-1.5 rounded-lg text-charcoal-500 dark:text-charcoal-400 hover:text-orange-500 hover:bg-charcoal-100 dark:hover:bg-charcoal-800 transition-colors"
        title="Notifications"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-3.5 px-0.5 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center leading-none">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 md:right-auto md:left-0 top-full mt-2 w-80 max-h-[420px] bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-2xl shadow-xl z-50 flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-charcoal-200 dark:border-charcoal-700">
            <span className="text-sm font-semibold">Notifications</span>
            {notifs.some(n => !n.read) && (
              <button onClick={clearAll} className="text-xs text-charcoal-400 hover:text-orange-500 transition-colors">
                Mark all read
              </button>
            )}
          </div>
          <div className="overflow-y-auto flex-1">
            {notifs.length === 0 ? (
              <p className="text-xs text-charcoal-400 dark:text-charcoal-500 text-center py-6">No notifications yet</p>
            ) : (
              notifs.map(n => (
                <div
                  key={n.id}
                  onClick={() => markRead(n.id)}
                  className={`px-4 py-3 border-b border-charcoal-100 dark:border-charcoal-800 last:border-0 cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors ${n.read ? 'opacity-60' : ''}`}
                >
                  <div className="flex items-start gap-2">
                    {!n.read && <div className="w-1.5 h-1.5 rounded-full bg-orange-500 mt-1.5 shrink-0" />}
                    <div className={!n.read ? '' : 'pl-3.5'}>
                      <p className="text-xs font-semibold text-charcoal-800 dark:text-charcoal-100">{n.title}</p>
                      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5 line-clamp-2">{n.body}</p>
                      {navTarget(n.action) ? (
                        // Navigation action — always available (re-viewable, no resolve)
                        <div className="flex gap-2 mt-1.5" onClick={e => e.stopPropagation()}>
                          <button
                            onClick={() => openTarget(n)}
                            className="btn-primary text-[11px] px-2.5 py-1"
                          >
                            View →
                          </button>
                          <span className="text-[10px] text-charcoal-400 dark:text-charcoal-500 self-center">{fmt(n.created_at)}</span>
                        </div>
                      ) : n.action && n.status !== 'resolved' ? (
                        <div className="flex gap-2 mt-1.5" onClick={e => e.stopPropagation()}>
                          <button onClick={() => respond(n, true)} className="btn-primary text-[11px] px-2.5 py-1">Accept</button>
                          <button onClick={() => respond(n, false)} className="btn-ghost text-[11px] px-2.5 py-1">Decline</button>
                        </div>
                      ) : (
                        <p className="text-[10px] text-charcoal-400 dark:text-charcoal-500 mt-1">
                          {n.action ? '✓ handled · ' : ''}{fmt(n.created_at)}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { user, logout, refreshUser } = useAuth()
  const { workspace, switchWorkspace } = useWorkspace()
  const navigate = useNavigate()
  const location = useLocation()
  const [showDrawer, setShowDrawer] = useState(false)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('lc_sidebar') === 'collapsed')

  const userWorkspaces = user?.workspaces || ['personal']
  const hasMultipleWorkspaces = userWorkspaces.length > 1

  // Auto-switch to first allowed workspace if current one isn't in the user's list
  useEffect(() => {
    if (userWorkspaces.length > 0 && !userWorkspaces.includes(workspace)) {
      switchWorkspace(userWorkspaces[0])
    }
  }, [userWorkspaces.join(','), workspace])

  // Re-fetch /me whenever workspace changes so disabled_modules reflects the new workspace.
  // Also redirect to dashboard if the current page is restricted to the other workspace.
  useEffect(() => {
    if (user) refreshUser()
    const currentModule = ALL_MODULES.find(m => m.to && (m.to === '/' ? location.pathname === '/' : location.pathname.startsWith(m.to)))
    if (currentModule?.workspace && currentModule.workspace !== workspace) {
      navigate('/')
    }
  }, [workspace])

  function toggleSidebar() {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem('lc_sidebar', next ? 'collapsed' : 'expanded')
  }

  const disabledIds = new Set(user?.disabledModules || [])
  const visibleModules = ALL_MODULES.filter(m =>
    m.nav !== false && m.to && !disabledIds.has(m.id) &&
    (!m.workspace || m.workspace === workspace)
  )

  // Shortcuts flow from the server-side user object — reactive to workspace + user changes
  const shortcutModules = getShortcutsForUser(user, workspace)
    .map(id => ALL_MODULES.find(m => m.id === id))
    .filter(m => m && !disabledIds.has(m.id))

  function navTo(to) {
    navigate(to)
    setShowDrawer(false)
  }

  return (
    <div className="flex h-[100dvh] overflow-hidden">

      {/* Sidebar — desktop only */}
      <aside className={`hidden md:flex flex-col bg-white dark:bg-charcoal-950 border-r border-charcoal-200 dark:border-charcoal-800 transition-all duration-200 ${collapsed ? 'w-14' : 'w-56'}`}>
        <div className={`border-b border-charcoal-200 dark:border-charcoal-800 ${collapsed ? 'px-2 py-3 flex flex-col items-center gap-2' : 'px-5 py-5 flex items-start justify-between'}`}>
          {collapsed ? (
            <>
              <span className="text-orange-500 font-bold text-xl">LC</span>
              <NotifBell />
            </>
          ) : (
            <>
              <div>
                <span className="text-orange-500 font-bold text-xl tracking-tight">LogCore</span>
                <span className="text-charcoal-400 dark:text-charcoal-500 text-xs block mt-0.5">{user?.name}</span>
              </div>
              <NotifBell />
            </>
          )}
        </div>

        {/* Workspace toggle pill — only when user has multiple workspaces */}
        {hasMultipleWorkspaces && !collapsed && (
          <div className="flex gap-1 p-2 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 mx-2 mt-2">
            {userWorkspaces.map(w => (
              <button
                key={w}
                onClick={() => switchWorkspace(w)}
                className={`flex-1 py-1 rounded text-xs capitalize transition-colors ${
                  workspace === w
                    ? 'bg-white dark:bg-charcoal-700 shadow font-semibold text-charcoal-900 dark:text-charcoal-100'
                    : 'text-charcoal-500 dark:text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200'
                }`}
              >
                {w}
              </button>
            ))}
          </div>
        )}
        {hasMultipleWorkspaces && collapsed && (
          <div className="flex flex-col gap-1 px-1 mt-2">
            {userWorkspaces.map(w => (
              <button
                key={w}
                onClick={() => switchWorkspace(w)}
                title={w}
                className={`py-1 rounded text-[10px] capitalize transition-colors ${
                  workspace === w
                    ? 'bg-orange-500 text-white font-semibold'
                    : 'text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200'
                }`}
              >
                {w[0].toUpperCase()}
              </button>
            ))}
          </div>
        )}

        <nav className="flex-1 p-2 space-y-0.5">
          {visibleModules.map(({ id, to, icon, label }) => (
            <NavLink
              key={id}
              to={to}
              end={to === '/'}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors border-l-2 rounded-r-lg ${
                  isActive
                    ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                    : 'border-transparent text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
                } ${collapsed ? 'justify-center' : ''}`
              }
            >
              <span className="text-base shrink-0">{icon}</span>
              {!collapsed && label}
            </NavLink>
          ))}
        </nav>

        <div className="p-2 border-t border-charcoal-200 dark:border-charcoal-800 space-y-0.5">
          {user?.role === 'admin' && (
            <NavLink
              to="/admin"
              title={collapsed ? 'Admin' : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors border-l-2 rounded-r-lg ${
                  isActive
                    ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                    : 'border-transparent text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
                } ${collapsed ? 'justify-center' : ''}`
              }
            >
              <span className="text-base shrink-0">🛡</span>
              {!collapsed && 'Admin'}
            </NavLink>
          )}
          <NavLink
            to="/settings"
            title={collapsed ? 'Settings' : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors border-l-2 rounded-r-lg ${
                isActive
                  ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                  : 'border-transparent text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
              } ${collapsed ? 'justify-center' : ''}`
            }
          >
            <span className="text-base shrink-0">⚙</span>
            {!collapsed && 'Settings'}
          </NavLink>
          <button
            onClick={logout}
            title={collapsed ? 'Sign out' : undefined}
            className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-r-lg border-l-2 border-transparent ${collapsed ? 'justify-center' : ''}`}
          >
            <span className="text-base shrink-0">→</span>
            {!collapsed && 'Sign out'}
          </button>
          <button
            onClick={toggleSidebar}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="w-full flex items-center justify-center py-2 text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 transition-colors text-xs"
          >
            {collapsed ? '›' : '‹'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile-only top bar with brand + bell */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white dark:bg-charcoal-950 border-b border-charcoal-200 dark:border-charcoal-800 shrink-0">
          <span className="text-orange-500 font-bold text-xl tracking-tight">LogCore</span>
          <NotifBell />
        </header>

        <main className="flex-1 min-h-0 overflow-y-scroll overflow-x-hidden p-4 md:p-6 flex flex-col">
          <Outlet />
        </main>

        {/* Bottom bar — mobile: pinned shortcuts + More button */}
        <nav className="md:hidden shrink-0 bg-white dark:bg-charcoal-950 border-t border-charcoal-200 dark:border-charcoal-800 flex z-40 pb-[env(safe-area-inset-bottom)]">
          {shortcutModules.map(({ id, to, icon, label }) => (
            <NavLink
              key={id}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex-1 flex flex-col items-center py-2 text-xs gap-0.5 transition-colors ${
                  isActive
                    ? 'text-orange-500'
                    : 'text-charcoal-500 dark:text-charcoal-400'
                }`
              }
            >
              <span className="text-lg leading-none">{icon}</span>
              {label}
            </NavLink>
          ))}

          {/* More button */}
          <button
            onClick={() => setShowDrawer(true)}
            className="flex-1 flex flex-col items-center py-2 text-xs gap-0.5 text-charcoal-500 dark:text-charcoal-400"
          >
            <span className="text-lg leading-none">⋯</span>
            More
          </button>
        </nav>
      </div>

      {/* Module drawer — slides up from bottom on mobile */}
      {showDrawer && (
        <>
          <div
            className="fixed inset-0 bg-black/50 z-50 md:hidden"
            onClick={() => setShowDrawer(false)}
          />
          <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-charcoal-950 z-50 md:hidden rounded-t-2xl shadow-xl">
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <h3 className="font-semibold text-base">All Modules</h3>
              <button
                onClick={() => setShowDrawer(false)}
                className="text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-xl leading-none"
              >
                ✕
              </button>
            </div>

            {/* Drag handle hint */}
            <div className="flex justify-center -mt-3 mb-2">
              <div className="w-10 h-1 rounded-full bg-charcoal-200 dark:bg-charcoal-700" />
            </div>

            {/* Workspace switcher — mobile */}
            {hasMultipleWorkspaces && (
              <div className="flex gap-1 mx-5 mb-4 p-1 rounded-lg bg-charcoal-100 dark:bg-charcoal-800">
                {userWorkspaces.map(w => (
                  <button
                    key={w}
                    onClick={() => { switchWorkspace(w); setShowDrawer(false) }}
                    className={`flex-1 py-1.5 rounded text-xs capitalize font-medium transition-colors ${
                      workspace === w
                        ? 'bg-white dark:bg-charcoal-700 shadow text-charcoal-900 dark:text-charcoal-100'
                        : 'text-charcoal-500 dark:text-charcoal-400'
                    }`}
                  >
                    {w}
                  </button>
                ))}
              </div>
            )}

            <div className="grid grid-cols-3 gap-3 px-5 pb-4">
              {visibleModules.map(({ id, to, icon, label }) => (
                <button
                  key={id}
                  onClick={() => navTo(to)}
                  className="flex flex-col items-center gap-2 p-4 rounded-xl bg-charcoal-50 dark:bg-charcoal-800 hover:bg-orange-50 dark:hover:bg-orange-900/20 active:scale-95 transition-all"
                >
                  <span className="text-2xl leading-none">{icon}</span>
                  <span className="text-xs font-medium text-charcoal-700 dark:text-charcoal-300">{label}</span>
                </button>
              ))}
            </div>

            <div className="p-3 border-t border-charcoal-200 dark:border-charcoal-800 space-y-1">
              {user?.role === 'admin' && (
                <button
                  onClick={() => navTo('/admin')}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800 transition-colors"
                >
                  <span className="text-base">🛡</span>
                  Admin
                </button>
              )}
              <button
                onClick={() => navTo('/settings')}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800 transition-colors"
              >
                <span className="text-base">⚙</span>
                Settings
              </button>
              <button
                onClick={() => { setShowDrawer(false); logout() }}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <span className="text-base">→</span>
                Sign out
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
