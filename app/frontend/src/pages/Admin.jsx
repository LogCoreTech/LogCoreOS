import { useEffect, useState } from 'react'
import { auth as authApi, admin as adminApi } from '../lib/api'
import { ALL_MODULES } from '../lib/constants'

export default function Admin() {
  const [allUsers, setAllUsers] = useState([])
  const [userModules, setUserModules] = useState({})
  const [userTimezones, setUserTimezones] = useState({})
  const [moduleSaving, setModuleSaving] = useState(null)
  const [tzSaving, setTzSaving] = useState(null)
  const [openReg, setOpenReg] = useState(false)
  const [openRegSaving, setOpenRegSaving] = useState(false)
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '' })
  const [addingUser, setAddingUser] = useState(false)
  const [addUserError, setAddUserError] = useState('')
  const [addUserSuccess, setAddUserSuccess] = useState('')
  const [roleSaving, setRoleSaving] = useState(null)

  async function loadUsers() {
    const users = await adminApi.users()
    setAllUsers(users)
    const modMap = {}
    const tzMap = {}
    users.forEach(u => {
      modMap[u.id] = u.disabled_modules || []
      tzMap[u.id] = u.timezone || ''
    })
    setUserModules(modMap)
    setUserTimezones(tzMap)
  }

  useEffect(() => {
    loadUsers().catch(() => {})
    adminApi.getSettings().then(s => setOpenReg(s.allow_open_registration)).catch(() => {})
  }, [])

  function toggleUserModule(userId, moduleId) {
    setUserModules(prev => {
      const cur = prev[userId] || []
      return {
        ...prev,
        [userId]: cur.includes(moduleId)
          ? cur.filter(id => id !== moduleId)
          : [...cur, moduleId],
      }
    })
  }

  async function saveUserModules(userId) {
    setModuleSaving(userId)
    try {
      await adminApi.updateModules(userId, userModules[userId] || [])
    } finally {
      setModuleSaving(null)
    }
  }

  async function saveUserTimezone(userId) {
    setTzSaving(userId)
    try {
      await adminApi.updateUser(userId, { timezone: userTimezones[userId] })
    } catch (e) {
      alert(e.message || 'Invalid timezone')
    } finally {
      setTzSaving(null)
    }
  }

  async function updateRole(userId, role) {
    setRoleSaving(userId)
    try {
      await adminApi.updateRole(userId, role)
      await loadUsers()
    } catch (e) {
      alert(e.message || 'Failed to update role')
    } finally {
      setRoleSaving(null)
    }
  }

  async function toggleOpenReg() {
    const next = !openReg
    setOpenRegSaving(true)
    try {
      await adminApi.updateSettings({ allow_open_registration: next })
      setOpenReg(next)
    } finally {
      setOpenRegSaving(false)
    }
  }

  async function addUser(e) {
    e.preventDefault()
    setAddUserError('')
    setAddUserSuccess('')
    setAddingUser(true)
    try {
      await authApi.register(newUser.email, newUser.password, newUser.name)
      setAddUserSuccess(`${newUser.name} added. They can now sign in.`)
      setNewUser({ name: '', email: '', password: '' })
      await loadUsers()
    } catch (err) {
      setAddUserError(err.message || 'Failed to add user.')
    } finally {
      setAddingUser(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Admin</h1>

      {/* Registration settings */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Registration</h2>
        <div className="flex items-center justify-between py-3">
          <div>
            <p className="text-sm font-medium">Open Registration</p>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
              {openReg ? 'Anyone can create an account.' : 'Only admins can add new users.'}
            </p>
          </div>
          <button
            onClick={toggleOpenReg}
            disabled={openRegSaving}
            className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200 focus:outline-none ${
              openReg ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-600'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 mt-0.5 ${
                openReg ? 'translate-x-5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Add user */}
      <div className="card p-5">
        <h2 className="font-semibold mb-4">Add User</h2>
        <form onSubmit={addUser} className="space-y-3">
          <input
            type="text"
            placeholder="Full name"
            value={newUser.name}
            onChange={e => setNewUser(u => ({ ...u, name: e.target.value }))}
            required
            className="input"
          />
          <input
            type="email"
            placeholder="Email"
            value={newUser.email}
            onChange={e => setNewUser(u => ({ ...u, email: e.target.value }))}
            required
            className="input"
          />
          <input
            type="password"
            placeholder="Password (8+ characters)"
            value={newUser.password}
            onChange={e => setNewUser(u => ({ ...u, password: e.target.value }))}
            required
            minLength={8}
            className="input"
          />
          {addUserError && <p className="text-red-500 text-xs">{addUserError}</p>}
          {addUserSuccess && <p className="text-green-500 text-xs">{addUserSuccess}</p>}
          <button type="submit" disabled={addingUser} className="btn-primary w-full">
            {addingUser ? 'Adding…' : '+ Add User'}
          </button>
        </form>
      </div>

      {/* Per-user management */}
      <div className="card p-5">
        <h2 className="font-semibold mb-4">Users</h2>
        {allUsers.length === 0 ? (
          <p className="text-sm text-charcoal-400 dark:text-charcoal-500">No users yet.</p>
        ) : (
          <div className="space-y-5">
            {allUsers.map(u => (
              <div key={u.id} className="border border-charcoal-100 dark:border-charcoal-800 rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="text-sm font-medium">{u.name}</p>
                    <p className="text-xs text-charcoal-400">{u.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      u.role === 'admin'
                        ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400'
                        : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                    }`}>
                      {u.role}
                    </span>
                    <button
                      onClick={() => updateRole(u.id, u.role === 'admin' ? 'member' : 'admin')}
                      disabled={roleSaving === u.id}
                      className="text-xs text-charcoal-400 hover:text-orange-500 transition-colors"
                      title={u.role === 'admin' ? 'Demote to member' : 'Promote to admin'}
                    >
                      {roleSaving === u.id ? '…' : u.role === 'admin' ? '↓' : '↑'}
                    </button>
                  </div>
                </div>

                {/* Timezone */}
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-1">Timezone</p>
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={userTimezones[u.id] || ''}
                    onChange={e => setUserTimezones(prev => ({ ...prev, [u.id]: e.target.value }))}
                    placeholder="e.g. America/New_York"
                    className="input flex-1 text-sm"
                  />
                  <button
                    onClick={() => saveUserTimezone(u.id)}
                    disabled={tzSaving === u.id}
                    className="btn-primary text-xs px-3 py-1 whitespace-nowrap"
                  >
                    {tzSaving === u.id ? '…' : 'Set TZ'}
                  </button>
                </div>

                {/* Module access — only for non-admins */}
                {u.role !== 'admin' && (
                  <>
                    <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-1">Module access</p>
                    <div className="space-y-1 mb-2">
                      {ALL_MODULES.filter(m => m.id !== 'settings').map(mod => {
                        const disabled = (userModules[u.id] || []).includes(mod.id)
                        return (
                          <label
                            key={mod.id}
                            className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              checked={!disabled}
                              onChange={() => toggleUserModule(u.id, mod.id)}
                              className="accent-orange-500 w-4 h-4"
                            />
                            <span className="text-sm leading-none">{mod.icon}</span>
                            <span className="text-sm">{mod.label}</span>
                          </label>
                        )
                      })}
                    </div>
                    <button
                      onClick={() => saveUserModules(u.id)}
                      disabled={moduleSaving === u.id}
                      className="btn-primary text-xs px-3 py-1 w-full"
                    >
                      {moduleSaving === u.id ? '…' : 'Save Module Access'}
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
