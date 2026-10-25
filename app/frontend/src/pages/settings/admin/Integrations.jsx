import { useEffect, useRef, useState } from 'react'
import { admin as adminApi } from '../../../lib/api'
import { useToast } from '../../../lib/toast'
import useEscapeToClose from '../../../lib/useEscapeToClose'
import useFocusTrap from '../../../lib/useFocusTrap'
import useScrollLock from '../../../lib/useScrollLock'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'
import ConfirmDialog from '../../../components/ConfirmDialog'

// Admin → Integrations & MCP (docs/MEMORY.md 2026-10-25). Two kinds of key:
// - Integration: belongs to the instance (not a person), pinned to a shared
//   contacts list, can only send leads in. Shown to the admin exactly once.
// - MCP: lets an AI app act as ONE user the admin picks, limited to the tools
//   picked here. It's an invitation — that user is notified, reviews the
//   tools, and accepts; the key is generated then and shown only to them.
//   Widening an accepted key's tools waits for the user's approval again.

const STATUS_STYLES = {
  active: 'text-green-600 dark:text-green-400',
  pending: 'text-amber-600 dark:text-amber-400',
  expired: 'text-charcoal-400',
  declined: 'text-charcoal-400',
  revoked: 'text-red-500',
}

const STATUS_LABELS = { pending: 'waiting for them to accept' }

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

const WS_LABELS = { business: 'Business', personal: 'Personal' }

function grantSummary(grant, labels) {
  const parts = Object.entries(grant?.access || {}).map(
    ([g, level]) => `${labels[g] || g} ${level === 'write' ? 'read + write' : 'read'}`
  )
  const n = Object.keys(grant?.tool_overrides || {}).length
  if (n) parts.push(`${n} tool exception${n === 1 ? '' : 's'}`)
  return parts.join(', ') || 'no tools'
}

function accessSummary(key, catalog) {
  const labels = Object.fromEntries((catalog || []).map(g => [g.id, g.label]))
  const parts = Object.entries(key.grants || {}).map(
    ([ws, grant]) => `${WS_LABELS[ws] || ws}: ${grantSummary(grant, labels)}`
  )
  return parts.join(' · ') || 'no tools'
}

// The catalog groups this person can actually use in one workspace — core
// always, modules only if they're not disabled for them there.
function catalogFor(catalog, user, ws) {
  const disabled = new Set(user?.disabled_modules?.[ws] || [])
  return (catalog || []).filter(g => g.id === 'core' || !disabled.has(g.id))
}

function grantAllows(catalog, grant) {
  return catalog.some(g => g.tools.some(t => toolAllowed(g, t, grant?.access || {}, grant?.tool_overrides || {})))
}

// The fields + a ready-to-copy request for the lead intake endpoint, built
// server-side from the endpoint's own model (services/intake_spec.py).
function IntakeHelp({ spec, apiKey }) {
  if (!spec) return null
  const url = `${window.location.origin}${spec.path}`
  const curl = [
    `curl -X POST ${url} \\`,
    `  -H "Authorization: Bearer ${apiKey || '<your integration key>'}" \\`,
    '  -H "Content-Type: application/json" \\',
    `  -d '${JSON.stringify(spec.example)}'`,
  ].join('\n')
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium mb-1">Send each lead as</p>
        <code className="block p-2 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 text-xs break-all">
          POST {url}
        </code>
      </div>
      <div className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg divide-y divide-charcoal-100 dark:divide-charcoal-800">
        {spec.fields.map(f => (
          <div key={f.name} className="p-2">
            <p className="text-xs">
              <span className="font-mono font-medium">{f.name}</span>
              <span className="text-charcoal-400"> · {f.type}</span>
              {f.required && <span className="text-orange-600 dark:text-orange-400"> · required</span>}
            </p>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400">{f.description}</p>
          </div>
        ))}
      </div>
      <div>
        <p className="text-sm font-medium mb-1">Example</p>
        <pre className="p-2 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 text-xs whitespace-pre-wrap break-all select-all">{curl}</pre>
      </div>
      <p className="text-xs text-charcoal-400">
        The same field list is at GET {spec.path}, for tools that look it up themselves.
      </p>
    </div>
  )
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
  userId: '',
  grants: {},
  activeWs: 'business',
  expiresDays: '90',
  password: '',
}

