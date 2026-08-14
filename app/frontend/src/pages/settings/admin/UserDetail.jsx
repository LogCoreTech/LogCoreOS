import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { admin as adminApi, features as featuresApi, finance as financeApi } from '../../../lib/api'
import { useAuth } from '../../../lib/auth'
import { ALL_MODULES } from '../../../lib/constants'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const ROLE_COLORS = {
  admin:  'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  member: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  guest:  'bg-charcoal-100 text-charcoal-600 dark:bg-charcoal-800 dark:text-charcoal-400',
}

function initials(name) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

export default function UserDetail() {
  const { userId } = useParams()
  const navigate = useNavigate()
  const { user: currentUser } = useAuth()
  const isSelf = userId === currentUser?.id

  const [target, setTarget] = useState(null)
  const [roles, setRoles] = useState(['member', 'guest'])
  const [enabledWs, setEnabledWs] = useState(['personal', 'business'])
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState(null)

  const [role, setRole] = useState('member')
  const [roleSaving, setRoleSaving] = useState(false)

  const [workspaces, setWorkspaces] = useState(['personal'])
  const [wsSaving, setWsSaving] = useState(false)

  const [poolEdit, setPoolEdit] = useState([])
  const [poolSaving, setPoolSaving] = useState(false)

  const [featureRole, setFeatureRole] = useState('guest')
  const [fRoleSaving, setFRoleSaving] = useState(false)

  const [wsTab, setWsTab] = useState('personal')
  const [moduleOverrides, setModuleOverrides] = useState({ personal: [], business: [] })
  const [moduleSaving, setModuleSaving] = useState(false)

  // Bank connection
  const [bankRow, setBankRow] = useState(null) // null = loading
  const [tokenInput, setTokenInput] = useState('')
  const [showTokenInput, setShowTokenInput] = useState(false)
  const [revealed, setRevealed] = useState(null)
  const [bankBusy, setBankBusy] = useState(false)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 4000)
  }

  async function load() {
    const [d, fd, settings, sfRows] = await Promise.all([
      adminApi.listUsers(),
      featuresApi.get(),
      adminApi.getSettings().catch(() => null),
      financeApi.sfConnections().catch(() => []),
    ])
    const list = d.users || d
    const found = list.find(u => u.id === userId)
    setTarget(found || null)
    setRoles(Object.keys(fd.roles || { member: {} }))
    if (settings?.enabled_workspaces) setEnabledWs(settings.enabled_workspaces)
    if (found) {
      setRole(found.role)
      setWorkspaces(found.workspaces || ['personal'])
      setPoolEdit(found.pool_edit || [])
      setFeatureRole(found.feature_role || 'guest')
      const raw = found.disabled_modules
      if (Array.isArray(raw)) setModuleOverrides({ personal: raw, business: raw })
      else if (raw && typeof raw === 'object') setModuleOverrides({ personal: raw.personal || [], business: raw.business || [] })
      else setModuleOverrides({ personal: [], business: [] })
    }
    setBankRow((Array.isArray(sfRows) ? sfRows : []).find(r => r.user_id === userId) || null)
  }

  // Reload when the viewed user changes only; `load` is redefined every
  // render and isn't memoized, so including it would refetch on every render.
  useEffect(() => {
    load().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId])

  async function saveRole() {
    setRoleSaving(true)
    try {
      const updated = await adminApi.updateUserRole(userId, role)
      setTarget(t => ({ ...t, role: updated.role }))
      flash(true, `Role updated to ${updated.role}.`)
    } catch (err) {
      flash(false, err.message || 'Failed to update role')
    } finally {
      setRoleSaving(false)
    }
  }

  function toggleWorkspace(ws) {
    setWorkspaces(prev => {
      const next = prev.includes(ws) ? prev.filter(w => w !== ws) : [...prev, ws]
      return next.length > 0 ? next : prev
    })
  }

  async function saveWorkspaces() {
    setWsSaving(true)
    try {
      await adminApi.updateWorkspaces(userId, workspaces)
      flash(true, 'Workspace access saved.')
    } catch (err) {
      flash(false, err.message || 'Failed to save workspace access')
    } finally {
      setWsSaving(false)
    }
  }

  function togglePoolEdit(pool) {
    setPoolEdit(prev => prev.includes(pool) ? prev.filter(p => p !== pool) : [...prev, pool])
  }

  async function savePoolEdit() {
    setPoolSaving(true)
    try {
      await adminApi.updatePoolEdit(userId, poolEdit)
      flash(true, 'Pool management access saved.')
    } catch (err) {
      flash(false, err.message || 'Failed to save pool access')
    } finally {
      setPoolSaving(false)
    }
  }

  async function saveFeatureRole() {
    setFRoleSaving(true)
    try {
      await featuresApi.setUserRole(userId, featureRole)
      setTarget(t => ({ ...t, feature_role: featureRole }))
      flash(true, 'Feature role updated.')
    } catch (err) {
      flash(false, err.message || 'Failed to update feature role')
    } finally {
      setFRoleSaving(false)
    }
  }

  function toggleModule(modId) {
    setModuleOverrides(prev => {
      const list = prev[wsTab] || []
      return {
        ...prev,
        [wsTab]: list.includes(modId) ? list.filter(id => id !== modId) : [...list, modId],
      }
    })
  }

  async function saveModules() {
    setModuleSaving(true)
    try {
      await adminApi.updateWorkspaceModules(userId, wsTab, moduleOverrides[wsTab] || [])
      flash(true, `${wsTab.charAt(0).toUpperCase() + wsTab.slice(1)} module access saved.`)
    } catch (err) {
      flash(false, err.message || 'Failed to save module access')
    } finally {
      setModuleSaving(false)
    }
  }

  function goToDelete() {
    if (!target) return
    navigate(`/settings/admin/users/${userId}/delete`)
  }

  // --- Bank connection actions ---
  async function bankClaim() {
    if (!tokenInput.trim()) return
    setBankBusy(true)
    try {
      await financeApi.sfClaim(userId, tokenInput.trim())
      setTokenInput('')
      setShowTokenInput(false)
      flash(true, 'Connected — the user was notified to map their accounts.')
      load()
    } catch (err) {
      flash(false, err.message || 'Claim failed')
    } finally {
      setBankBusy(false)
    }
  }

  async function bankSync() {
    setBankBusy(true)
    try {
      const r = await financeApi.sfSync(userId)
      flash(true, `Synced — ${r.created} new, ${r.skipped} already known.`)
      load()
    } catch (err) {
      flash(false, err.message || 'Sync failed')
    } finally {
      setBankBusy(false)
    }
  }

  async function bankReveal() {
    setBankBusy(true)
    try {
      const r = await financeApi.sfReveal(userId)
      setRevealed(r.access_url)
    } catch (err) {
      flash(false, err.message || 'Reveal failed')
    } finally {
      setBankBusy(false)
    }
  }

  async function bankDisconnect() {
    if (!target) return
    if (!window.confirm(`Disconnect ${target.name}'s bank connection? Their imported transactions stay.`)) return
    setBankBusy(true)
    try {
      await financeApi.sfDisconnect(userId)
      flash(true, 'Disconnected.')
      load()
    } catch (err) {
      flash(false, err.message || 'Disconnect failed')
    } finally {
      setBankBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        <SettingsPageHeader title="User" backTo="/settings/admin/users" backLabel="Users & Roles" />
        <p className="text-sm text-charcoal-400">Loading…</p>
      </div>
    )
  }

  if (!target) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        <SettingsPageHeader title="User" backTo="/settings/admin/users" backLabel="Users & Roles" />
        <p className="text-sm text-red-500">User not found.</p>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title={target.name} backTo="/settings/admin/users" backLabel="Users & Roles" />

      <div className="card p-5 flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-orange-500 text-white flex items-center justify-center text-sm font-semibold shrink-0">
          {initials(target.name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm truncate">{target.name}</span>
            {isSelf && <span className="text-xs text-charcoal-400">(you)</span>}
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${ROLE_COLORS[target.role] || ROLE_COLORS.member}`}>{target.role}</span>
          </div>
          <div className="text-xs text-charcoal-400 truncate">{target.email}</div>
        </div>
      </div>

      {msg && (
        <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</p>
      )}

      {/* Role */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Role</h2>
        <div className="flex items-center gap-2">
          <select
            value={role}
            disabled={isSelf}
            onChange={e => setRole(e.target.value)}
            className="input text-sm flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="admin">admin</option>
            <option value="member">member</option>
            <option value="guest">guest</option>
          </select>
          <button
            onClick={saveRole}
            disabled={isSelf || role === target.role || roleSaving}
            className="btn-primary text-sm px-3 py-1.5 disabled:opacity-30"
          >
            {roleSaving ? '…' : 'Save'}
          </button>
        </div>
        {isSelf && <p className="text-xs text-charcoal-400 mt-2">You cannot change your own role.</p>}
      </div>

      {target.role !== 'admin' && (
        <>
          {/* Workspace access */}
          <div className="card p-5">
            <h2 className="font-semibold mb-3">Workspace Access</h2>
            <div className="flex items-center gap-4 mb-3">
              {['personal', 'business'].filter(ws => enabledWs.includes(ws)).map(ws => (
                <label key={ws} className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" checked={workspaces.includes(ws)} onChange={() => toggleWorkspace(ws)} className="accent-orange-500 w-4 h-4" />
                  <span className="text-sm capitalize">{ws}</span>
                </label>
              ))}
            </div>
            <button onClick={saveWorkspaces} disabled={wsSaving} className="btn-primary text-sm px-3 py-1.5 disabled:opacity-30">
              {wsSaving ? '…' : 'Save'}
            </button>
          </div>

          {/* Pool management */}
          <div className="card p-5">
            <h2 className="font-semibold mb-1">Can Manage</h2>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
              Allow this user to add &amp; edit events and add &amp; assign tasks in the shared pool.
            </p>
            <div className="flex items-center gap-4 mb-3">
              {[
                { pool: 'household', label: 'Household', ws: 'personal' },
                { pool: 'team',      label: 'Team',      ws: 'business' },
              ].filter(p => enabledWs.includes(p.ws)).map(p => (
                <label key={p.pool} className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" checked={poolEdit.includes(p.pool)} onChange={() => togglePoolEdit(p.pool)} className="accent-orange-500 w-4 h-4" />
                  <span className="text-sm">{p.label}</span>
                </label>
              ))}
            </div>
            <button onClick={savePoolEdit} disabled={poolSaving} className="btn-primary text-sm px-3 py-1.5 disabled:opacity-30">
              {poolSaving ? '…' : 'Save'}
            </button>
          </div>

          {/* Feature role */}
          <div className="card p-5">
            <h2 className="font-semibold mb-1">Feature Role</h2>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
              Controls which modules this user can see. Edit role definitions from the Users &amp;
              Roles list.
            </p>
            <div className="flex items-center gap-2">
              <select value={featureRole} onChange={e => setFeatureRole(e.target.value)} className="input text-sm flex-1">
                {roles.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              <button onClick={saveFeatureRole} disabled={featureRole === (target.feature_role || 'guest') || fRoleSaving} className="btn-primary text-sm px-3 py-1.5 disabled:opacity-30">
                {fRoleSaving ? '…' : 'Save'}
              </button>
            </div>
          </div>

          {/* Module overrides */}
          <div className="card p-5">
            <h2 className="font-semibold mb-3">Module Restrictions</h2>
            <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1 mb-3">
              {['personal', 'business'].map(ws => (
                <button
                  key={ws}
                  onClick={() => setWsTab(ws)}
                  className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                    wsTab === ws
                      ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                      : 'text-charcoal-500 dark:text-charcoal-400'
                  }`}
                >
                  {ws}
                </button>
              ))}
            </div>
            <div className="space-y-1 mb-3">
              {ALL_MODULES.map(mod => {
                const disabled = (moduleOverrides[wsTab] || []).includes(mod.id)
                return (
                  <label key={mod.id} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 cursor-pointer">
                    <input type="checkbox" checked={!disabled} onChange={() => toggleModule(mod.id)} className="accent-orange-500 w-4 h-4" />
                    <span className="text-sm leading-none">{mod.icon}</span>
                    <span className="text-sm">{mod.label}</span>
                  </label>
                )
              })}
            </div>
            <button onClick={saveModules} disabled={moduleSaving} className="btn-primary text-sm px-3 py-1.5 w-full capitalize">
              {moduleSaving ? '…' : `Save ${wsTab} overrides`}
            </button>
          </div>
        </>
      )}

      {/* Bank connection */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Bank Connection</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          SimpleFIN bank sync. The user connects at <span className="font-mono">bridge.simplefin.org</span>,
          sends you their setup token, and you connect it below. Tokens are read-only.
        </p>
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <div className={`w-2 h-2 rounded-full shrink-0 ${bankRow?.connected ? (bankRow?.last_error ? 'bg-yellow-500' : 'bg-green-500') : 'bg-charcoal-300'}`} />
          {bankRow?.connected ? (
            <span className="text-xs text-charcoal-500 dark:text-charcoal-400">
              {bankRow.mapped_accounts} mapped{bankRow.last_sync ? ` · synced ${new Date(bankRow.last_sync).toLocaleDateString()}` : ' · never synced'}
            </span>
          ) : (
            <span className="text-xs text-charcoal-400">not connected</span>
          )}
        </div>
        {bankRow?.last_error && <p className="text-xs text-red-500 mb-2">{bankRow.last_error}</p>}

        {showTokenInput ? (
          <div className="flex gap-2 mb-2">
            <input className="input flex-1" placeholder="Paste SimpleFIN setup token" value={tokenInput} onChange={e => setTokenInput(e.target.value)} autoFocus />
            <button onClick={bankClaim} disabled={bankBusy || !tokenInput.trim()} className="btn-primary shrink-0 text-sm">
              {bankBusy ? '…' : 'Connect'}
            </button>
            <button onClick={() => { setShowTokenInput(false); setTokenInput('') }} className="btn-ghost shrink-0 text-sm">Cancel</button>
          </div>
        ) : (
          <div className="flex gap-1.5 flex-wrap">
            <button onClick={() => setShowTokenInput(true)} className="btn-ghost text-xs">
              {bankRow?.connected ? 'Replace token' : '＋ Connect'}
            </button>
            {bankRow?.connected && (
              <>
                <button onClick={bankSync} disabled={bankBusy} className="btn-ghost text-xs">{bankBusy ? 'Syncing…' : 'Sync now'}</button>
                <button onClick={bankReveal} disabled={bankBusy} className="btn-ghost text-xs">Reveal</button>
                <button onClick={bankDisconnect} disabled={bankBusy} className="btn-ghost text-xs text-red-500">Disconnect</button>
              </>
            )}
          </div>
        )}

        {revealed && (
          <div className="text-xs bg-charcoal-100 dark:bg-charcoal-800 rounded p-2 break-all mt-2">
            <p className="text-charcoal-500 dark:text-charcoal-400 mb-1">Access URL (treat like a password — read-only bank data):</p>
            <p className="font-mono">{revealed}</p>
            <button onClick={() => setRevealed(null)} className="text-orange-500 mt-1">Hide</button>
          </div>
        )}
      </div>

      {/* Delete */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1 text-red-500">Danger Zone</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Permanently delete this user and their Brain folder. This cannot be undone.
        </p>
        <button
          onClick={goToDelete}
          disabled={isSelf}
          title={isSelf ? 'Cannot delete your own account' : ''}
          className="text-sm text-red-500 hover:text-red-600 font-medium disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Delete User
        </button>
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
