import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const navItems = [
  { to: '/',        icon: '⊞', label: 'Dashboard' },
  { to: '/tasks',   icon: '✓', label: 'Tasks'     },
  { to: '/chat',    icon: '◈', label: 'AI Chat'   },
  { to: '/settings',icon: '⚙', label: 'Settings'  },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-charcoal-50 dark:bg-charcoal-900">

      {/* Sidebar — desktop */}
      <aside className="hidden md:flex flex-col w-56 bg-white dark:bg-charcoal-950 border-r border-charcoal-200 dark:border-charcoal-800">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-charcoal-200 dark:border-charcoal-800">
          <span className="text-orange-500 font-bold text-xl tracking-tight">LogCore</span>
          <span className="text-charcoal-400 dark:text-charcoal-500 text-xs block mt-0.5">
            {user?.name}
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(({ to, icon, label }) => (
            <NavLink
              key={to}
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

        {/* Logout */}
        <div className="p-3 border-t border-charcoal-200 dark:border-charcoal-800">
          <button onClick={handleLogout} className="btn-ghost w-full text-left text-sm">
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <main className="flex-1 overflow-y-auto p-4 md:p-6 pb-24 md:pb-6">
          <Outlet />
        </main>

        {/* Bottom nav — mobile */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white dark:bg-charcoal-950 border-t border-charcoal-200 dark:border-charcoal-800 flex z-50">
          {navItems.map(({ to, icon, label }) => (
            <NavLink
              key={to}
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
        </nav>
      </div>
    </div>
  )
}
