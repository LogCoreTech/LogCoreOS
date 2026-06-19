import { useEffect, useState } from 'react'
import { admin as adminApi } from '../lib/api'
import { useAuth } from '../lib/auth'

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
function UsersCard({ currentUserId }) {
  const [users, setUsers]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [pendingRole, setPendingRole] = useState({}) // { [id]: role }
  const [saving, setSaving]     = useState(null)     // user_id being saved
  const [deleting, setDeleting] = useState(null)     // user_id being deleted
  const [msg, setMsg]           = useState(null)     // { ok, text }

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 4000)
  }

  useEffect(() => {
    adminApi.listUsers()
      .then(d => setUsers(d.users))
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

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-4">Users</h2>

      {loading ? (
        <p className="text-sm text-charcoal-400">Loading…</p>
      ) : (
        <div className="space-y-3">
          {users.map(user => {
            const isSelf    = user.id === currentUserId
            const roleValue = pendingRole[user.id] ?? user.role
            const dirty     = roleValue !== user.role

            return (
              <div
                key={user.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-charcoal-100 dark:border-charcoal-800"
              >
                {/* Avatar */}
                <div className="w-9 h-9 rounded-full bg-orange-500 text-white flex items-center justify-center text-sm font-semibold shrink-0">
                  {initials(user.name)}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm truncate">{user.name}</span>
                    {isSelf && (
                      <span className="text-xs text-charcoal-400">(you)</span>
                    )}
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${ROLE_COLORS[user.role]}`}>
                      {user.role}
                    </span>
                  </div>
                  <div className="text-xs text-charcoal-400 truncate">{user.email}</div>
                </div>

                {/* Role selector */}
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

                {/* Save role */}
                <button
                  onClick={() => saveRole(user)}
                  disabled={!dirty || isSelf || saving === user.id}
                  className="btn-primary text-xs py-1 px-3 shrink-0 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  {saving === user.id ? '…' : 'Save'}
                </button>

                {/* Delete */}
                <button
                  onClick={() => confirmDelete(user)}
                  disabled={isSelf || deleting === user.id}
                  title={isSelf ? 'Cannot delete your own account' : `Delete ${user.name}`}
                  className="text-charcoal-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
                >
                  {deleting === user.id ? '…' : '✕'}
                </button>
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
      .then(d => setAllowed(d.allow_registration ?? false))
      .catch(() => {})
  }, [])

  async function toggle() {
    const next = !allowed
    setSaving(true)
    setMsg(null)
    try {
      const updated = await adminApi.updateSettings({ allow_registration: next })
      setAllowed(updated.allow_registration)
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
        When closed, only admins can create new accounts via the API.
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
  const [keySet, setKeySet]     = useState(false)
  const [saving, setSaving]     = useState(false)
  const [saveMsg, setSaveMsg]   = useState(null)
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
// Page
// ---------------------------------------------------------------------------
export default function Admin() {
  const { user } = useAuth()

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Admin</h1>
      <UsersCard currentUserId={user?.id || ''} />
      <RegistrationCard />
      <AiProviderCard />
    </div>
  )
}
