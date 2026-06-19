import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { ALL_MODULES, getShortcuts } from '../lib/constants'

const ADMIN_NAV = { to: '/admin', icon: '⬡', label: 'Admin' }

export default function Layout() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [shortcuts, setShortcuts] = useState(getShortcuts)
  const [showDrawer, setShowDrawer] = useState(false)

  // Re-read shortcuts when Settings saves them
  useEffect(() => {
    function refresh() { setShortcuts(getShortcuts()) }
    window.addEventListener('lc_shortcuts_changed', refresh)
    return () => window.removeEventListener('lc_shortcuts_changed', refresh)
  }, [])

  const disabledIds = new Set(user?.disabledModules || [])
  const visibleModules = ALL_MODULES.filter(m => !disabledIds.has(m.id))

  const shortcutModules = shortcuts
    .map(id => ALL_MODULES.find(m => m.id === id))
    .filter(m => m && !disabledIds.has(m.id))

  function navTo(to) {
    navigate(to)
    setShowDrawer(false)
  }

  return (
    <div className="flex h-screen overflow-hidden bg-charcoal-50 dark:bg-charcoal-900">

      {/* Sidebar — desktop only, always shows all modules */}
      <aside className="hidden md:flex flex-col w-56 bg-white dark:bg-charcoal-950 border-r border-charcoal-200 dark:border-charcoal-800">
        <div className="px-5 py-5 border-b border-charcoal-200 dark:border-charcoal-800">
          <span className="text-orange-500 font-bold text-xl tracking-tight">LogCore</span>
          <span className="text-charcoal-400 dark:text-charcoal-500 text-xs block mt-0.5">
            {user?.name}
          </span>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {visibleModules.map(({ id, to, icon, label }) => (
            <NavLink
              key={id}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-orange-500 text-white'
                    : 'text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
                }`
              }
            >
              <span className="text-base">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-charcoal-200 dark:border-charcoal-800 space-y-1">
          {user?.role === 'admin' && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-orange-500 text-white'
                    : 'text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
                }`
              }
            >
              <span className="text-base">🛡</span>
              Admin
            </NavLink>
          )}
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-orange-500 text-white'
                  : 'text-charcoal-600 dark:text-charcoal-400 hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
              }`
            }
          >
            <span className="text-base">⚙</span>
            Settings
          </NavLink>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <main className="flex-1 overflow-y-auto p-4 md:p-6 pb-24 md:pb-6">
          <Outlet />
        </main>

        {/* Bottom bar — mobile: pinned shortcuts + More button */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white dark:bg-charcoal-950 border-t border-charcoal-200 dark:border-charcoal-800 flex z-40">
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
            </div>
          </div>
        </>
      )}
    </div>
  )
}
