import { createContext, useContext, useState } from 'react'
import { auth as authApi } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lc_user')) } catch { return null }
  })

  function login(id, name, role) {
    localStorage.setItem('lc_user', JSON.stringify({ id, name, role }))
    setUser({ id, name, role })
  }

  async function logout() {
    try { await authApi.logout() } catch { /* cookie cleared server-side; ignore errors */ }
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
