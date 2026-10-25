import { useEffect, useRef, useState } from 'react'
import { admin as adminApi } from '../../../lib/api'
import { useToast } from '../../../lib/toast'
import useEscapeToClose from '../../../lib/useEscapeToClose'
import useFocusTrap from '../../../lib/useFocusTrap'
import useScrollLock from '../../../lib/useScrollLock'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'
import ConfirmDialog from '../../../components/ConfirmDialog'

// API keys — admin-only (docs/MEMORY.md 2026-10-25), two kinds:
// - integration: belongs to the instance (not a person), pinned to a shared
//   contacts list; can only send leads in.
// - mcp: an AI app acting as the admin who made it, limited to the modules /
//   tools picked here (editable later). The full key is shown exactly once.

const STATUS_STYLES = {
  active: 'text-green-600 dark:text-green-400',
  expired: 'text-charcoal-400',
  revoked: 'text-red-500',
}

const TARGET_LABELS = { _team: 'Team contacts', _household: 'Household contacts' }
const LEVELS = [
  { value: 'none', label: 'None' },
  { value: 'read', label: 'Read' },
  { value: 'write', label: 'Read + write' },
]

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString() : '—'
}

function groupAllows(level, tool) {
  return level === 'write' || (level === 'read' && tool.read_only)
}

function toolAllowed(group, tool, access, overrides) {
  if (tool.name in overrides) return overrides[tool.name]
  return groupAllows(access[group.id] || 'none', tool)
}

function accessSummary(key, catalog) {
  const labels = Object.fromEntries((catalog || []).map(g => [g.id, g.label]))
  const parts = Object.entries(key.access || {}).map(
    ([g, level]) => `${labels[g] || g}: ${level === 'write' ? 'read + write' : 'read'}`
  )
  const n = Object.keys(key.tool_overrides || {}).length
  if (n) parts.push(`${n} tool exception${n === 1 ? '' : 's'}`)
  return parts.join(' · ') || 'no tools'
}

