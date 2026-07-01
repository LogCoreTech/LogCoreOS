import { useEffect, useState } from 'react'
import { admin as adminApi, features as featuresApi, infisical as infisicalApi, automations as automationsApi, home as homeApi, priorities as prioritiesApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ALL_MODULES } from '../lib/constants'

const QUICK_GUIDES = [
  {
    label: 'Ollama (local)',
    provider: 'openai',
    base_url: 'http://localhost:11434/v1',
    api_key: 'ollama',
    model: 'llama3.2',
  },
  {
    label: 'Groq',
    provider: 'openai',
    base_url: '',
    api_key: '<your groq key>',
    model: 'llama-3.3-70b-versatile',
  },
  {
    label: 'Gemini',
    provider: 'openai',
    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    api_key: '<your gemini key>',
    model: 'gemini-2.0-flash',
  },
  {
    label: 'OpenAI',
    provider: 'openai',
    base_url: '',
    api_key: '<your openai key>',
    model: 'gpt-4o',
  },
  {
    label: 'Anthropic',
    provider: 'anthropic',
    base_url: '',
    api_key: '<your anthropic key>',
    model: 'claude-sonnet-4-6',
  },
]

const ROLE_COLORS = {
  admin:  'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  member: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  guest:  'bg-charcoal-100 text-charcoal-600 dark:bg-charcoal-800 dark:text-charcoal-400',
}

function initials(name) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

// ---------------------------------------------------------------------------
// Users card
// ---------------------------------------------------------------------------
const BLANK_NEW_USER = { email: '', name: '', password: '', role: 'member', feature_role: 'guest', workspaces: ['personal'] }

