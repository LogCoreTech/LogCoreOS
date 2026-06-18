import { createContext, useContext, useState, useEffect } from 'react'
import { auth as authApi } from './api'

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

  // On mount, verify the cookie session is still valid
  useEffect(() => {
    authApi.me()
      .then(me => {
        const u = {
          name:            me.name,
          role:            me.role,
          disabledModules: me.disabled_modules || [],
          timezone:        me.timezone || 'UTC',
        }
        localStorage.setItem('lc_user', JSON.stringify(u))
        setUser(u)
      })
      .catch(() => {
        // Cookie expired or absent — clear stale localStorage and let the app redirect
        localStorage.removeItem('lc_user')
        setUser(null)
      })
      .finally(() => setSessionChecked(true))
  }, [])

  function login(name, role, disabledModules = [], timezone = 'UTC') {
    // Auth is handled via httpOnly cookie set by the server.
    // Only cache non-sensitive user metadata in localStorage.
    const u = { name, role, disabledModules, timezone }
    localStorage.setItem('lc_user', JSON.stringify(u))
    setUser(u)
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
    const id = setInterval(async () => {
      try {
        const me = await authApi.me()
        const updated = {
          ...user,
          disabledModules: me.disabled_modules || [],
          timezone: me.timezone || user.timezone,
        }
        localStorage.setItem('lc_user', JSON.stringify(updated))
        setUser(updated)
      } catch {
        // 401 handled in api.js — clears storage and redirects to /login
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [user?.name])

  // Don't render children until the initial session check completes (avoids flash)
  if (!sessionChecked) return null

  return (
    <AuthContext.Provider value={{ user, login, logout, updateUserField }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
