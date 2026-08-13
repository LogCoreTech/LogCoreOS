import { useEffect, useState } from 'react'
import { features as featuresApi } from '../../../lib/api'
import { ALL_MODULES } from '../../../lib/constants'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

export default function RoleDefinitions() {
  const [roles, setRoles] = useState([])
  const [roleMods, setRoleMods] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [expandedRole, setExpandedRole] = useState(null)
  const [msg, setMsg] = useState(null)
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
    const mods = {}
    const names = []
    for (const [name, map] of Object.entries(d.roles || {})) {
      mods[name] = { ...map }
      names.push(name)
    }
    setRoleMods(mods)
    setRoles(names)
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
      setRoles(prev => prev.filter(r => r !== name))
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
      const result = await featuresApi.createRole(trimmed, modMap)
      // Use the server's canonical name/modules (it strips+lowercases the name) rather
      // than our own local `trimmed` — otherwise this role's local-state key can end up
      // differently cased than what's actually persisted, and every subsequent edit/delete
      // on it 404s until the page is refreshed.
      setRoleMods(prev => ({ ...prev, [result.name]: result.modules }))
      setRoles(prev => [...prev, result.name])
      setNewRoleName('')
      setNewRoleMods({})
      setShowCreate(false)
      flash(true, `Role "${result.name}" created.`)
    } catch (err) {
      flash(false, err.message || 'Failed to create role')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Role Definitions" backTo="/settings/admin/users" backLabel="Users & Roles" />

      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Feature Roles</h2>
          <button onClick={() => setShowCreate(o => !o)} className="btn-primary text-sm py-1 px-3">
            {showCreate ? 'Cancel' : '+ New Role'}
          </button>
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4 break-words">
          Define which modules each role can access. Assign roles to users from their own page.
        </p>

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

        {loading ? (
          <p className="text-sm text-charcoal-400">Loading…</p>
        ) : (
          <div className="space-y-2">
            {roles.map(name => {
              const isBuiltIn = name === 'member' || name === 'guest'
              const mods = roleMods[name] || {}
              const open = expandedRole === name
              return (
                <div key={name} className="rounded-lg border border-charcoal-100 dark:border-charcoal-800">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button
                      onClick={() => setExpandedRole(open ? null : name)}
                      className="flex-1 min-w-0 flex items-center gap-2 text-left"
                    >
                      <span className="text-xs text-charcoal-400 shrink-0">{open ? '▾' : '▸'}</span>
                      <span className="font-medium text-sm truncate">{name}</span>
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
        )}

        {msg && (
          <p className={`text-sm mt-3 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
