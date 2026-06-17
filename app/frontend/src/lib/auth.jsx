import { createContext, useContext, useState, useEffect } from 'react'
import { auth as authApi } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lc_user')) } catch { return null }
  })

  function login(token, name, role, disabledModules = []) {
    localStorage.setItem('lc_token', token)
    localStorage.setItem('lc_user', JSON.stringify({ name, role, disabledModules }))
    setUser({ name, role, disabledModules })
  }

  async function logout() {
    try { await authApi.logout() } catch { /* token may already be expired */ }
    localStorage.removeItem('lc_token')
    localStorage.removeItem('lc_user')
    setUser(null)
  }

  // Poll /me every 30 seconds so admin permission changes take effect immediately
  useEffect(() => {
    if (!user) return
    const id = setInterval(async () => {
      try {
        const me = await authApi.me()
        const updated = { ...user, disabledModules: me.disabled_modules || [] }
        localStorage.setItem('lc_user', JSON.stringify(updated))
        setUser(updated)
      } catch {
        // 401 is handled in api.js — it clears storage and redirects to /login
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [user?.name]) // restart only if the logged-in identity changes

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
