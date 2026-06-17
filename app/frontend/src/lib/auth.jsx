import { createContext, useContext, useState } from 'react'
import { auth as authApi } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lc_user')) } catch { return null }
  })

  function login(token, name, role) {
    localStorage.setItem('lc_token', token)
    localStorage.setItem('lc_user', JSON.stringify({ name, role }))
    setUser({ name, role })
  }

  async function logout() {
    try { await authApi.logout() } catch { /* token may already be expired */ }
    localStorage.removeItem('lc_token')
    localStorage.removeItem('lc_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
