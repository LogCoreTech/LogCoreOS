import { createContext, useContext, useState, useEffect } from 'react'
import { auth as authApi } from './api'

const AuthContext = createContext(null)

function _detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lc_user')) } catch { return null }
  })

  function login(token, name, role, disabledModules = [], timezone = 'UTC') {
    localStorage.setItem('lc_token', token)
    localStorage.setItem('lc_user', JSON.stringify({ name, role, disabledModules, timezone }))
    setUser({ name, role, disabledModules, timezone })
  }

  async function logout() {
    try { await authApi.logout() } catch { /* token may already be expired */ }
    localStorage.removeItem('lc_token')
    localStorage.removeItem('lc_user')
    setUser(null)
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
  }, [user?.name]) // runs once per login session

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
        // 401 is handled in api.js — it clears storage and redirects to /login
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [user?.name])

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
