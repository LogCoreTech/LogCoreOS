import { useEffect, useState } from 'react'
import { priorities as prioritiesApi, auth as authApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useNavigate } from 'react-router-dom'
import { ALL_MODULES, getShortcuts, saveShortcuts } from '../lib/constants'
import { admin as adminApi } from '../lib/api'

const BASE_CATS = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']

const SESSION_OPTIONS = [
  { label: '1 day',   value: 1440   },
  { label: '7 days',  value: 10080  },
  { label: '30 days', value: 43200  },
  { label: '90 days', value: 129600 },
]

export default function Settings() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [order, setOrder] = useState([])
  const [profileOrder, setProfileOrder] = useState([])
  const [customCat, setCustomCat] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [ntfyChannel, setNtfyChannel] = useState('')
  const [sessionMinutes, setSessionMinutes] = useState(10080)
  const [shortcutIds, setShortcutIds] = useState(getShortcuts)
  const [shortcutDragIdx, setShortcutDragIdx] = useState(null)
  const [shortcutSaved, setShortcutSaved] = useState(false)
  const [allUsers, setAllUsers] = useState([])
  const [userModules, setUserModules] = useState({})   // { userId: [disabledId, ...] }
  const [moduleSaving, setModuleSaving] = useState(null)
  const [openReg, setOpenReg] = useState(false)
  const [openRegSaving, setOpenRegSaving] = useState(false)
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '' })
  const [addingUser, setAddingUser] = useState(false)
  const [addUserError, setAddUserError] = useState('')
  const [addUserSuccess, setAddUserSuccess] = useState('')

  useEffect(() => {
    const fetches = [prioritiesApi.get(), authApi.me()]
    Promise.all(fetches).then(([p, me]) => {
      setOrder(p.order || [])
      setProfileOrder(p.profile_order || [])
      setNtfyChannel(me.notification_channel || '')
      setSessionMinutes(me.session_minutes || 10080)
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (user?.role !== 'admin') return
    adminApi.users().then(users => {
      setAllUsers(users)
      const map = {}
      users.forEach(u => { map[u.id] = u.disabled_modules || [] })
      setUserModules(map)
    }).catch(() => {})
    adminApi.getSettings().then(s => setOpenReg(s.allow_open_registration)).catch(() => {})
  }, [user?.role])

  function addCustom() {
    const v = customCat.trim()
    if (v && !order.includes(v)) { setOrder([...order, v]); setCustomCat('') }
  }

  function removeCustom(cat) {
    if (BASE_CATS.includes(cat)) return
    setOrder(order.filter(c => c !== cat))
  }

  function onDragStart(i) { setDragIdx(i) }
  function onDragOver(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) return
    const next = [...order]
    const [m] = next.splice(dragIdx, 1)
    next.splice(i, 0, m)
    setOrder(next)
    setDragIdx(i)
  }
  function onDragEnd() { setDragIdx(null) }

  function flash() {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function savePriorities() {
    await prioritiesApi.override(order)
    flash()
  }

  async function saveSession() {
    try {
      await authApi.updateSession(sessionMinutes)
      flash()
    } catch (e) {
      console.error('Failed to save session length:', e)
    }
  }

  function toggleShortcut(id) {
    if (shortcutIds.includes(id)) {
      setShortcutIds(shortcutIds.filter(s => s !== id))
    } else if (shortcutIds.length < 4) {
      setShortcutIds([...shortcutIds, id])
    }
  }

  function onShortcutDragStart(i) { setShortcutDragIdx(i) }
  function onShortcutDragOver(e, i) {
    e.preventDefault()
    if (shortcutDragIdx === null || shortcutDragIdx === i) return
    const next = [...shortcutIds]
    const [m] = next.splice(shortcutDragIdx, 1)
    next.splice(i, 0, m)
    setShortcutIds(next)
    setShortcutDragIdx(i)
  }
  function onShortcutDragEnd() { setShortcutDragIdx(null) }

  function saveShortcutsHandler() {
    saveShortcuts(shortcutIds)
    setShortcutSaved(true)
    setTimeout(() => setShortcutSaved(false), 2000)
  }

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

  async function addUser(e) {
    e.preventDefault()
    setAddUserError('')
    setAddUserSuccess('')
    setAddingUser(true)
    try {
      await authApi.register(newUser.email, newUser.password, newUser.name)
      setAddUserSuccess(`${newUser.name} added. They can now sign in.`)
      setNewUser({ name: '', email: '', password: '' })
      // Refresh user list
      const users = await adminApi.users()
      setAllUsers(users)
      const map = {}
      users.forEach(u => { map[u.id] = u.disabled_modules || [] })
      setUserModules(map)
    } catch (err) {
      setAddUserError(err.message || 'Failed to add user.')
    } finally {
      setAddingUser(false)
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

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Profile */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Profile</h2>
        <div className="text-sm space-y-1 text-charcoal-700 dark:text-charcoal-300">
          <p><span className="text-charcoal-500">Name:</span> {user?.name}</p>
          <p><span className="text-charcoal-500">Role:</span> {user?.role}</p>
        </div>
      </div>

      {/* Priority order */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Life Priority Order</h2>
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          This sets today's priority override. Your profile default is: {profileOrder.join(' → ')}
        </p>

        {loading ? (
          <div className="space-y-2">{[1,2,3].map(i=><div key={i} className="h-10 bg-charcoal-100 dark:bg-charcoal-700 rounded animate-pulse"/>)}</div>
        ) : (
          <>
            <ul className="space-y-2 mb-4">
              {order.map((cat, i) => (
                <li
                  key={cat}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={e => onDragOver(e, i)}
                  onDragEnd={onDragEnd}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                    dragIdx === i
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                  }`}
                >
                  <span className="text-charcoal-400 text-xs w-4">{i+1}</span>
                  <span className="flex-1 text-sm">{cat}</span>
                  {!BASE_CATS.includes(cat) && (
                    <button onClick={() => removeCustom(cat)} className="text-charcoal-400 hover:text-red-500 text-xs">✕</button>
                  )}
                  <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
                </li>
              ))}
            </ul>

            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={customCat}
                onChange={e => setCustomCat(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCustom()}
                placeholder="Add category…"
                className="input"
              />
              <button onClick={addCustom} className="btn-primary px-3">+</button>
            </div>

            <button onClick={savePriorities} className="btn-primary w-full">
              Apply Today's Order
            </button>
          </>
        )}
      </div>

      {/* Notifications */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Notifications (ntfy)</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Install the <strong>ntfy</strong> app on your phone and subscribe to your personal channel to receive morning digests and alerts.
        </p>
        {ntfyChannel ? (
          <div>
            <label className="block text-sm font-medium mb-1">Your ntfy channel</label>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-charcoal-100 dark:bg-charcoal-700 text-sm px-3 py-2 rounded-lg font-mono break-all">
                {ntfyChannel}
              </code>
              <button
                onClick={() => navigator.clipboard?.writeText(ntfyChannel)}
                className="text-xs text-charcoal-500 hover:text-orange-500 whitespace-nowrap"
              >
                Copy
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-charcoal-500">Channel loading…</p>
        )}
      </div>

      {/* Session length */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Session Length</h2>
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          How long you stay signed in before needing to log in again.
        </p>
        <div className="flex gap-2">
          <select
            value={sessionMinutes}
            onChange={e => setSessionMinutes(Number(e.target.value))}
            className="input flex-1"
          >
            {SESSION_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button onClick={saveSession} className="btn-primary px-4">Save</button>
        </div>
        <p className="text-xs text-charcoal-400 mt-2">
          Takes effect on your next sign-in.
        </p>
      </div>

      {/* Bottom Bar Shortcuts */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Bottom Bar Shortcuts</h2>
          {shortcutSaved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Pin up to 4 modules to the bottom bar. Drag to reorder.
        </p>

        {/* Pinned shortcuts — draggable */}
        <ul className="space-y-2 mb-3">
          {shortcutIds.map((id, i) => {
            const mod = ALL_MODULES.find(m => m.id === id)
            if (!mod) return null
            return (
              <li
                key={id}
                draggable
                onDragStart={() => onShortcutDragStart(i)}
                onDragOver={e => onShortcutDragOver(e, i)}
                onDragEnd={onShortcutDragEnd}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                  shortcutDragIdx === i
                    ? 'border-orange-500 bg-orange-500/10'
                    : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                }`}
              >
                <span className="text-base leading-none">{mod.icon}</span>
                <span className="flex-1 text-sm">{mod.label}</span>
                <button
                  onClick={() => toggleShortcut(id)}
                  className="text-charcoal-400 hover:text-red-500 text-xs"
                >✕</button>
                <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
              </li>
            )
          })}
        </ul>

        {/* Available modules to add */}
        {shortcutIds.length < 4 && (
          <div className="mb-4">
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mb-2">
              Add ({4 - shortcutIds.length} slot{4 - shortcutIds.length !== 1 ? 's' : ''} left):
            </p>
            <div className="flex flex-wrap gap-2">
              {ALL_MODULES.filter(m => !shortcutIds.includes(m.id)).map(mod => (
                <button
                  key={mod.id}
                  onClick={() => toggleShortcut(mod.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-charcoal-300 dark:border-charcoal-600 text-xs text-charcoal-500 dark:text-charcoal-400 hover:border-orange-500 hover:text-orange-500 transition-colors"
                >
                  <span>{mod.icon}</span>
                  {mod.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <button onClick={saveShortcutsHandler} className="btn-primary w-full">
          Save Shortcuts
        </button>
      </div>

      {/* Admin — User Access */}
      {user?.role === 'admin' && (
        <div className="card p-5">
          <h2 className="font-semibold mb-1">User Access</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
            Disable modules for specific users. Admins always have full access.
          </p>

          {/* Open registration toggle */}
          <div className="flex items-center justify-between py-3 border-b border-charcoal-100 dark:border-charcoal-800 mb-4">
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
          {/* Add user form */}
          <form onSubmit={addUser} className="space-y-3 mb-5">
            <p className="text-sm font-medium">Add User</p>
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

          {/* Per-user module access */}
          <div className="space-y-5">
            {allUsers.filter(u => u.role !== 'admin').length === 0 && (
              <p className="text-sm text-charcoal-400 dark:text-charcoal-500">
                No other users yet.
              </p>
            )}
            {allUsers.filter(u => u.role !== 'admin').map(u => (
              <div key={u.id}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">{u.name}</span>
                  <button
                    onClick={() => saveUserModules(u.id)}
                    disabled={moduleSaving === u.id}
                    className="btn-primary text-xs px-3 py-1"
                  >
                    {moduleSaving === u.id ? '…' : 'Save'}
                  </button>
                </div>
                <div className="space-y-1">
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
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Account */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Account</h2>
        <button onClick={handleLogout} className="text-red-500 hover:text-red-600 text-sm font-medium">
          Sign out
        </button>
      </div>
    </div>
  )
}