// Per-module access (none / read / read + write) with an expandable per-tool
// checklist. A tick that differs from the module's own setting is stored as
// an override; one that matches it is dropped, so module settings keep
// covering tools a module adds later.
function ToolAccessPicker({ catalog, access, overrides, onChange }) {
  const [open, setOpen] = useState({})

  function setLevel(groupId, level) {
    const next = { ...access }
    if (level === 'none') delete next[groupId]
    else next[groupId] = level
    // Drop overrides that now match the new module default.
    const group = catalog.find(g => g.id === groupId)
    const nextOverrides = { ...overrides }
    for (const tool of group.tools) {
      if (tool.name in nextOverrides && nextOverrides[tool.name] === groupAllows(level, tool)) {
        delete nextOverrides[tool.name]
      }
    }
    onChange(next, nextOverrides)
  }

  function toggleTool(group, tool) {
    const want = !toolAllowed(group, tool, access, overrides)
    const next = { ...overrides }
    if (want === groupAllows(access[group.id] || 'none', tool)) delete next[tool.name]
    else next[tool.name] = want
    onChange(access, next)
  }

  return (
    <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800 border border-charcoal-200 dark:border-charcoal-700 rounded-lg">
      {catalog.map(group => {
        const level = access[group.id] || 'none'
        const custom = group.tools.some(t => t.name in overrides)
        const count = group.tools.filter(t => toolAllowed(group, t, access, overrides)).length
        return (
          <div key={group.id} className="p-2.5">
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setOpen(o => ({ ...o, [group.id]: !o[group.id] }))}
                aria-expanded={!!open[group.id]}
                className="text-left min-w-0"
              >
                <span className="block text-sm font-medium truncate">
                  {open[group.id] ? '▾' : '▸'} {group.label}
                </span>
                <span className="block text-xs text-charcoal-400">
                  {count} of {group.tools.length} tools{custom ? ' · customized' : ''}
                </span>
              </button>
              <select
                value={level}
                onChange={e => setLevel(group.id, e.target.value)}
                aria-label={`${group.label} access`}
                className="input text-base w-36 shrink-0"
              >
                {LEVELS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
            </div>
            {open[group.id] && (
              <div className="mt-2 space-y-1.5 pl-4">
                {group.tools.map(tool => (
                  <label key={tool.name} className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={toolAllowed(group, tool, access, overrides)}
                      onChange={() => toggleTool(group, tool)}
                      className="mt-1 accent-orange-500"
                    />
                    <span className="min-w-0">
                      <span className="font-mono text-xs">{tool.name}</span>
                      {!tool.read_only && <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">changes data</span>}
                      <span className="block text-xs text-charcoal-400">{tool.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

const EMPTY_FORM = {
  kind: 'integration',
  name: '',
  target: '_team',
  workspace: 'personal',
  expiresDays: '90',
  access: {},
  overrides: {},
  password: '',
}

export default function ApiKeys() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [enabled, setEnabled] = useState(true)
  const [savingSwitch, setSavingSwitch] = useState(false)

  const [modal, setModal] = useState(null) // 'create' | 'reveal' | 'edit' | null
  const modalCardRef = useRef(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')
  const [newKey, setNewKey] = useState('')
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(null)
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
    setForm(EMPTY_FORM)
    setFormError('')
    setNewKey('')
    setCopied(false)
    setEditing(null)
  }

  function openCreate() {
    const ws = data?.workspaces || []
    setForm({
      ...EMPTY_FORM,
      target: ws.includes('business') ? '_team' : '_household',
      workspace: ws.includes('personal') ? 'personal' : ws[0] || 'personal',
    })
    setModal('create')
  }

  function update(fields) {
    setForm(f => ({ ...f, ...fields }))
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

  async function createKey() {
    setFormError('')
    setBusy(true)
    try {
      const body = {
        kind: form.kind,
        name: form.name,
        expires_days: form.expiresDays ? Number(form.expiresDays) : null,
        current_password: form.password,
      }
      if (form.kind === 'integration') body.target = form.target
      else Object.assign(body, { workspace: form.workspace, access: form.access, tool_overrides: form.overrides })
      const result = await adminApi.createApiKey(body)
      setNewKey(result.key)
      update({ password: '' })
      setModal('reveal')
      load()
    } catch (err) {
      setFormError(err.message || 'Failed to create key')
    } finally {
      setBusy(false)
    }
  }

  function openEdit(key) {
    setEditing(key)
    setForm({ ...EMPTY_FORM, name: key.name, access: key.access || {}, overrides: key.tool_overrides || {} })
    setModal('edit')
  }

  async function saveEdit() {
    setFormError('')
    setBusy(true)
    try {
      const body = { name: form.name }
      if (editing.kind === 'mcp') Object.assign(body, { access: form.access, tool_overrides: form.overrides })
      await adminApi.updateApiKey(editing.id, body)
      toast.success(`Saved “${form.name}”.`)
      closeModal()
      load()
    } catch (err) {
      setFormError(err.message || 'Failed to save')
    } finally {
      setBusy(false)
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

  const catalog = data?.mcp_catalog || []
  const grantsSomething = catalog.some(g => g.tools.some(t => toolAllowed(g, t, form.access, form.overrides)))
  const canCreate = form.name.trim() && form.password && (form.kind === 'integration' || grantsSomething)

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="API Keys" backTo="/settings/admin" backLabel="Admin Settings" />

      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        Let outside tools reach LogCore. A <strong>website / integration</strong> key belongs to
        this instance and can only send leads into a shared contacts list. An <strong>AI app
        (MCP)</strong> key acts as you, limited to the modules and tools you pick. See Help → API
        Keys &amp; MCP for setup.
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
          <button onClick={openCreate} disabled={!enabled || !data} className="btn-primary text-sm">
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
                    {k.name}{' '}
                    <span className="text-xs font-normal text-charcoal-400">
                      · {k.kind === 'mcp' ? 'AI app (MCP)' : 'Integration'}
                    </span>{' '}
                    <span className={`text-xs font-normal ${STATUS_STYLES[k.status]}`}>· {k.status}</span>
                  </p>
                  <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                    {k.kind === 'mcp'
                      ? `${accessSummary(k, catalog)} · ${k.workspace} · acts as ${k.user_name}`
                      : `Sends leads to ${TARGET_LABELS[k.target] || k.target}`}
                  </p>
                  <p className="text-xs text-charcoal-400">
                    lcos_{k.id}_… · created {formatDate(k.created_at)} by {k.created_by_name} · expires {k.expires_at ? formatDate(k.expires_at) : 'never'} · last used {formatDate(k.last_used_at)}
                  </p>
                </div>
                {k.status === 'active' && (
                  <div className="flex flex-col gap-1 shrink-0">
                    <button onClick={() => openEdit(k)} className="btn-ghost text-sm">
                      {k.kind === 'mcp' ? 'Edit access' : 'Rename'}
                    </button>
                    <button onClick={() => setRevoking(k)} className="btn-ghost text-sm text-red-500">
                      Revoke
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {(modal === 'create' || modal === 'edit') && (
        <div className="modal-overlay">
          <div ref={modalCardRef} className="modal-card p-5 max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">{modal === 'create' ? 'New API Key' : `Edit “${editing?.name}”`}</h2>
              <button onClick={closeModal} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
            </div>

            <div className="space-y-4 mb-3">
              {modal === 'create' && (
                <fieldset>
                  <legend className="block text-sm font-medium mb-1">What&apos;s it for?</legend>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { value: 'integration', label: 'Website / integration', desc: 'Send leads in. Belongs to this instance.' },
                      { value: 'mcp', label: 'AI app (MCP)', desc: 'Claude or another AI app, acting as you.' },
                    ].map(opt => (
                      <label
                        key={opt.value}
                        className={`p-2.5 rounded-lg border cursor-pointer ${form.kind === opt.value ? 'border-orange-500 bg-orange-500/5' : 'border-charcoal-200 dark:border-charcoal-700'}`}
                      >
                        <input
                          type="radio"
                          name="api-key-kind"
                          checked={form.kind === opt.value}
                          onChange={() => update({ kind: opt.value })}
                          className="sr-only"
                        />
                        <span className="block text-sm font-medium">{opt.label}</span>
                        <span className="block text-xs text-charcoal-400">{opt.desc}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}

              <div>
                <label className="block text-sm font-medium mb-1" htmlFor="api-key-name">Name</label>
                <input
                  id="api-key-name"
                  value={form.name}
                  onChange={e => update({ name: e.target.value })}
                  maxLength={60}
                  placeholder={form.kind === 'integration' ? 'e.g. Website lead form' : 'e.g. Claude on my laptop'}
                  className="input w-full text-base"
                />
              </div>

              {modal === 'create' && form.kind === 'integration' && (
                <div>
                  <label className="block text-sm font-medium mb-1" htmlFor="api-key-target">Leads go to</label>
                  <select id="api-key-target" value={form.target} onChange={e => update({ target: e.target.value })} className="input w-full text-base">
                    {(data?.workspaces || []).includes('business') && <option value="_team">Team contacts (business)</option>}
                    {(data?.workspaces || []).includes('personal') && <option value="_household">Household contacts (personal)</option>}
                  </select>
                  <p className="text-xs text-charcoal-400 mt-1">
                    Fixed for this key — the website can&apos;t send leads anywhere else. Follow-up reminders go to every admin.
                  </p>
                </div>
              )}

              {modal === 'create' && form.kind === 'mcp' && (
                <div>
                  <label className="block text-sm font-medium mb-1" htmlFor="api-key-ws">Workspace</label>
                  <select id="api-key-ws" value={form.workspace} onChange={e => update({ workspace: e.target.value })} className="input w-full text-base">
                    {(data?.workspaces || []).map(w => (
                      <option key={w} value={w}>{w === 'business' ? 'Business' : 'Personal'}</option>
                    ))}
                  </select>
                </div>
              )}

              {(form.kind === 'mcp' && modal === 'create') || editing?.kind === 'mcp' ? (
                <div>
                  <p className="block text-sm font-medium mb-1">What it can use</p>
                  <p className="text-xs text-charcoal-400 mb-2">
                    Set each module, or tap one to pick individual tools. Tools marked “changes data”
                    run without asking in LogCore — only your AI app&apos;s own prompt stands in between.
                  </p>
                  <ToolAccessPicker
                    catalog={catalog}
                    access={form.access}
                    overrides={form.overrides}
                    onChange={(access, overrides) => update({ access, overrides })}
                  />
                </div>
              ) : null}

              {modal === 'create' && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1" htmlFor="api-key-exp">Expires</label>
                    <select id="api-key-exp" value={form.expiresDays} onChange={e => update({ expiresDays: e.target.value })} className="input w-full text-base">
                      {(data?.expiry_days || [30, 90, 365]).map(d => (
                        <option key={d} value={String(d)}>In {d} days</option>
                      ))}
                      <option value="">Never</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1" htmlFor="api-key-pw">Your current password</label>
                    <input
                      id="api-key-pw"
                      type="password"
                      value={form.password}
                      onChange={e => update({ password: e.target.value })}
                      autoComplete="current-password"
                      className="input w-full text-base"
                    />
                  </div>
                </>
              )}
            </div>

            {formError && <p className="text-red-500 text-sm mb-2">{formError}</p>}
            <div className="flex gap-2">
              <button onClick={closeModal} className="btn-ghost flex-1">Cancel</button>
              {modal === 'create' ? (
                <button onClick={createKey} disabled={busy || !canCreate} className="btn-primary flex-1">
                  {busy ? 'Creating…' : 'Create Key'}
                </button>
              ) : (
                <button
                  onClick={saveEdit}
                  disabled={busy || !form.name.trim() || (editing?.kind === 'mcp' && !grantsSomething)}
                  className="btn-primary flex-1"
                >
                  {busy ? 'Saving…' : 'Save'}
                </button>
              )}
            </div>
          </div>
        </div>
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
