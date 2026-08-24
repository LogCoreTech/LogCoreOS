import { createContext, useContext, useState, useEffect } from 'react'
import { auth as authApi, modStore as modStoreApi } from './api'
import { applyAccentColor, applyDarkMode, applyBackground, applyDensity, applyCornerStyle, getSystemDarkPreference } from './theme'
import DemoBanner from '../components/DemoBanner'

const AuthContext = createContext(null)

function _detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' }
}

export function AuthProvider({ children }) {
  // Cached user metadata (not the token — that lives in the httpOnly cookie)
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lc_user')) } catch { return null }
  })
  const [sessionChecked, setSessionChecked] = useState(false)
  const [demoMode, setDemoMode] = useState(false)
  // Which module_packages/ modules are actually registered in the CURRENT
  // backend process — distinct from user.disabledModules (which reflects the
  // installed_modules.json marker live, even before a pending restart has
  // picked it up). Nav/routing for a converted module must gate on this, not
  // just disabledModules, or a just-installed-not-yet-restarted module would
  // show as reachable while its router still 404s. Empty array is the
  // correct default before the first fetch resolves — no converted module
  // is falsely treated as active.
  const [activeModuleIds, setActiveModuleIds] = useState([])

  async function refreshActiveModules() {
    try {
      const { active } = await modStoreApi.active()
      setActiveModuleIds(active || [])
    } catch {
      // Same philosophy as refreshUser()'s catch — a transient failure here
      // must not eject any module a user was already using; the next poll
      // (30s, same cadence as refreshUser) will pick up the real state.
    }
  }

  // Instance-wide, not user-specific — fetched once regardless of login
  // state (the public /auth/status endpoint), so the banner shows on the
  // login screen too, not just once inside the app.
  useEffect(() => {
    authApi.status().then(s => setDemoMode(!!s.demo_mode)).catch(() => {})
  }, [])

  async function refreshUser() {
    try {
      const me = await authApi.me()
      const u = {
        id:              me.id,
        name:            me.name,
        role:            me.role,
        disabledModules: me.disabled_modules || [],
        poolEdit:        me.pool_edit     || [],
        timezone:        me.timezone     || 'UTC',
        workspaces:      me.workspaces   || ['personal'],
        accentColor:     me.accent_color || null,
        darkMode:        me.dark_mode    || 'system',
        background:      me.background   || null,
        density:         me.density      || 'comfortable',
        cornerStyle:     me.corner_style || 'rounded',
        shortcuts:       me.shortcuts    || {},
        defaultDashboardId: me.default_dashboard_id || {},
      }
      // Persist theme prefs too so the pre-React FOUC script in main.jsx can
      // apply the real background/accent before first paint (otherwise the
      // background flashes the default until /me resolves).
      localStorage.setItem('lc_user', JSON.stringify({
        id: u.id, name: u.name, role: u.role,
        disabledModules: u.disabledModules, timezone: u.timezone,
        workspaces: u.workspaces,
        accentColor: u.accentColor, darkMode: u.darkMode, background: u.background,
        density: u.density, cornerStyle: u.cornerStyle,
      }))
      setUser(u)
      applyAccentColor(u.accentColor)
      applyDarkMode(u.darkMode, getSystemDarkPreference())
      applyBackground(u.background)
      applyDensity(u.density)
      applyCornerStyle(u.cornerStyle)
    } catch {
      // A genuine 401 is handled inside request('/auth/me') (clears storage +
      // redirects to /login). A transient failure (network blip, backend
      // restart) must NOT eject the user or churn the theme — keep the session.
    }
  }

  // On mount, verify the cookie session is still valid
  useEffect(() => {
    Promise.all([refreshUser(), refreshActiveModules()]).finally(() => setSessionChecked(true))
  }, [])

  function login(id, name, role, disabledModules = [], timezone = 'UTC', accentColor = null, darkMode = 'system', background = null, density = 'comfortable', cornerStyle = 'rounded', workspaces = ['personal']) {
    // Auth is handled via httpOnly cookie set by the server.
    // Only persist session/routing fields — preferences come from server and stay in memory only.
    const u = { id, name, role, disabledModules, timezone, workspaces, accentColor, darkMode, background, density, cornerStyle }
    localStorage.setItem('lc_user', JSON.stringify({
      id, name, role, disabledModules, timezone, workspaces,
      accentColor, darkMode, background, density, cornerStyle,
    }))
    setUser(u)
    applyAccentColor(accentColor)
    applyDarkMode(darkMode, getSystemDarkPreference())
    applyBackground(background)
    applyDensity(density)
    applyCornerStyle(cornerStyle)
  }

  async function logout() {
    try { await authApi.logout() } catch { /* cookie may already be expired */ }
    localStorage.removeItem('lc_user')
    setUser(null)
    // Reset theme to auth-page defaults so the login page is clean immediately
    // (otherwise the signed-out user's background/accent linger until a reload).
    applyBackground(null)
    applyAccentColor(null)
    applyDarkMode('system', getSystemDarkPreference())
    applyDensity('comfortable')
    applyCornerStyle('rounded')
  }

  function updateUserField(key, value) {
    setUser(prev => {
      if (!prev) return prev
      const updated = { ...prev, [key]: value }
      localStorage.setItem('lc_user', JSON.stringify(updated))
      return updated
    })
  }

  // Auto-sync timezone to the device's detected zone if the user has opted in.
  // Deliberately keyed on user?.name (identity), not the full `user` object:
  // this effect calls setUser() itself, and the full object also changes on
  // every unrelated profile field update (theme, accent color, ...) — neither
  // should re-trigger this check.
  useEffect(() => {
    if (!user) return
    if (localStorage.getItem('lc_auto_tz') !== 'true') return
    const detected = _detectTz()
    if (detected && detected !== user.timezone) {
      authApi.updateMe({ timezone: detected })
        .then(() => {
          const updated = { ...user, timezone: detected }
          localStorage.setItem('lc_user', JSON.stringify(updated))
          setUser(updated)
        })
        .catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.name])

  // Poll /me every 30 seconds so admin permission changes take effect live —
  // active modules on the same cadence, so a Restart Now elsewhere is picked
  // up without a manual reload. Keyed on user?.name so the interval is only
  // torn down/recreated when the logged-in identity changes, not on every
  // unrelated `user` field update.
  useEffect(() => {
    if (!user) return
    const id = setInterval(() => {
      refreshUser()
      refreshActiveModules()
    }, 30_000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.name])

  // Don't render children until the initial session check completes (avoids flash)
  if (!sessionChecked) return (
    <div className="min-h-screen flex items-center justify-center bg-charcoal-50 dark:bg-charcoal-900">
      <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  return (
    <AuthContext.Provider value={{ user, login, logout, updateUserField, refreshUser, demoMode, activeModuleIds, refreshActiveModules }}>
      {demoMode && <DemoBanner />}
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