function KeyRow({ k, catalog, onEdit, onRevoke, onHelp }) {
  const live = k.status === 'active' || k.status === 'pending'
  return (
    <div className="p-4 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">
          {k.name}{' '}
          <span className={`text-xs font-normal ${STATUS_STYLES[k.status]}`}>
            · {STATUS_LABELS[k.status] || k.status}
          </span>
        </p>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
          {k.kind === 'mcp'
            ? `Acts as ${k.user_name} · ${accessSummary(k, catalog)}`
            : `Sends leads to ${TARGET_LABELS[k.target] || k.target}`}
        </p>
        {k.proposed_access && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            More tools proposed — waiting for {k.user_name} to approve
          </p>
        )}
        <p className="text-xs text-charcoal-400">
          {k.status === 'pending' ? 'not accepted yet' : `lcos_${k.id}_…`} · set up {formatDate(k.created_at)} by {k.created_by_name}
          {k.status === 'active' && ` · expires ${k.expires_at ? formatDate(k.expires_at) : 'never'} · last used ${formatDate(k.last_used_at)}`}
        </p>
      </div>
      {live && (
        <div className="flex flex-col gap-1 shrink-0">
          {k.kind === 'integration' && (
            <button onClick={() => onHelp(k)} className="btn-ghost text-sm">How to send</button>
          )}
          <button onClick={() => onEdit(k)} className="btn-ghost text-sm">
            {k.kind === 'mcp' ? 'Edit tools' : 'Rename'}
          </button>
          <button onClick={() => onRevoke(k)} className="btn-ghost text-sm text-red-500">
            {k.status === 'pending' ? 'Cancel' : 'Revoke'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function Integrations() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [enabled, setEnabled] = useState(true)
  const [savingSwitch, setSavingSwitch] = useState(false)

  const [modal, setModal] = useState(null) // 'create' | 'reveal' | 'edit' | 'help' | null
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
      .catch(err => toast.error(err.message || 'Failed to load keys'))
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

  function openCreate(kind, userId = '') {
    const ws = data?.workspaces || []
    const user = (data?.users || []).find(u => u.id === userId)
    setForm({
      ...EMPTY_FORM,
      kind,
      userId,
      target: ws.includes('business') ? '_team' : '_household',
      activeWs: user?.workspaces?.[0] || 'business',
    })
    setModal('create')
  }

  function update(fields) {
    setForm(f => ({ ...f, ...fields }))
  }

  function pickUser(userId) {
    const user = (data?.users || []).find(u => u.id === userId)
    const ws = user?.workspaces || []
    // Drop grants for workspaces the new person doesn't have.
    const grants = Object.fromEntries(Object.entries(form.grants).filter(([w]) => ws.includes(w)))
    update({ userId, grants, activeWs: ws.includes(form.activeWs) ? form.activeWs : ws[0] || 'business' })
  }

  function setGrant(ws, access, overrides) {
    setForm(f => ({ ...f, grants: { ...f.grants, [ws]: { access, tool_overrides: overrides } } }))
  }

  async function toggleEnabled() {
    setSavingSwitch(true)
    try {
      const updated = await adminApi.updateSettings({ api_keys_enabled: !enabled })
      setEnabled(updated.api_keys_enabled)
      toast.success(updated.api_keys_enabled ? 'Integrations & MCP turned on.' : 'Turned off — every key is rejected until turned back on.')
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
      else Object.assign(body, { user_id: form.userId, grants: form.grants })
      const result = await adminApi.createApiKey(body)
      if (result.key) {
        setNewKey(result.key)
        update({ password: '' })
        setModal('reveal')
      } else {
        toast.success(`Sent to ${result.meta.user_name} to review and accept.`)
        closeModal()
      }
      load()
    } catch (err) {
      setFormError(err.message || 'Failed to create key')
    } finally {
      setBusy(false)
    }
  }

  function openEdit(key) {
    setEditing(key)
    const user = (data?.users || []).find(u => u.id === key.user_id)
    setForm({
      ...EMPTY_FORM,
      kind: key.kind,
      name: key.name,
      userId: key.user_id || '',
      grants: key.grants || {},
      activeWs: Object.keys(key.grants || {})[0] || user?.workspaces?.[0] || 'business',
    })
    setModal('edit')
  }

  async function saveEdit() {
    setFormError('')
    setBusy(true)
    try {
      const body = { name: form.name }
      if (editing.kind === 'mcp') body.grants = form.grants
      const result = await adminApi.updateApiKey(editing.id, body)
      toast.success(result.needs_approval
        ? `Sent to ${editing.user_name} to approve — their current tools stay until then.`
        : `Saved “${form.name}”.`)
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
      toast.success(key.status === 'pending' ? `Cancelled “${key.name}”.` : `Revoked “${key.name}”.`)
      load()
    } catch (err) {
      toast.error(err.message || 'Failed to revoke key')
    }
  }

  async function dismissRequest(request) {
    try {
      await adminApi.dismissKeyRequest(request.id)
      load()
    } catch (err) {
      toast.error(err.message || 'Failed to dismiss')
    }
  }

  const catalog = data?.mcp_catalog || []
  const users = data?.users || []
  const keys = data?.keys || []
  const integrations = keys.filter(k => k.kind === 'integration')
  const mcpKeys = keys.filter(k => k.kind === 'mcp')
  const formUser = users.find(u => u.id === form.userId)
  const formWorkspaces = formUser?.workspaces || []
  const grantsSomething = formWorkspaces.some(ws => grantAllows(catalogFor(catalog, formUser, ws), form.grants[ws]))
  const canCreate = form.name.trim() && form.password && (
    form.kind === 'integration' || (form.userId && grantsSomething)
  )
  const isMcpForm = modal === 'create' ? form.kind === 'mcp' : editing?.kind === 'mcp'

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Integrations & MCP" backTo="/settings/admin" backLabel="Admin Settings" />

      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        Let outside tools reach LogCore without sharing a password. An <strong>integration</strong>
        {' '}belongs to this instance and can only send leads into a shared contacts list.
        {' '}<strong>MCP</strong> lets an AI app act as one person, with only the tools you pick —
        they review and accept it themselves. See Help → Integrations &amp; MCP for setup.
      </p>

      <div className="card p-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Allow integrations &amp; MCP</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
            Off rejects every key immediately, without deleting any.
          </p>
        </div>
        <button
          role="switch"
          aria-checked={enabled}
          aria-label="Allow integrations and MCP"
          disabled={savingSwitch || !data}
          onClick={toggleEnabled}
          className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${enabled ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-700'} ${savingSwitch ? 'opacity-50' : ''}`}
        >
          <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${enabled ? 'translate-x-5' : ''}`} />
        </button>
      </div>

      {data?.requests?.length > 0 && (
        <div className="card">
          <h2 className="font-semibold p-4 border-b border-charcoal-100 dark:border-charcoal-800">MCP requests</h2>
          <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
            {data.requests.map(r => (
              <div key={r.id} className="p-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{r.user_name}</p>
                  {r.note && <p className="text-xs text-charcoal-500 dark:text-charcoal-400">“{r.note}”</p>}
                  <p className="text-xs text-charcoal-400">asked {formatDate(r.created_at)}</p>
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  <button onClick={() => openCreate('mcp', r.user_id)} disabled={!enabled} className="btn-primary text-sm">Set up</button>
                  <button onClick={() => dismissRequest(r)} className="btn-ghost text-sm">Dismiss</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <div className="flex items-center justify-between p-4 border-b border-charcoal-100 dark:border-charcoal-800">
          <h2 className="font-semibold">Integrations</h2>
          <button onClick={() => openCreate('integration')} disabled={!enabled || !data} className="btn-primary text-sm">
            + New
          </button>
        </div>
        <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
          {!data ? (
            <p className="text-sm text-charcoal-400 p-4">Loading…</p>
          ) : integrations.length === 0 ? (
            <p className="text-sm text-charcoal-400 p-4">No integrations yet — e.g. a website lead form.</p>
          ) : (
            integrations.map(k => <KeyRow key={k.id} k={k} catalog={catalog} onEdit={openEdit} onRevoke={setRevoking} onHelp={() => setModal('help')} />)
          )}
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between p-4 border-b border-charcoal-100 dark:border-charcoal-800">
          <h2 className="font-semibold">MCP</h2>
          <button onClick={() => openCreate('mcp')} disabled={!enabled || !data} className="btn-primary text-sm">
            + Set up
          </button>
        </div>
        <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
          {!data ? (
            <p className="text-sm text-charcoal-400 p-4">Loading…</p>
          ) : mcpKeys.length === 0 ? (
            <p className="text-sm text-charcoal-400 p-4">No one has MCP access yet.</p>
          ) : (
            mcpKeys.map(k => <KeyRow key={k.id} k={k} catalog={catalog} onEdit={openEdit} onRevoke={setRevoking} onHelp={() => setModal('help')} />)
          )}
        </div>
      </div>

      {(modal === 'create' || modal === 'edit') && (
        <div className="modal-overlay">
          <div ref={modalCardRef} className="modal-card p-5 max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">
                {modal === 'edit' ? `Edit “${editing?.name}”` : form.kind === 'mcp' ? 'Set up MCP access' : 'New integration'}
              </h2>
              <button onClick={closeModal} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
            </div>

            <div className="space-y-4 mb-3">
              {modal === 'create' && form.kind === 'mcp' && (
                <div>
                  <label className="block text-sm font-medium mb-1" htmlFor="key-user">Acts as</label>
                  <select id="key-user" value={form.userId} onChange={e => pickUser(e.target.value)} className="input w-full text-base">
                    <option value="">Pick a person…</option>
                    {users.map(u => <option key={u.id} value={u.id}>{u.name}{u.role === 'admin' ? ' (admin)' : ''}</option>)}
                  </select>
                  <p className="text-xs text-charcoal-400 mt-1">
                    They get a notification to review and accept. Only they will see the key — you won&apos;t.
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium mb-1" htmlFor="key-name">Name</label>
                <input
                  id="key-name"
                  value={form.name}
                  onChange={e => update({ name: e.target.value })}
                  maxLength={60}
                  placeholder={form.kind === 'integration' ? 'e.g. Website lead form' : 'e.g. Claude on their laptop'}
                  className="input w-full text-base"
                />
              </div>

              {modal === 'create' && form.kind === 'integration' && (
                <div>
                  <label className="block text-sm font-medium mb-1" htmlFor="key-target">Leads go to</label>
                  <select id="key-target" value={form.target} onChange={e => update({ target: e.target.value })} className="input w-full text-base">
                    {(data?.workspaces || []).includes('business') && <option value="_team">Team contacts (business)</option>}
                    {(data?.workspaces || []).includes('personal') && <option value="_household">Household contacts (personal)</option>}
                  </select>
                  <p className="text-xs text-charcoal-400 mt-1">
                    Fixed for this key — the website can&apos;t send leads anywhere else. Follow-up reminders go to every admin.
                  </p>
                </div>
              )}

              {isMcpForm && formUser && (
                <div>
                  <p className="block text-sm font-medium mb-1">Tools, per workspace</p>
                  <p className="text-xs text-charcoal-400 mb-2">
                    Business and Personal data are separate, so each gets its own tools. Set each module,
                    or tap one to pick individual tools. The AI picks the workspace on every call, and the
                    key can never do more than {formUser.name} can already do in LogCore.
                    {modal === 'edit' && editing?.status === 'active' && ' Adding tools (or a workspace) sends them a request to approve; removing applies right away.'}
                  </p>
                  {formWorkspaces.length > 1 && (
                    <div role="tablist" aria-label="Workspace" className="flex gap-1 mb-2">
                      {formWorkspaces.map(ws => {
                        const on = grantAllows(catalogFor(catalog, formUser, ws), form.grants[ws])
                        return (
                          <button
                            key={ws}
                            role="tab"
                            aria-selected={form.activeWs === ws}
                            onClick={() => update({ activeWs: ws })}
                            className={`flex-1 py-1.5 rounded-lg text-sm border ${form.activeWs === ws ? 'border-orange-500 bg-orange-500/5 font-medium' : 'border-charcoal-200 dark:border-charcoal-700'}`}
                          >
                            {WS_LABELS[ws]}{on ? ' ✓' : ''}
                          </button>
                        )
                      })}
                    </div>
                  )}
                  {formWorkspaces.includes(form.activeWs) && (
                    <ToolAccessPicker
                      key={form.activeWs}
                      catalog={catalogFor(catalog, formUser, form.activeWs)}
                      access={form.grants[form.activeWs]?.access || {}}
                      overrides={form.grants[form.activeWs]?.tool_overrides || {}}
                      onChange={(access, overrides) => setGrant(form.activeWs, access, overrides)}
                    />
                  )}
                  {formWorkspaces.length === 1 && (
                    <p className="text-xs text-charcoal-400 mt-1">{formUser.name} only has the {WS_LABELS[formWorkspaces[0]]} workspace.</p>
                  )}
                </div>
              )}

              {modal === 'create' && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1" htmlFor="key-exp">
                      {form.kind === 'mcp' ? 'Key expires (after they accept)' : 'Expires'}
                    </label>
                    <select id="key-exp" value={form.expiresDays} onChange={e => update({ expiresDays: e.target.value })} className="input w-full text-base">
                      {(data?.expiry_days || [30, 90, 365]).map(d => (
                        <option key={d} value={String(d)}>In {d} days</option>
                      ))}
                      <option value="">Never</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1" htmlFor="key-pw">Your current password</label>
                    <input
                      id="key-pw"
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
                  {busy ? 'Working…' : form.kind === 'mcp' ? 'Send to them' : 'Create key'}
                </button>
              ) : (
                <button
                  onClick={saveEdit}
                  disabled={busy || !form.name.trim() || (isMcpForm && !grantsSomething)}
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
          <div ref={modalCardRef} className="modal-card p-5 max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold mb-2">Copy the integration key</h2>
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-3">
              This is the only time it will be shown. Put it in the website&apos;s settings as a secret —
              if you lose it, revoke it and create a new one.
            </p>
            <code className="block p-3 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 text-xs break-all select-all mb-3">
              {newKey}
            </code>
            <div className="flex gap-2 mb-4">
              <button onClick={copyKey} className="btn-ghost flex-1">{copied ? 'Copied ✓' : 'Copy'}</button>
              <button onClick={closeModal} className="btn-primary flex-1">Done</button>
            </div>
            <IntakeHelp spec={data?.intake_spec} apiKey={newKey} />
          </div>
        </div>
      )}

      {modal === 'help' && (
        <div className="modal-overlay">
          <div ref={modalCardRef} className="modal-card p-5 max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">How to send leads</h2>
              <button onClick={closeModal} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
            </div>
            <IntakeHelp spec={data?.intake_spec} />
          </div>
        </div>
      )}

      {revoking && (
        <ConfirmDialog
          title={revoking.status === 'pending' ? 'Cancel this MCP setup?' : 'Revoke this key?'}
          message={revoking.status === 'pending'
            ? `${revoking.user_name} won't be able to accept “${revoking.name}”.`
            : `“${revoking.name}” stops working immediately. Anything using it will start getting errors.`}
          confirmLabel={revoking.status === 'pending' ? 'Cancel setup' : 'Revoke'}
          danger
          onConfirm={revokeKey}
          onCancel={() => setRevoking(null)}
        />
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
