import { createContext, useContext, useState, useEffect } from 'react'
import { auth as authApi } from './api'
import { applyAccentColor, applyDarkMode, applyBackground, applyDensity, applyCornerStyle, getSystemDarkPreference } from './theme'

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

  async function refreshUser() {
    try {
      const me = await authApi.me()
      const u = {
        id:              me.id,
        name:            me.name,
        role:            me.role,
        disabledModules: me.disabled_modules || [],
        timezone:        me.timezone     || 'UTC',
        workspaces:      me.workspaces   || ['personal'],
        accentColor:     me.accent_color || null,
        darkMode:        me.dark_mode    || 'system',
        background:      me.background   || null,
        density:         me.density      || 'comfortable',
        cornerStyle:     me.corner_style || 'rounded',
        shortcuts:       me.shortcuts    || {},
      }
      localStorage.setItem('lc_user', JSON.stringify({
        id: u.id, name: u.name, role: u.role,
        disabledModules: u.disabledModules, timezone: u.timezone,
        workspaces: u.workspaces,
      }))
      setUser(u)
      applyAccentColor(u.accentColor)
      applyDarkMode(u.darkMode, getSystemDarkPreference())
      applyBackground(u.background)
      applyDensity(u.density)
      applyCornerStyle(u.cornerStyle)
    } catch {
      localStorage.removeItem('lc_user')
      setUser(null)
    }
  }

  // On mount, verify the cookie session is still valid
  useEffect(() => {
    refreshUser().finally(() => setSessionChecked(true))
  }, [])

  function login(id, name, role, disabledModules = [], timezone = 'UTC', accentColor = null, darkMode = 'system', background = null, density = 'comfortable', cornerStyle = 'rounded', workspaces = ['personal']) {
    // Auth is handled via httpOnly cookie set by the server.
    // Only persist session/routing fields — preferences come from server and stay in memory only.
    const u = { id, name, role, disabledModules, timezone, workspaces, accentColor, darkMode, background, density, cornerStyle }
    localStorage.setItem('lc_user', JSON.stringify({ id, name, role, disabledModules, timezone, workspaces }))
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
  }

  function updateUserField(key, value) {
    setUser(prev => {
      if (!prev) return prev
      const updated = { ...prev, [key]: value }
      localStorage.setItem('lc_user', JSON.stringify(updated))
      return updated
    })
  }

  // Auto-sync timezone to the device's detected zone if the user has opted in
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
  }, [user?.name])

  // Poll /me every 30 seconds so admin permission changes take effect live
  useEffect(() => {
    if (!user) return
    const id = setInterval(() => refreshUser(), 30_000)
    return () => clearInterval(id)
  }, [user?.name])

  // Don't render children until the initial session check completes (avoids flash)
  if (!sessionChecked) return (
    <div className="min-h-screen flex items-center justify-center bg-charcoal-50 dark:bg-charcoal-900">
      <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  return (
    <AuthContext.Provider value={{ user, login, logout, updateUserField, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
