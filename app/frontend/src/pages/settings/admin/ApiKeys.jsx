import { useEffect, useRef, useState } from 'react'
import { admin as adminApi } from '../../../lib/api'
import { useToast } from '../../../lib/toast'
import useEscapeToClose from '../../../lib/useEscapeToClose'
import useFocusTrap from '../../../lib/useFocusTrap'
import useScrollLock from '../../../lib/useScrollLock'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'
import SimpleFormModal from '../../../components/SimpleFormModal'
import ConfirmDialog from '../../../components/ConfirmDialog'

// Personal API keys — admin-only (docs/MEMORY.md 2026-10-25). A key acts as
// the admin who created it, limited to the scopes picked here. The full key
// is shown exactly once, right after creation.

const STATUS_STYLES = {
  active: 'text-green-600 dark:text-green-400',
  expired: 'text-charcoal-400',
  revoked: 'text-red-500',
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString() : '—'
}

export default function ApiKeys() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [enabled, setEnabled] = useState(true)
  const [savingSwitch, setSavingSwitch] = useState(false)

  const [modal, setModal] = useState(null) // 'create' | 'reveal' | null
  const modalCardRef = useRef(null)
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState([])
  const [workspace, setWorkspace] = useState('personal')
  const [expiresDays, setExpiresDays] = useState('90')
  const [password, setPassword] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [newKey, setNewKey] = useState('')
  const [copied, setCopied] = useState(false)
  const [revoking, setRevoking] = useState(null)

  useEscapeToClose(() => closeModal())
  useFocusTrap(modalCardRef, !!modal)
  useScrollLock(!!modal)

  function load() {
    adminApi.listApiKeys()
      .then(d => { setData(d); setEnabled(d.enabled) })
      .catch(err => toast.error(err.message || 'Failed to load API keys'))
  }

  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps

  function closeModal() {
    setModal(null)
    setName('')
    setScopes([])
    setWorkspace('personal')
    setExpiresDays('90')
    setPassword('')
    setCreateError('')
    setNewKey('')
    setCopied(false)
  }

  async function toggleEnabled() {
    setSavingSwitch(true)
    try {
      const updated = await adminApi.updateSettings({ api_keys_enabled: !enabled })
      setEnabled(updated.api_keys_enabled)
      toast.success(updated.api_keys_enabled ? 'API keys turned on.' : 'API keys turned off — every key is rejected until turned back on.')
    } catch (err) {
      toast.error(err.message || 'Failed to save')
    } finally {
      setSavingSwitch(false)
    }
  }

  function toggleScope(scope) {
    setScopes(s => (s.includes(scope) ? s.filter(x => x !== scope) : [...s, scope]))
  }

  async function createKey() {
    setCreateError('')
    setCreating(true)
    try {
      const result = await adminApi.createApiKey({
        name,
        scopes,
        workspace,
        expires_days: expiresDays ? Number(expiresDays) : null,
        current_password: password,
      })
      setNewKey(result.key)
      setPassword('')
      setModal('reveal')
      load()
    } catch (err) {
      setCreateError(err.message || 'Failed to create key')
    } finally {
      setCreating(false)
    }
  }

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(newKey)
      setCopied(true)
    } catch { /* clipboard permission denied — the text is still selectable */ }
  }

  async function revokeKey() {
    const key = revoking
    setRevoking(null)
    try {
      await adminApi.revokeApiKey(key.id)
      toast.success(`Revoked “${key.name}”.`)
      load()
    } catch (err) {
      toast.error(err.message || 'Failed to revoke key')
    }
  }

  const scopeEntries = Object.entries(data?.scopes || {})

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="API Keys" backTo="/settings/admin" backLabel="Admin Settings" />

      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        Let outside tools reach LogCore — a website lead form, or an AI app over MCP. A key acts
        as <em>you</em>, limited to the scopes you pick, and stops working the moment it&apos;s
        revoked, expires, or you&apos;re no longer an admin. See Help → API Keys &amp; MCP for setup.
      </p>

      <div className="card p-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Allow API keys</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
            Off rejects every key immediately, without deleting any.
          </p>
        </div>
        <button
          role="switch"
          aria-checked={enabled}
          aria-label="Allow API keys"
          disabled={savingSwitch || !data}
          onClick={toggleEnabled}
          className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${enabled ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-700'} ${savingSwitch ? 'opacity-50' : ''}`}
        >
          <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${enabled ? 'translate-x-5' : ''}`} />
        </button>
      </div>

      <div className="card">
        <div className="flex items-center justify-between p-4 border-b border-charcoal-100 dark:border-charcoal-800">
          <h2 className="font-semibold">Keys</h2>
          <button onClick={() => setModal('create')} disabled={!enabled} className="btn-primary text-sm">
            + New Key
          </button>
        </div>
        <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
          {!data ? (
            <p className="text-sm text-charcoal-400 p-4">Loading…</p>
          ) : data.keys.length === 0 ? (
            <p className="text-sm text-charcoal-400 p-4">No API keys yet.</p>
          ) : (
            data.keys.map(k => (
              <div key={k.id} className="p-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {k.name} <span className={`text-xs font-normal ${STATUS_STYLES[k.status]}`}>· {k.status}</span>
                  </p>
                  <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                    {k.scopes.join(', ')} · {k.workspace} · owner {k.user_name}
                  </p>
                  <p className="text-xs text-charcoal-400">
                    lcos_{k.id}_… · created {formatDate(k.created_at)} · expires {k.expires_at ? formatDate(k.expires_at) : 'never'} · last used {formatDate(k.last_used_at)}
                  </p>
                </div>
                {k.status === 'active' && (
                  <button onClick={() => setRevoking(k)} className="btn-ghost text-sm text-red-500 shrink-0">
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {modal === 'create' && (
        <SimpleFormModal
          cardRef={modalCardRef}
          title="New API Key"
          onClose={closeModal}
          onCancel={closeModal}
          onSubmit={createKey}
          submitLabel="Create Key"
          submitBusyLabel="Creating…"
          busy={creating}
          submitDisabled={creating || !name.trim() || scopes.length === 0 || !password}
          error={createError}
        >
          <div className="space-y-3 mb-3">
            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="api-key-name">Name</label>
              <input
                id="api-key-name"
                value={name}
                onChange={e => setName(e.target.value)}
                maxLength={60}
                placeholder="e.g. Website lead form"
                className="input w-full text-base"
              />
            </div>
            <fieldset>
              <legend className="block text-sm font-medium mb-1">Scopes</legend>
              <div className="space-y-1.5">
                {scopeEntries.map(([scope, desc]) => (
                  <label key={scope} className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope)}
                      onChange={() => toggleScope(scope)}
                      className="mt-1 accent-orange-500"
                    />
                    <span>
                      <span className="font-mono text-xs">{scope}</span>
                      <span className="block text-xs text-charcoal-400">{desc}</span>
                    </span>
                  </label>
                ))}
              </div>
              {scopes.includes('mcp:write') && (
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                  mcp:write lets the connected app create and change your data without asking
                  in LogCore first — only your MCP app&apos;s own approval prompt stands in between.
                </p>
              )}
            </fieldset>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-sm font-medium mb-1" htmlFor="api-key-ws">Workspace</label>
                <select id="api-key-ws" value={workspace} onChange={e => setWorkspace(e.target.value)} className="input w-full text-base">
                  <option value="personal">Personal</option>
                  <option value="business">Business</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1" htmlFor="api-key-exp">Expires</label>
                <select id="api-key-exp" value={expiresDays} onChange={e => setExpiresDays(e.target.value)} className="input w-full text-base">
                  {(data?.expiry_days || [30, 90, 365]).map(d => (
                    <option key={d} value={String(d)}>In {d} days</option>
                  ))}
                  <option value="">Never</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="api-key-pw">Your current password</label>
              <input
                id="api-key-pw"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                className="input w-full text-base"
              />
            </div>
          </div>
        </SimpleFormModal>
      )}

      {modal === 'reveal' && (
        <div className="modal-overlay">
          <div ref={modalCardRef} className="modal-card p-5 max-w-sm">
            <h2 className="font-semibold mb-2">Copy your new key</h2>
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-3">
              This is the only time it will be shown. Store it somewhere safe — if you lose it,
              revoke it and create a new one.
            </p>
            <code className="block p-3 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 text-xs break-all select-all mb-3">
              {newKey}
            </code>
            <div className="flex gap-2">
              <button onClick={copyKey} className="btn-ghost flex-1">{copied ? 'Copied ✓' : 'Copy'}</button>
              <button onClick={closeModal} className="btn-primary flex-1">Done</button>
            </div>
          </div>
        </div>
      )}

      {revoking && (
        <ConfirmDialog
          title="Revoke API key?"
          message={`“${revoking.name}” stops working immediately. Anything using it will start getting errors.`}
          confirmLabel="Revoke"
          danger
          onConfirm={revokeKey}
          onCancel={() => setRevoking(null)}
        />
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