function UsersCard({ currentUserId, roles, onRolesLoaded }) {
  const [users, setUsers]             = useState([])
  const [loading, setLoading]         = useState(true)
  const [pendingRole, setPendingRole] = useState({})
  const [saving, setSaving]           = useState(null)
  const [deleting, setDeleting]       = useState(null)
  const [msg, setMsg]                 = useState(null)
  const [showCreate, setShowCreate]   = useState(false)
  const [newUser, setNewUser]         = useState(BLANK_NEW_USER)
  const [creating, setCreating]       = useState(false)

  // Module management state
  const [userModules, setUserModules]       = useState({})
  const [moduleSaving, setModuleSaving]     = useState(null)
  const [expandedUser, setExpandedUser]     = useState(null)
  const [wsTab, setWsTab]                   = useState({})
  // Workspace access
  const [userWorkspaces, setUserWorkspaces] = useState({})
  const [wsSaving, setWsSaving]             = useState(null)
  // Feature role assignment
  const [pendingFRole, setPendingFRole]     = useState({})
  const [fRoleSaving, setFRoleSaving]       = useState(null)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 4000)
  }

  async function loadUsers() {
    const [d, fd] = await Promise.all([adminApi.listUsers(), featuresApi.get()])
    const list = d.users || d
    setUsers(list)
    const modMap = {}
    const wsMap = {}
    list.forEach(u => {
      const raw = u.disabled_modules
      if (Array.isArray(raw)) {
        modMap[u.id] = { personal: raw, business: raw }
      } else if (raw && typeof raw === 'object') {
        modMap[u.id] = { personal: raw.personal || [], business: raw.business || [] }
      } else {
        modMap[u.id] = { personal: [], business: [] }
      }
      wsMap[u.id] = u.workspaces || ['personal']
    })
    setUserModules(modMap)
    setUserWorkspaces(wsMap)
    onRolesLoaded(Object.keys(fd.roles || { member: {} }))
  }

  useEffect(() => {
    loadUsers()
      .catch(() => flash(false, 'Failed to load users'))
      .finally(() => setLoading(false))
  }, [])

  async function saveRole(user) {
    const role = pendingRole[user.id]
    if (!role || role === user.role) return
    setSaving(user.id)
    try {
      const updated = await adminApi.updateUserRole(user.id, role)
      setUsers(us => us.map(u => u.id === user.id ? { ...u, role: updated.role } : u))
      setPendingRole(p => { const n = { ...p }; delete n[user.id]; return n })
      flash(true, `${user.name}'s role updated to ${updated.role}.`)
    } catch (err) {
      flash(false, err.message || 'Failed to update role')
    } finally {
      setSaving(null)
    }
  }

  async function confirmDelete(user) {
    if (!window.confirm(`Delete ${user.name}? This cannot be undone.`)) return
    setDeleting(user.id)
    try {
      await adminApi.deleteUser(user.id)
      setUsers(us => us.filter(u => u.id !== user.id))
      flash(true, `${user.name} deleted.`)
    } catch (err) {
      flash(false, err.message || 'Failed to delete user')
    } finally {
      setDeleting(null)
    }
  }

  async function submitCreate(e) {
    e.preventDefault()
    setCreating(true)
    try {
      const created = await adminApi.createUser({
        ...newUser,
        feature_role: newUser.feature_role || 'guest',
      })
      setUsers(us => [...us, { ...created, feature_role: newUser.feature_role || 'guest', workspaces: newUser.workspaces || ['personal'] }])
      setUserModules(prev => ({ ...prev, [created.id]: { personal: [], business: [] } }))
      setUserWorkspaces(prev => ({ ...prev, [created.id]: newUser.workspaces || ['personal'] }))
      setNewUser(BLANK_NEW_USER)
      setShowCreate(false)
      flash(true, `${created.name} created.`)
    } catch (err) {
      flash(false, err.message || 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  function toggleUserModule(userId, moduleId, workspace) {
    setUserModules(prev => {
      const cur = prev[userId] || { personal: [], business: [] }
      const list = cur[workspace] || []
      return {
        ...prev,
        [userId]: {
          ...cur,
          [workspace]: list.includes(moduleId)
            ? list.filter(id => id !== moduleId)
            : [...list, moduleId],
        },
      }
    })
  }

  async function saveUserModules(userId, workspace) {
    setModuleSaving(userId)
    try {
      const mods = userModules[userId] || { personal: [], business: [] }
      await adminApi.updateWorkspaceModules(userId, workspace, mods[workspace] || [])
      flash(true, `${workspace.charAt(0).toUpperCase() + workspace.slice(1)} module access saved.`)
    } catch (err) {
      flash(false, err.message || 'Failed to save module access')
    } finally {
      setModuleSaving(null)
    }
  }

  function toggleUserWorkspace(userId, ws) {
    setUserWorkspaces(prev => {
      const cur = prev[userId] || ['personal']
      const next = cur.includes(ws) ? cur.filter(w => w !== ws) : [...cur, ws]
      return { ...prev, [userId]: next.length > 0 ? next : cur }
    })
  }

  async function saveUserWorkspaces(userId) {
    setWsSaving(userId)
    try {
      await adminApi.updateWorkspaces(userId, userWorkspaces[userId] || ['personal'])
      flash(true, 'Workspace access saved.')
    } catch (err) {
      flash(false, err.message || 'Failed to save workspace access')
    } finally {
      setWsSaving(null)
    }
  }

  async function saveFeatureRole(userId) {
    const role = pendingFRole[userId]
    if (!role) return
    setFRoleSaving(userId)
    try {
      await featuresApi.setUserRole(userId, role)
      setUsers(us => us.map(u => u.id === userId ? { ...u, feature_role: role } : u))
      setPendingFRole(p => { const n = { ...p }; delete n[userId]; return n })
      flash(true, 'Feature role updated.')
    } catch (err) {
      flash(false, err.message || 'Failed to update feature role')
    } finally {
      setFRoleSaving(null)
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold">Users</h2>
        <button
          onClick={() => setShowCreate(o => !o)}
          className="btn-primary text-sm py-1 px-3"
        >
          {showCreate ? 'Cancel' : '+ Add User'}
        </button>
      </div>

      {/* Create user form */}
      {showCreate && (
        <form
          onSubmit={submitCreate}
          className="mb-4 p-4 rounded-lg border border-orange-200 dark:border-orange-900/40 bg-orange-50 dark:bg-orange-900/10 space-y-3"
        >
          <p className="text-sm font-medium text-orange-700 dark:text-orange-400">New user</p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1">Full name</label>
              <input
                type="text"
                required
                value={newUser.name}
                onChange={e => setNewUser(u => ({ ...u, name: e.target.value }))}
                placeholder="Jane Smith"
                className="input text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">Role</label>
              <select
                value={newUser.role}
                onChange={e => setNewUser(u => ({ ...u, role: e.target.value }))}
                className="input text-sm"
              >
                <option value="admin">admin</option>
                <option value="member">member</option>
                <option value="guest">guest</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Feature Access Role</label>
            <select
              value={newUser.feature_role || 'guest'}
              onChange={e => setNewUser(u => ({ ...u, feature_role: e.target.value }))}
              className="input text-sm"
            >
              {roles.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <p className="text-xs text-charcoal-400 mt-1">Controls which app features this user can see.</p>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Workspace Access</label>
            <div className="flex items-center gap-4">
              {['personal', 'business'].map(ws => (
                <label key={ws} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={(newUser.workspaces || ['personal']).includes(ws)}
                    onChange={() => {
                      const cur = newUser.workspaces || ['personal']
                      const next = cur.includes(ws) ? cur.filter(w => w !== ws) : [...cur, ws]
                      if (next.length > 0) setNewUser(u => ({ ...u, workspaces: next }))
                    }}
                    className="accent-orange-500 w-4 h-4"
                  />
                  <span className="text-sm capitalize">{ws}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Email</label>
            <input
              type="email"
              required
              value={newUser.email}
              onChange={e => setNewUser(u => ({ ...u, email: e.target.value }))}
              placeholder="jane@example.com"
              className="input text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={newUser.password}
              onChange={e => setNewUser(u => ({ ...u, password: e.target.value }))}
              placeholder="Min 8 characters"
              className="input text-sm"
              autoComplete="new-password"
            />
          </div>

          <button type="submit" disabled={creating} className="btn-primary w-full text-sm">
            {creating ? 'Creating…' : 'Create User'}
          </button>
        </form>
      )}

      {/* User list */}
      {loading ? (
        <p className="text-sm text-charcoal-400">Loading…</p>
      ) : (
        <div className="space-y-3">
          {users.map(user => {
            const isSelf    = user.id === currentUserId
            const roleValue = pendingRole[user.id] ?? user.role
            const dirty     = roleValue !== user.role
            const expanded  = expandedUser === user.id

            return (
              <div
                key={user.id}
                className="rounded-lg border border-charcoal-100 dark:border-charcoal-800"
              >
                <div className="flex items-center gap-3 p-3">
                  <div className="w-9 h-9 rounded-full bg-orange-500 text-white flex items-center justify-center text-sm font-semibold shrink-0">
                    {initials(user.name)}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm truncate">{user.name}</span>
                      {isSelf && <span className="text-xs text-charcoal-400">(you)</span>}
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${ROLE_COLORS[user.role] || ROLE_COLORS.member}`}>
                        {user.role}
                      </span>
                    </div>
                    <div className="text-xs text-charcoal-400 truncate">{user.email}</div>
                  </div>

                  <select
                    value={roleValue}
                    disabled={isSelf}
                    onChange={e => setPendingRole(p => ({ ...p, [user.id]: e.target.value }))}
                    className="input text-sm py-1 w-28 shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <option value="admin">admin</option>
                    <option value="member">member</option>
                    <option value="guest">guest</option>
                  </select>

                  <button
                    onClick={() => saveRole(user)}
                    disabled={!dirty || isSelf || saving === user.id}
                    className="btn-primary text-xs py-1 px-3 shrink-0 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {saving === user.id ? '…' : 'Save'}
                  </button>

                  <button
                    onClick={() => confirmDelete(user)}
                    disabled={isSelf || deleting === user.id}
                    title={isSelf ? 'Cannot delete your own account' : `Delete ${user.name}`}
                    className="text-charcoal-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
                  >
                    {deleting === user.id ? '…' : '✕'}
                  </button>
                </div>

                {/* Feature role + module access — only for non-admins */}
                {user.role !== 'admin' && (
                  <>
                    {/* Workspace access — always visible */}
                    <div className="border-t border-charcoal-100 dark:border-charcoal-800 px-3 py-2 flex items-center gap-3 flex-wrap">
                      <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">Workspaces</span>
                      <div className="flex items-center gap-3">
                        {['personal', 'business'].map(ws => (
                          <label key={ws} className="flex items-center gap-1.5 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={(userWorkspaces[user.id] || ['personal']).includes(ws)}
                              onChange={() => toggleUserWorkspace(user.id, ws)}
                              className="accent-orange-500 w-3.5 h-3.5"
                            />
                            <span className="text-xs capitalize">{ws}</span>
                          </label>
                        ))}
                      </div>
                      <button
                        onClick={() => saveUserWorkspaces(user.id)}
                        disabled={wsSaving === user.id}
                        className="btn-primary text-xs px-3 py-1 shrink-0 disabled:opacity-30"
                      >
                        {wsSaving === user.id ? '…' : 'Save'}
                      </button>
                    </div>

                    {/* Feature role — always visible */}
                    <div className="border-t border-charcoal-100 dark:border-charcoal-800 px-3 py-2 flex items-center gap-2">
                      <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">Feature role</span>
                      <select
                        value={pendingFRole[user.id] ?? (user.feature_role || 'guest')}
                        onChange={e => setPendingFRole(p => ({ ...p, [user.id]: e.target.value }))}
                        className="input text-xs py-1 flex-1"
                      >
                        {roles.map(r => <option key={r} value={r}>{r}</option>)}
                      </select>
                      <button
                        onClick={() => saveFeatureRole(user.id)}
                        disabled={!pendingFRole[user.id] || pendingFRole[user.id] === (user.feature_role || 'guest') || fRoleSaving === user.id}
                        className="btn-primary text-xs px-3 py-1 shrink-0 disabled:opacity-30"
                      >
                        {fRoleSaving === user.id ? '…' : 'Save'}
                      </button>
                      <button
                        onClick={() => setExpandedUser(expanded ? null : user.id)}
                        className="text-xs text-charcoal-400 hover:text-orange-500 transition-colors shrink-0"
                        title="Manage per-module overrides"
                      >
                        {expanded ? '▾ Modules' : '▸ Modules'}
                      </button>
                    </div>

                    {/* Per-workspace module overrides — collapsed by default */}
                    {expanded && (
                      <div className="px-3 pb-3">
                        <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Module Restrictions</p>
                        <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1 mb-2">
                          {['personal', 'business'].map(ws => (
                            <button
                              key={ws}
                              onClick={() => setWsTab(p => ({ ...p, [user.id]: ws }))}
                              className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                                (wsTab[user.id] || 'personal') === ws
                                  ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                                  : 'text-charcoal-500 dark:text-charcoal-400'
                              }`}
                            >
                              {ws}
                            </button>
                          ))}
                        </div>
                        {(() => {
                          const activeWs = wsTab[user.id] || 'personal'
                          const wsDisabled = ((userModules[user.id] || {})[activeWs]) || []
                          return (
                            <>
                              <div className="space-y-1 mb-2">
                                {ALL_MODULES.map(mod => {
                                  const disabled = wsDisabled.includes(mod.id)
                                  return (
                                    <label
                                      key={mod.id}
                                      className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 cursor-pointer"
                                    >
                                      <input
                                        type="checkbox"
                                        checked={!disabled}
                                        onChange={() => toggleUserModule(user.id, mod.id, activeWs)}
                                        className="accent-orange-500 w-4 h-4"
                                      />
                                      <span className="text-sm leading-none">{mod.icon}</span>
                                      <span className="text-sm">{mod.label}</span>
                                    </label>
                                  )
                                })}
                              </div>
                              <button
                                onClick={() => saveUserModules(user.id, activeWs)}
                                disabled={moduleSaving === user.id}
                                className="btn-primary text-xs px-3 py-1 w-full capitalize"
                              >
                                {moduleSaving === user.id ? '…' : `Save ${activeWs} overrides`}
                              </button>
                            </>
                          )
                        })()}
                      </div>
                    )}
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}

      {msg && (
        <p className={`text-sm mt-3 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Registration card
// ---------------------------------------------------------------------------
function RegistrationCard() {
  const [allowed, setAllowed] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    adminApi.getSettings()
      .then(d => setAllowed(d.allow_open_registration ?? false))
      .catch(() => {})
  }, [])

  async function toggle() {
    const next = !allowed
    setSaving(true)
    setMsg(null)
    try {
      const updated = await adminApi.updateSettings({ allow_open_registration: next })
      setAllowed(updated.allow_open_registration)
      setMsg({ ok: true, text: next ? 'Registration is now open.' : 'Registration is now closed.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Failed to save' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Registration</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        When closed, only admins can create new accounts.
      </p>

      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Open registration</p>
          <p className="text-xs text-charcoal-400">
            {allowed ? 'Anyone can create an account.' : 'New sign-ups are disabled.'}
          </p>
        </div>

        <button
          onClick={toggle}
          disabled={saving}
          className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
            allowed ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-700'
          } disabled:opacity-50`}
          role="switch"
          aria-checked={allowed}
        >
          <span
            className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ${
              allowed ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {msg && (
        <p className={`text-sm mt-3 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AI Provider card
// ---------------------------------------------------------------------------
function AiProviderCard() {
  const [form, setForm] = useState({
    ai_provider: 'anthropic',
    ai_api_key: '',
    ai_base_url: '',
    ai_model: '',
  })
  const [keySet, setKeySet]         = useState(false)
  const [saving, setSaving]         = useState(false)
  const [saveMsg, setSaveMsg]       = useState(null)
  const [guidesOpen, setGuidesOpen] = useState(false)

  useEffect(() => {
    adminApi.getAiSettings().then(s => {
      setForm(f => ({
        ...f,
        ai_provider: s.ai_provider || 'anthropic',
        ai_base_url: s.ai_base_url || '',
        ai_model: s.ai_model || '',
      }))
      setKeySet(s.ai_api_key_set || false)
    }).catch(() => {})
  }, [])

  function applyGuide(g) {
    setForm(f => ({
      ...f,
      ai_provider: g.provider,
      ai_base_url: g.base_url,
      ai_model: g.model,
      ai_api_key: g.api_key.startsWith('<') ? '' : g.api_key,
    }))
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setSaveMsg(null)
    try {
      const updated = await adminApi.updateAiSettings(form)
      setKeySet(updated.ai_api_key_set || false)
      setForm(f => ({ ...f, ai_api_key: '' }))
      setSaveMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setSaveMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">AI Provider</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Model must support tool / function calling. Changes take effect immediately.
      </p>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Provider</label>
          <select
            value={form.ai_provider}
            onChange={e => setForm(f => ({ ...f, ai_provider: e.target.value }))}
            className="input"
          >
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI / Compatible</option>
          </select>
        </div>

        {form.ai_provider === 'openai' && (
          <div>
            <label className="block text-sm font-medium mb-1">Base URL</label>
            <input
              type="text"
              value={form.ai_base_url}
              onChange={e => setForm(f => ({ ...f, ai_base_url: e.target.value }))}
              placeholder="http://localhost:11434/v1"
              className="input"
            />
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5">
              Leave blank for OpenAI default. Required for Ollama, Groq, Gemini, etc.
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1">Model</label>
          <input
            type="text"
            value={form.ai_model}
            onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
            placeholder={form.ai_provider === 'anthropic' ? 'claude-sonnet-4-6' : 'gpt-4o'}
            className="input"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">API Key</label>
          <input
            type="password"
            value={form.ai_api_key}
            onChange={e => setForm(f => ({ ...f, ai_api_key: e.target.value }))}
            placeholder={keySet ? '••••••••  (leave blank to keep current)' : 'Paste your API key'}
            className="input"
            autoComplete="new-password"
          />
        </div>

        {saveMsg && (
          <p className={`text-sm ${saveMsg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {saveMsg.text}
          </p>
        )}

        <button type="submit" disabled={saving} className="btn-primary w-full">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>

      <div className="mt-4 border-t border-charcoal-100 dark:border-charcoal-800 pt-4">
        <button
          onClick={() => setGuidesOpen(o => !o)}
          className="flex items-center gap-1 text-sm text-charcoal-500 dark:text-charcoal-400 hover:text-orange-500 transition-colors"
        >
          <span>{guidesOpen ? '▾' : '▸'}</span>
          Quick setup guides
        </button>

        {guidesOpen && (
          <div className="mt-3 space-y-2">
            {QUICK_GUIDES.map(g => (
              <div
                key={g.label}
                className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">{g.label}</span>
                  <button
                    type="button"
                    onClick={() => applyGuide(g)}
                    className="text-xs text-orange-500 hover:text-orange-600 font-medium"
                  >
                    Apply
                  </button>
                </div>
                <div className="text-xs text-charcoal-500 dark:text-charcoal-400 space-y-0.5 font-mono">
                  <div>provider: {g.provider}</div>
                  {g.base_url && <div>base_url: {g.base_url}</div>}
                  <div>model: {g.model}</div>
                  <div>api_key: {g.api_key}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Web Search card
// ---------------------------------------------------------------------------
function WebSearchCard() {
  const [keySet, setKeySet]   = useState(false)
  const [key, setKey]         = useState('')
  const [saving, setSaving]   = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    adminApi.getSearchSettings().then(s => setKeySet(s.tavily_key_set || false)).catch(() => {})
  }, [])

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      const res = await adminApi.updateSearchSettings({ tavily_api_key: key })
      setKeySet(res.tavily_key_set || false)
      setKey('')
      setMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Web Search</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Enables web search in AI Research mode. Get a free Tavily API key at{' '}
        <span className="font-mono">tavily.com</span> (1 000 searches/month free).
      </p>

      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2 h-2 rounded-full ${keySet ? 'bg-green-500' : 'bg-charcoal-300'}`} />
        <span className="text-sm">{keySet ? 'API key configured' : 'No API key set'}</span>
      </div>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Tavily API Key</label>
          <input
            type="password"
            value={key}
            onChange={e => setKey(e.target.value)}
            placeholder={keySet ? '••••••••  (leave blank to keep current)' : 'tvly-…'}
            className="input"
            autoComplete="new-password"
          />
        </div>
        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}
        <button type="submit" disabled={saving || !key} className="btn-primary w-full disabled:opacity-50">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hosting card
// ---------------------------------------------------------------------------
function HostingCard() {
  const [form, setForm]         = useState({ mode: 'local', domain_url: '', tunnel_token: '' })
  const [tokenSaved, setTokenSaved] = useState(false)
  const [saving, setSaving]     = useState(false)
  const [applying, setApplying] = useState(false)
  const [msg, setMsg]           = useState(null)

  useEffect(() => {
    adminApi.getHostingSettings().then(s => {
      let mode = 'local'
      if (s.proxy_type === 'cloudflare' || s.proxy_type === 'nginx') {
        mode = s.proxy_type
      } else if (s.cookie_secure || s.trust_proxy_headers) {
        mode = 'cloudflare'
      }
      setForm({ mode, domain_url: s.domain_url || '', tunnel_token: '' })
      setTokenSaved(s.tunnel_token_set || false)
    }).catch(() => {})
  }, [])

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    const isHttps = form.mode !== 'local'
    const payload = {
      proxy_type: form.mode === 'local' ? '' : form.mode,
      cookie_secure: isHttps,
      trust_proxy_headers: isHttps,
      domain_url: isHttps ? form.domain_url.trim() : '',
    }
    if (form.tunnel_token) payload.tunnel_token = form.tunnel_token
    try {
      const updated = await adminApi.updateHostingSettings(payload)
      setTokenSaved(updated.tunnel_token_set || false)
      setForm(f => ({ ...f, tunnel_token: '' }))
      setMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  async function applyTunnel() {
    setApplying(true)
    setMsg(null)
    try {
      await adminApi.applyHostingSettings()
      setMsg({ ok: true, text: 'Tunnel restarted. Your domain should be live in a few seconds.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Restart failed. Check container logs.' })
    } finally {
      setApplying(false)
      setTimeout(() => setMsg(null), 8000)
    }
  }

  const isHttps = form.mode !== 'local'
  const needsDomain = isHttps && !form.domain_url.trim()

  const nginxConfig = (() => {
    if (!form.domain_url) return ''
    try {
      const { hostname } = new URL(form.domain_url)
      return `server {
    listen 443 ssl;
    server_name ${hostname};

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}`
    } catch { return '' }
  })()

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Hosting</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Configure how this app is accessed. Changes take effect immediately.
      </p>

      <form onSubmit={save} className="space-y-4">
        {/* Mode selector */}
        <div className="space-y-2">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="radio" name="mode" value="local" checked={form.mode === 'local'}
              onChange={() => setForm(f => ({ ...f, mode: 'local', domain_url: '', tunnel_token: '' }))}
              className="accent-orange-500" />
            <span className="text-sm">
              <span className="font-medium">Local only</span>
              <span className="text-charcoal-500 dark:text-charcoal-400"> — http://localhost:8000</span>
            </span>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="radio" name="mode" value="cloudflare" checked={form.mode === 'cloudflare'}
              onChange={() => setForm(f => ({ ...f, mode: 'cloudflare' }))}
              className="accent-orange-500" />
            <span className="text-sm font-medium">Cloudflare Tunnel</span>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="radio" name="mode" value="nginx" checked={form.mode === 'nginx'}
              onChange={() => setForm(f => ({ ...f, mode: 'nginx' }))}
              className="accent-orange-500" />
            <span className="text-sm font-medium">nginx / Caddy / Reverse Proxy</span>
          </label>
        </div>

        {/* Domain URL — shown for both HTTPS modes */}
        {isHttps && (
          <div>
            <label className="block text-sm font-medium mb-1">Domain URL</label>
            <input
              type="url"
              value={form.domain_url}
              onChange={e => setForm(f => ({ ...f, domain_url: e.target.value }))}
              placeholder="https://logcore.yourdomain.com"
              className="input"
              autoComplete="off"
              required
            />
            {form.mode === 'cloudflare' && (
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
                Set this as the public hostname in Cloudflare Zero Trust → Networks → Tunnels → your tunnel → Configure.
              </p>
            )}
            {form.mode === 'nginx' && (
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
                Your reverse proxy must forward to <span className="font-mono">http://localhost:8000</span>.
              </p>
            )}
          </div>
        )}

        {/* Cloudflare: tunnel token */}
        {form.mode === 'cloudflare' && (
          <div>
            <label className="block text-sm font-medium mb-1">Tunnel Token</label>
            <input
              type="password"
              value={form.tunnel_token}
              onChange={e => setForm(f => ({ ...f, tunnel_token: e.target.value }))}
              placeholder={tokenSaved ? '••••••••••••• (saved — paste to replace)' : 'Paste token from Cloudflare dashboard'}
              className="input font-mono"
              autoComplete="new-password"
            />
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
              Find your token in Cloudflare Zero Trust → Networks → Tunnels → your tunnel → Configure.
            </p>
          </div>
        )}

        {/* nginx: generated config */}
        {form.mode === 'nginx' && nginxConfig && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium">nginx Config</label>
              <button type="button" onClick={() => navigator.clipboard.writeText(nginxConfig)}
                className="text-xs text-orange-500 hover:underline">Copy</button>
            </div>
            <pre className="bg-charcoal-900 text-charcoal-100 text-xs rounded p-3 overflow-x-auto whitespace-pre">{nginxConfig}</pre>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
              Paste into your nginx config, then run <span className="font-mono">nginx -t && systemctl reload nginx</span>.
            </p>
          </div>
        )}

        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}

        <button type="submit" disabled={saving || needsDomain} className="btn-primary w-full disabled:opacity-50">
          {saving ? 'Saving…' : 'Save Hosting Settings'}
        </button>

        {/* Cloudflare: apply button (only shown after token is saved) */}
        {form.mode === 'cloudflare' && tokenSaved && (
          <button
            type="button"
            onClick={applyTunnel}
            disabled={applying}
            className="btn-ghost w-full border border-orange-500 text-orange-500 hover:bg-orange-500 hover:text-white disabled:opacity-50"
          >
            {applying ? 'Restarting tunnel…' : 'Apply & Restart Tunnel'}
          </button>
        )}

        {isHttps && form.domain_url && !needsDomain && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 flex items-start gap-1">
            <span>✓</span>
            <span>
              App will be accessible at{' '}
              <a href={form.domain_url} target="_blank" rel="noopener noreferrer" className="text-orange-500 underline">
                {form.domain_url}
              </a>
              . Make sure your tunnel or proxy passes the <span className="font-mono">X-Forwarded-For</span> header.
            </span>
          </p>
        )}
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Infisical / Managed Hosting card — only visible when a token is configured
// ---------------------------------------------------------------------------
function InfisicalCard() {
  const [status, setStatus]   = useState(null)   // null = loading
  const [token, setToken]     = useState('')
  const [saving, setSaving]   = useState(false)
  const [clearing, setClearing] = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    infisicalApi.getStatus()
      .then(s => setStatus(s))
      .catch(() => setStatus({ configured: false }))
  }, [])

  // Hidden entirely when not configured — self-hosters never see this
  if (!status || !status.configured) return null

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 5000)
  }

  async function save(e) {
    e.preventDefault()
    if (!token.trim()) return
    setSaving(true)
    setMsg(null)
    try {
      const res = await infisicalApi.setToken(token.trim())
      setStatus(res)
      setToken('')
      flash(true, res.message || 'Token saved. New secrets will load on next restart.')
    } catch (err) {
      flash(false, err.message || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  async function clear() {
    if (!confirm('Clear the saved Infisical token? The app will revert to local .env on next restart.')) return
    setClearing(true)
    setMsg(null)
    try {
      await infisicalApi.clearToken()
      setStatus({ configured: false, source: null })
      flash(true, 'Token cleared.')
    } catch (err) {
      flash(false, err.message || 'Clear failed.')
    } finally {
      setClearing(false)
    }
  }

  const sourceLabel = status.source === 'env'
    ? 'environment variable (set at deploy time)'
    : 'admin panel'

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Managed Hosting</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Secrets are pulled from Infisical at startup. Rotate the token here — new secrets apply on next restart.
      </p>

      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2 h-2 rounded-full ${status.connected ? 'bg-green-500' : 'bg-red-400'}`} />
        <span className="text-sm">
          {status.connected ? 'Connected to Infisical' : 'Infisical unreachable (running from cache)'}
        </span>
      </div>

      <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mb-4">
        Token source: {sourceLabel}
        {status.last_fetched && (
          <span className="ml-2">· Last fetched: {new Date(status.last_fetched).toLocaleString()}</span>
        )}
      </p>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Rotate Token</label>
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="Paste new Infisical token to rotate"
            className="input font-mono"
            autoComplete="new-password"
          />
        </div>
        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={saving || !token.trim()}
          className="btn-primary w-full disabled:opacity-50"
        >
          {saving ? 'Validating & saving…' : 'Save new token'}
        </button>
      </form>

      {status.source === 'file' && (
        <button
          onClick={clear}
          disabled={clearing}
          className="mt-3 w-full text-sm text-red-500 hover:text-red-600 disabled:opacity-50 text-center"
        >
          {clearing ? 'Clearing…' : 'Clear token (revert to self-hosted .env mode)'}
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Roles card
// ---------------------------------------------------------------------------
function RolesCard({ roles, onRolesChange }) {
  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [roleMods, setRoleMods] = useState({})
  const [saving, setSaving]       = useState(null)
  const [deleting, setDeleting]   = useState(null)
  const [expandedRole, setExpandedRole] = useState(null)
  const [msg, setMsg]             = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newRoleName, setNewRoleName] = useState('')
  const [newRoleMods, setNewRoleMods] = useState({})
  const [creating, setCreating] = useState(false)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 4000)
  }

  async function load() {
    const d = await featuresApi.get()
    setData(d)
    const mods = {}
    const names = []
    for (const [name, map] of Object.entries(d.roles || {})) {
      mods[name] = { ...map }
      names.push(name)
    }
    setRoleMods(mods)
    onRolesChange(names)
  }

  useEffect(() => {
    load().catch(() => flash(false, 'Failed to load feature roles')).finally(() => setLoading(false))
  }, [])

  function toggleMod(roleName, modId) {
    setRoleMods(prev => ({
      ...prev,
      [roleName]: { ...prev[roleName], [modId]: !prev[roleName]?.[modId] },
    }))
  }

  async function saveRole(name) {
    setSaving(name)
    try {
      await featuresApi.updateRole(name, roleMods[name])
      flash(true, `Role "${name}" saved.`)
    } catch (err) {
      flash(false, err.message || 'Failed to save role')
    } finally {
      setSaving(null)
    }
  }

  async function deleteRole(name) {
    if (!window.confirm(`Delete role "${name}"? Users with this role will fall back to "member".`)) return
    setDeleting(name)
    try {
      await featuresApi.deleteRole(name)
      setRoleMods(prev => { const n = { ...prev }; delete n[name]; return n })
      setData(prev => {
        const r = { ...prev.roles }
        delete r[name]
        return { ...prev, roles: r }
      })
      onRolesChange(roles.filter(r => r !== name))
      flash(true, `Role "${name}" deleted.`)
    } catch (err) {
      flash(false, err.message || 'Failed to delete role')
    } finally {
      setDeleting(null)
    }
  }

  async function createRole(e) {
    e.preventDefault()
    const trimmed = newRoleName.trim()
    if (!trimmed) return
    setCreating(true)
    try {
      const modMap = {}
      ALL_MODULES.forEach(m => { modMap[m.id] = newRoleMods[m.id] !== false })
      await featuresApi.createRole(trimmed, modMap)
      setRoleMods(prev => ({ ...prev, [trimmed]: modMap }))
      setData(prev => ({ ...prev, roles: { ...prev.roles, [trimmed]: modMap } }))
      onRolesChange([...roles, trimmed])
      setNewRoleName('')
      setNewRoleMods({})
      setShowCreate(false)
      flash(true, `Role "${trimmed}" created.`)
    } catch (err) {
      flash(false, err.message || 'Failed to create role')
    } finally {
      setCreating(false)
    }
  }

  if (loading) return <div className="card p-5"><p className="text-sm text-charcoal-400">Loading…</p></div>

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-semibold">Feature Roles</h2>
        <button onClick={() => setShowCreate(o => !o)} className="btn-primary text-sm py-1 px-3">
          {showCreate ? 'Cancel' : '+ New Role'}
        </button>
      </div>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4 break-words">
        Define which modules each role can access. Assign roles to users above.
      </p>

      {/* Create role form */}
      {showCreate && (
        <form
          onSubmit={createRole}
          className="mb-4 p-4 rounded-lg border border-orange-200 dark:border-orange-900/40 bg-orange-50 dark:bg-orange-900/10 space-y-3"
        >
          <p className="text-sm font-medium text-orange-700 dark:text-orange-400">New role</p>
          <div>
            <label className="block text-xs font-medium mb-1">Role name</label>
            <input
              type="text"
              required
              maxLength={40}
              value={newRoleName}
              onChange={e => setNewRoleName(e.target.value)}
              placeholder="e.g. cleaner, nanny, employee"
              className="input text-sm"
            />
          </div>
          <div>
            <p className="text-xs font-medium mb-2">Modules enabled</p>
            <div className="space-y-1">
              {ALL_MODULES.map(mod => {
                const enabled = newRoleMods[mod.id] !== false
                return (
                  <label
                    key={mod.id}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={() => setNewRoleMods(p => ({ ...p, [mod.id]: !enabled }))}
                      className="accent-orange-500 w-4 h-4"
                    />
                    <span className="text-sm leading-none">{mod.icon}</span>
                    <span className="text-sm">{mod.label}</span>
                  </label>
                )
              })}
            </div>
          </div>
          <button type="submit" disabled={creating || !newRoleName.trim()} className="btn-primary w-full text-sm">
            {creating ? 'Creating…' : 'Create Role'}
          </button>
        </form>
      )}

      {/* Role list */}
      <div className="space-y-2">
        {roles.map(name => {
          const isBuiltIn = name === 'member' || name === 'guest'
          const mods = roleMods[name] || {}
          const open = expandedRole === name
          return (
            <div key={name} className="rounded-lg border border-charcoal-100 dark:border-charcoal-800">
              {/* Row header — always visible */}
              <div className="flex items-center gap-3 px-4 py-3">
                <button
                  onClick={() => setExpandedRole(open ? null : name)}
                  className="flex-1 flex items-center gap-2 text-left"
                >
                  <span className="text-xs text-charcoal-400">{open ? '▾' : '▸'}</span>
                  <span className="font-medium text-sm">{name}</span>
                  {isBuiltIn && (
                    <span className="text-xs text-charcoal-400">
                      {name === 'guest' ? 'built-in · default' : 'built-in'}
                    </span>
                  )}
                </button>
                {!isBuiltIn && (
                  <button
                    onClick={() => deleteRole(name)}
                    disabled={deleting === name}
                    className="text-xs text-charcoal-400 hover:text-red-500 transition-colors disabled:opacity-30 shrink-0"
                  >
                    {deleting === name ? '…' : 'Delete'}
                  </button>
                )}
              </div>

              {/* Expanded module toggles */}
              {open && (
                <div className="border-t border-charcoal-100 dark:border-charcoal-800 px-4 pb-4 pt-3">
                  <div className="space-y-1 mb-3">
                    {ALL_MODULES.map(mod => {
                      const enabled = mods[mod.id] !== false
                      return (
                        <label
                          key={mod.id}
                          className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={() => toggleMod(name, mod.id)}
                            className="accent-orange-500 w-4 h-4"
                          />
                          <span className="text-sm leading-none">{mod.icon}</span>
                          <span className="text-sm">{mod.label}</span>
                        </label>
                      )
                    })}
                  </div>
                  <button
                    onClick={() => saveRole(name)}
                    disabled={saving === name}
                    className="btn-primary text-xs px-3 py-1 w-full"
                  >
                    {saving === name ? '…' : 'Save Role'}
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {msg && (
        <p className={`text-sm mt-3 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// n8n card
// ---------------------------------------------------------------------------
function N8nCard() {
  const [url, setUrl]               = useState('http://n8n:5678')
  const [apiKey, setApiKey]         = useState('')
  const [testing, setTesting]       = useState(false)
  const [saving, setSaving]         = useState(false)
  const [syncing, setSyncing]       = useState(false)
  const [syncingWf, setSyncingWf]   = useState(false)
  const [msg, setMsg]               = useState(null)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 5000)
  }

  async function testConn() {
    setTesting(true)
    setMsg(null)
    try {
      const res = await automationsApi.n8nStatus()
      flash(res.ok, res.ok ? `Connected to ${res.url}` : `Cannot reach ${res.url}${res.error ? ': ' + res.error : ''}`)
    } catch (err) {
      flash(false, err.message || 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  async function saveCfg(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      await automationsApi.saveN8nConfig({ url: url.trim(), api_key: apiKey.trim() })
      flash(true, 'n8n configuration saved.')
    } catch (err) {
      flash(false, err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function syncSecrets() {
    if (!confirm('Write Infisical secrets to n8n.env and restart n8n?')) return
    setSyncing(true)
    setMsg(null)
    try {
      const res = await automationsApi.syncSecrets()
      flash(true, res.message || 'Secrets synced.')
    } catch (err) {
      flash(false, err.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">n8n Automation</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Configure the bundled n8n instance or point to an external one.
      </p>

      <form onSubmit={saveCfg} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">n8n URL</label>
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="http://n8n:5678"
            className="input"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="n8n API key"
            className="input"
            autoComplete="new-password"
          />
        </div>

        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={testConn}
            disabled={testing}
            className="btn-ghost text-sm flex-1 disabled:opacity-50"
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
          <button type="submit" disabled={saving} className="btn-primary text-sm flex-1 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save Config'}
          </button>
        </div>
      </form>

      <div className="mt-3 flex gap-2">
        <button
          onClick={syncSecrets}
          disabled={syncing}
          className="flex-1 text-sm text-charcoal-500 hover:text-orange-500 transition-colors disabled:opacity-50"
        >
          {syncing ? 'Syncing…' : '↺ Sync Infisical → n8n'}
        </button>
        <button
          onClick={async () => {
            setSyncingWf(true)
            setMsg(null)
            try {
              const res = await automationsApi.syncWorkflows()
              const { created = 0, updated = 0, deleted = 0, skipped = 0, errors = [] } = res
              const summary = `Workflows synced — ${created} created, ${updated} updated, ${deleted} deleted, ${skipped} unchanged`
              flash(errors.length === 0, errors.length ? `${summary}. Errors: ${errors.join('; ')}` : summary)
            } catch (err) {
              flash(false, err.message || 'Sync failed')
            } finally {
              setSyncingWf(false)
            }
          }}
          disabled={syncingWf}
          className="flex-1 text-sm text-charcoal-500 hover:text-orange-500 transition-colors disabled:opacity-50"
        >
          {syncingWf ? 'Syncing…' : '⚡ Sync Workflows Now'}
        </button>
      </div>
    </div>
  )
}

function HomeAssistantCard() {
  const [haUrl, setHaUrl]   = useState('')
  const [token, setToken]   = useState('')
  const [msg, setMsg]       = useState(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving]   = useState(false)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 5000)
  }

  async function testConn() {
    setTesting(true)
    setMsg(null)
    try {
      const res = await homeApi.status()
      flash(res.ok, res.ok ? `Connected to ${res.url}` : (res.error || 'Connection failed'))
    } catch (e) {
      flash(false, e.message || 'Connection failed')
    } finally {
      setTesting(false)
    }
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      await homeApi.saveConfig({ url: haUrl.trim(), token: token.trim() })
      flash(true, 'Config saved')
    } catch (e) {
      flash(false, e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-4 space-y-3">
      <div>
        <h2 className="font-semibold text-lg">Smart Home</h2>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
          Connect a Home Assistant instance. Users can control devices, scenes, and automations from the Smart Home page.
        </p>
      </div>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Home Assistant URL</label>
          <input
            type="url"
            value={haUrl}
            onChange={e => setHaUrl(e.target.value)}
            placeholder="http://homeassistant.local:8123"
            className="input"
            autoComplete="off"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Long-Lived Access Token</label>
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="HA long-lived access token"
            className="input"
            autoComplete="new-password"
          />
          <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-1">
            Generate in HA → Profile → Long-Lived Access Tokens
          </p>
        </div>

        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={testConn}
            disabled={testing}
            className="btn-ghost text-sm flex-1 disabled:opacity-50"
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
          <button type="submit" disabled={saving} className="btn-primary text-sm flex-1 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save Config'}
          </button>
        </div>
      </form>
    </div>
  )
}

const POOL_DEFAULT_HOUSEHOLD = ['Cleaning', 'Maintenance', 'Shopping', 'Cooking', 'Yard Work']
const POOL_DEFAULT_TEAM      = ['Projects', 'Client Work', 'Operations', 'Admin', 'Strategy']

function PoolPrioritiesCard() {
  const [household, setHousehold] = useState([])
  const [team, setTeam]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)
  const [msg, setMsg]             = useState(null)
  const [newHH, setNewHH]         = useState('')
  const [newTeam, setNewTeam]     = useState('')
  const [dragState, setDragState] = useState(null) // { pool, idx }

  useEffect(() => {
    prioritiesApi.getPool()
      .then(d => {
        setHousehold(d.household?.length ? d.household : [...POOL_DEFAULT_HOUSEHOLD])
        setTeam(d.team?.length ? d.team : [...POOL_DEFAULT_TEAM])
      })
      .catch(() => {
        setHousehold([...POOL_DEFAULT_HOUSEHOLD])
        setTeam([...POOL_DEFAULT_TEAM])
      })
      .finally(() => setLoading(false))
  }, [])

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 3000)
  }

  async function save() {
    setSaving(true)
    setMsg(null)
    try {
      await prioritiesApi.setPool({ household, team })
      flash(true, 'Saved')
    } catch (e) {
      flash(false, e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  function move(pool, setter, from, to) {
    const next = [...pool]
    const [m] = next.splice(from, 1)
    next.splice(to, 0, m)
    setter(next)
  }

  function remove(pool, setter, cat) {
    if (pool.length <= 1) return
    setter(pool.filter(c => c !== cat))
  }

  function add(pool, setter, val, clearFn) {
    const v = val.trim()
    if (v && !pool.includes(v)) { setter([...pool, v]); clearFn('') }
  }

  function onDragStart(pool, idx) { setDragState({ pool, idx }) }
  function onDragOver(e, pool, idx, setter) {
    e.preventDefault()
    if (!dragState || dragState.pool !== pool || dragState.idx === idx) return
    const next = [...pool]
    const [m] = next.splice(dragState.idx, 1)
    next.splice(idx, 0, m)
    setter(next)
    setDragState({ pool: dragState.pool, idx })
  }
  function onDragEnd() { setDragState(null) }

  function PriorityList({ label, pool, setter, newVal, setNewVal }) {
    return (
      <div>
        <p className="text-sm font-medium mb-2">{label}</p>
        <ul className="space-y-1.5 mb-2">
          {pool.map((cat, i) => (
            <li
              key={cat}
              draggable
              onDragStart={() => onDragStart(label, i)}
              onDragOver={e => onDragOver(e, pool, i, setter)}
              onDragEnd={onDragEnd}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                dragState?.pool === label && dragState?.idx === i
                  ? 'border-orange-500 bg-orange-500/10'
                  : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
              }`}
            >
              <span className="text-charcoal-400 text-xs w-4 shrink-0">{i + 1}</span>
              <span className="flex-1">{cat}</span>
              <div className="flex flex-col shrink-0 mr-2">
                <button type="button" onClick={() => move(pool, setter, i, i - 1)} disabled={i === 0}
                  className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 leading-none px-1 text-xs">▲</button>
                <button type="button" onClick={() => move(pool, setter, i, i + 1)} disabled={i === pool.length - 1}
                  className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 leading-none px-1 text-xs">▼</button>
              </div>
              <button type="button" onClick={() => remove(pool, setter, cat)} disabled={pool.length <= 1}
                className="text-charcoal-400 hover:text-red-500 disabled:opacity-20 text-xs shrink-0">✕</button>
              <span className="text-charcoal-300 dark:text-charcoal-600 cursor-grab hidden md:block">⠿</span>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <input type="text" value={newVal} onChange={e => setNewVal(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && add(pool, setter, newVal, setNewVal)}
            placeholder="Add category…" className="input text-sm" />
          <button onClick={() => add(pool, setter, newVal, setNewVal)} className="btn-primary px-3 text-sm">+</button>
        </div>
      </div>
    )
  }

  return (
    <div className="card p-4 space-y-4">
      <div>
        <h2 className="font-semibold text-lg">Pool Priorities</h2>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
          Category order used to score and rank tasks in the Household and Team shared pools.
          Drag to reorder. These apply to all members of each pool.
        </p>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1,2,3].map(i => <div key={i} className="h-8 bg-charcoal-100 dark:bg-charcoal-800 rounded animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <PriorityList label="Household" pool={household} setter={setHousehold} newVal={newHH} setNewVal={setNewHH} />
          <PriorityList label="Team" pool={team} setter={setTeam} newVal={newTeam} setNewVal={setNewTeam} />
        </div>
      )}

      {msg && (
        <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</p>
      )}

      <button onClick={save} disabled={saving || loading} className="btn-primary text-sm disabled:opacity-50">
        {saving ? 'Saving…' : 'Save Pool Priorities'}
      </button>
    </div>
  )
}

export default function Admin() {
  const { user } = useAuth()
  const [roles, setRoles] = useState(['member'])

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Admin</h1>
      <UsersCard currentUserId={user?.id || ''} roles={roles} onRolesLoaded={setRoles} />
      <RegistrationCard />
      <RolesCard roles={roles} onRolesChange={setRoles} />
      <AiProviderCard />
      <WebSearchCard />
      <HostingCard />
      <InfisicalCard />
      <N8nCard />
      <HomeAssistantCard />
      <PoolPrioritiesCard />
    </div>
  )
}
