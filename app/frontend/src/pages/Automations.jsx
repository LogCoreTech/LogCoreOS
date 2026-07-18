import { useEffect, useRef, useState } from 'react'
import HelpButton from '../components/HelpButton'
import { useSearchParams } from 'react-router-dom'
import { automations as api, auth as authApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import TagInput from '../components/TagInput'

function fmt(iso) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

const ITEM_ACTIONS = [
  { id: 'interested', label: 'Interested' },
  { id: 'passed', label: 'Pass' },
  { id: 'offer_made', label: 'Offer Made' },
  { id: 'closed', label: 'Closed' },
]
const STATUS_LABEL = {
  new: 'New', interested: 'Interested', passed: 'Passed',
  offer_made: 'Offer Made', closed: 'Closed',
}

// ── Inbox item row ─────────────────────────────────────────────────────────────
function InboxItemRow({ item, canAct, canManage, onStatus, onDelete }) {
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)

  async function act(status) {
    setBusy(true)
    try { await onStatus(item.id, status) } finally { setBusy(false) }
  }

  return (
    <div className="rounded-xl border border-charcoal-100 dark:border-charcoal-800 bg-white dark:bg-charcoal-900 p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <button onClick={() => setExpanded(e => !e)} className="min-w-0 flex-1 text-left">
          <div className="flex items-center gap-2 flex-wrap">
            {item.status === 'new' && <span className="w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0" />}
            <p className="font-medium text-sm">{item.title}</p>
            {item.status !== 'new' && (
              <span className="badge text-[10px]">{STATUS_LABEL[item.status] || item.status}</span>
            )}
          </div>
          <p className="text-[11px] text-charcoal-400 mt-0.5">
            {item.workflow_key} · {fmt(item.received_at)}
            {item.status_by && <> · {STATUS_LABEL[item.status]} by {item.status_by}</>}
          </p>
        </button>
        <div className="flex items-center gap-1 shrink-0">
          {item.url && (
            <a href={item.url} target="_blank" rel="noreferrer" className="btn-ghost text-xs px-1.5 py-0.5" title="Open source link">↗</a>
          )}
          {canManage && (
            <button onClick={() => onDelete(item.id)} className="text-charcoal-300 hover:text-red-500 text-xs px-1" title="Delete item">✕</button>
          )}
        </div>
      </div>

      {Object.keys(item.fields || {}).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {Object.entries(item.fields).map(([k, v]) => (
            <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-500 dark:text-charcoal-400">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {expanded && item.summary && (
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 whitespace-pre-wrap">{item.summary}</p>
      )}
      {expanded && item.note && (
        <p className="text-xs text-charcoal-400 italic">Note: {item.note}</p>
      )}

      {canAct && (
        <div className="flex gap-1 flex-wrap">
          {ITEM_ACTIONS.map(a => (
            <button
              key={a.id}
              onClick={() => act(a.id)}
              disabled={busy || item.status === a.id}
              className={`text-[11px] px-2 py-1 rounded-md font-medium transition-colors disabled:opacity-40 ${
                item.status === a.id
                  ? 'bg-orange-500 text-white'
                  : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-200 dark:hover:bg-charcoal-700'
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Inbox settings modal (create/edit) ─────────────────────────────────────────
function InboxSettingsModal({ inbox, isBusiness, workflowKeySuggestions, onClose, onSaved }) {
  const editing = !!inbox
  const [name, setName] = useState(inbox?.name || '')
  const [notify, setNotify] = useState(inbox?.notify || [])
  const [reviewers, setReviewers] = useState(inbox?.reviewers || [])
  const [workflows, setWorkflows] = useState(inbox?.workflows || [])
  const [members, setMembers] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isBusiness) return
    authApi.users().then(list => setMembers((Array.isArray(list) ? list : []).map(u => u.name))).catch(() => {})
  }, [isBusiness])

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = { name, notify, reviewers, workflows }
      if (editing) await api.updateInbox(inbox.id, payload)
      else await api.createInbox(payload)
      onSaved()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete inbox "${inbox.name}"? It must be empty.`)) return
    try {
      await api.removeInbox(inbox.id)
      onSaved()
      onClose()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card p-5 max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">{editing ? 'Inbox settings' : 'New inbox'}</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>
        <p className="text-xs text-charcoal-400 mb-4">
          {isBusiness
            ? '🧑‍🤝‍🧑 Business inbox — shared with the team.'
            : 'Personal inbox — only you. Switch to the business workspace for a team inbox.'}
        </p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Land Leads" className="input" autoFocus={!editing} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">
              Workflows <span className="text-charcoal-400 font-normal">(keys that route here)</span>
            </label>
            <TagInput
              value={workflows}
              onChange={setWorkflows}
              suggestions={workflowKeySuggestions}
              placeholder="e.g. land-lead-search"
            />
            <p className="text-[10px] text-charcoal-400 mt-1">Items posted with these workflow_key values land in this inbox. Unmatched keys go to “General”.</p>
          </div>
          {isBusiness && (
            <>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Notify <span className="text-charcoal-400 font-normal">(pinged on new items)</span>
                </label>
                <TagInput value={notify} onChange={setNotify} suggestions={members} strict placeholder="Pick members…" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Reviewers <span className="text-charcoal-400 font-normal">(can act on items — admins always can)</span>
                </label>
                <TagInput value={reviewers} onChange={setReviewers} suggestions={members} strict placeholder="Pick members…" />
              </div>
            </>
          )}
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2">
            {editing && (
              <button type="button" onClick={handleDelete} className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                Delete
              </button>
            )}
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={saving || !name.trim()} className="btn-primary flex-1">
              {saving ? 'Saving…' : editing ? 'Save' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Logs Modal ─────────────────────────────────────────────────────────────────
function LogsModal({ workflow, onClose }) {
  const [logs, setLogs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const timerRef              = useRef(null)

  async function fetchLogs() {
    try {
      const data = await api.logs(workflow.id)
      setLogs(data)
      setLoading(false)
      const running = data.some(e => e.status === 'running')
      if (running) timerRef.current = setTimeout(fetchLogs, 3000)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
    return () => clearTimeout(timerRef.current)
  }, [workflow.id])

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-charcoal-900 rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-charcoal-100 dark:border-charcoal-800">
          <h3 className="font-semibold">{workflow.name} — Logs</h3>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading && <p className="text-sm text-charcoal-400">Loading…</p>}
          {error && <p className="text-sm text-red-500">{error}</p>}
          {!loading && !error && logs.length === 0 && (
            <p className="text-sm text-charcoal-400">No executions yet.</p>
          )}
          {logs.map((ex, i) => (
            <div key={i} className="rounded-lg border border-charcoal-100 dark:border-charcoal-800 p-3 text-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                  ex.status === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                  ex.status === 'error'   ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                            'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                }`}>
                  {ex.status || 'running'}
                </span>
                <span className="text-charcoal-400 text-xs">{fmt(ex.startedAt || ex.started_at)}</span>
              </div>
              {ex.data?.resultData?.error?.message && (
                <p className="text-red-500 text-xs mt-1 font-mono truncate">
                  {ex.data.resultData.error.message}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Import Modal ───────────────────────────────────────────────────────────────
function ImportModal({ defaultScope, isAdmin, onClose, onImported }) {
  const [file, setFile]     = useState(null)
  const [name, setName]     = useState('')
  const [scope, setScope]   = useState(defaultScope || 'personal')
  const [tags, setTags]     = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')

  async function submit(e) {
    e.preventDefault()
    if (!file) { setError('Please select a workflow JSON file.'); return }
    setSaving(true)
    setError('')
    try {
      const tagList = tags.split(',').map(t => t.trim()).filter(Boolean)
      const record = await api.importFile(file, name, scope, tagList)
      onImported(record)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-charcoal-900 rounded-xl shadow-xl w-full max-w-md"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-charcoal-100 dark:border-charcoal-800">
          <h3 className="font-semibold">Import Workflow</h3>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>
        <form onSubmit={submit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">n8n Workflow JSON</label>
            <input
              type="file"
              accept=".json,application/json"
              onChange={e => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-charcoal-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-orange-100 file:text-orange-700 hover:file:bg-orange-200 cursor-pointer"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Name (optional)</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Override workflow name"
              className="input"
            />
          </div>
          {isAdmin && (
            <div>
              <label className="block text-sm font-medium mb-1">Scope</label>
              <div className="flex gap-2">
                {['personal', 'business'].map(s => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setScope(s)}
                    className={`flex-1 py-1.5 rounded-lg border text-sm font-medium transition-colors capitalize ${
                      scope === s
                        ? 'border-orange-500 bg-orange-50 dark:bg-orange-900/20 text-orange-600'
                        : 'border-charcoal-200 dark:border-charcoal-700'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div>
            <label className="block text-sm font-medium mb-1">Tags (optional, comma-separated)</label>
            <input
              type="text"
              value={tags}
              onChange={e => setTags(e.target.value)}
              placeholder="e.g. slack, daily, crm"
              className="input"
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button type="submit" disabled={saving || !file} className="btn-primary w-full disabled:opacity-50">
            {saving ? 'Importing…' : 'Import Workflow'}
          </button>
        </form>
      </div>
    </div>
  )
}

// ── Workflow Card ──────────────────────────────────────────────────────────────
function WorkflowCard({ workflow, isAdmin, onDelete, onRun, onToggleActive }) {
  const [logsOpen, setLogsOpen]     = useState(false)
  const [running, setRunning]       = useState(false)
  const [toggling, setToggling]     = useState(false)
  const [runError, setRunError]     = useState('')
  const [deleting, setDeleting]     = useState(false)
  const [active, setActive]         = useState(workflow.active ?? false)

  const canDelete   = isAdmin || workflow.scope === 'personal'
  const canActivate = isAdmin || workflow.scope === 'personal'

  async function handleRun() {
    setRunning(true)
    setRunError('')
    try {
      await onRun(workflow.id)
    } catch (err) {
      setRunError(err.message)
    } finally {
      setRunning(false)
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete "${workflow.name}"? This will also remove it from n8n.`)) return
    setDeleting(true)
    try {
      await onDelete(workflow.id)
    } catch (err) {
      alert(err.message)
      setDeleting(false)
    }
  }

  async function handleToggleActive() {
    setToggling(true)
    try {
      const result = await onToggleActive(workflow.id, active)
      setActive(result.active)
    } catch (err) {
      alert(err.message)
    } finally {
      setToggling(false)
    }
  }

  return (
    <>
      <div className="rounded-xl border border-charcoal-100 dark:border-charcoal-800 bg-white dark:bg-charcoal-900 p-4 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="font-medium text-sm truncate">{workflow.name}</p>
              <span className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full font-medium ${
                active
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-charcoal-100 text-charcoal-500 dark:bg-charcoal-800 dark:text-charcoal-400'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-green-500' : 'bg-charcoal-400'}`} />
                {active ? 'Active' : 'Inactive'}
              </span>
            </div>
            <p className="text-xs text-charcoal-400 mt-0.5">Last run: {fmt(workflow.last_run)}</p>
          </div>
          {canDelete && (
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-charcoal-300 hover:text-red-500 transition-colors shrink-0 text-xs disabled:opacity-30"
            >
              {deleting ? '…' : '✕'}
            </button>
          )}
        </div>

        {workflow.tags?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {workflow.tags.map(t => (
              <span key={t} className="text-xs px-1.5 py-0.5 rounded bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-500">
                {t}
              </span>
            ))}
          </div>
        )}

        {runError && <p className="text-xs text-red-500">{runError}</p>}

        <div className="flex gap-2">
          <button
            onClick={handleRun}
            disabled={running}
            title={!active ? 'Workflow is inactive — activate it to enable scheduled/webhook triggers. Manual run still works.' : ''}
            className="btn-primary text-xs px-3 py-1.5 flex-1 disabled:opacity-50"
          >
            {running ? 'Running…' : '▶ Run'}
          </button>
          {canActivate && (
            <button
              onClick={handleToggleActive}
              disabled={toggling}
              className="btn-ghost text-xs px-3 py-1.5 disabled:opacity-50"
            >
              {toggling ? '…' : active ? 'Deactivate' : 'Activate'}
            </button>
          )}
          <button
            onClick={() => setLogsOpen(true)}
            className="btn-ghost text-xs px-3 py-1.5"
          >
            Logs
          </button>
        </div>
      </div>

      {logsOpen && <LogsModal workflow={workflow} onClose={() => setLogsOpen(false)} />}
    </>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function Automations() {
  const { user }                  = useAuth()
  const { workspace }             = useWorkspace()
  const isAdmin                   = user?.role === 'admin'
  const scope                     = workspace === 'business' ? 'business' : 'personal'

  const [workflows, setWorkflows] = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState('')
  const [importing, setImporting] = useState(false)

  // Inbox state — workspace-scoped server-side via the X-Workspace header
  const [view, setView]           = useState('workflows') // 'workflows' | 'inbox'
  const [inboxes, setInboxes]     = useState([])
  const [items, setItems]         = useState([])
  const [activeInbox, setActiveInbox] = useState('') // inbox id filter ('' = all)
  const [statusFilter, setStatusFilter] = useState('new') // new | reviewed | all
  const [inboxModal, setInboxModal] = useState(null) // {inbox} | {creating: true}
  const [searchParams, setSearchParams] = useSearchParams()

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await api.list('all')
      setWorkflows(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadInbox() {
    try {
      const data = await api.inbox()
      setInboxes(Array.isArray(data?.inboxes) ? data.inboxes : [])
      setItems(Array.isArray(data?.items) ? data.items : [])
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => { loadInbox() }, [workspace])

  // Deep link from notifications: /automations?view=inbox&inbox=<id>
  useEffect(() => {
    if (searchParams.get('view') !== 'inbox') return
    setView('inbox')
    const target = searchParams.get('inbox')
    if (target) setActiveInbox(target)
    searchParams.delete('view')
    searchParams.delete('inbox')
    setSearchParams(searchParams, { replace: true })
  }, [searchParams])

  async function handleItemStatus(itemId, status) {
    try {
      const updated = await api.setItemStatus(itemId, status)
      setItems(prev => prev.map(i => i.id === itemId ? updated : i))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleItemDelete(itemId) {
    try {
      await api.removeItem(itemId)
      setItems(prev => prev.filter(i => i.id !== itemId))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRun(id) {
    await api.run(id)
    load()
  }

  async function handleToggleActive(id, currentlyActive) {
    const result = currentlyActive
      ? await api.deactivate(id)
      : await api.activate(id)
    setWorkflows(wfs => wfs.map(w => w.id === id ? { ...w, active: result.active } : w))
    return result
  }

  async function handleDelete(id) {
    await api.remove(id)
    setWorkflows(wfs => wfs.filter(w => w.id !== id))
  }

  function handleImported(record) {
    setWorkflows(wfs => [...wfs, record])
  }

  const visible = workflows.filter(w => w.scope === scope)
  const newCount = items.filter(i => i.status === 'new').length
  const canManageInboxes = scope !== 'business' || isAdmin
  const shownItems = items
    .filter(i => !activeInbox || i.inbox_id === activeInbox)
    .filter(i =>
      statusFilter === 'all' ? true :
      statusFilter === 'new' ? i.status === 'new' : i.status !== 'new'
    )
    .sort((a, b) => (b.received_at || '').localeCompare(a.received_at || ''))
  const inboxById = Object.fromEntries(inboxes.map(b => [b.id, b]))
  const workflowKeySuggestions = [...new Set(items.map(i => i.workflow_key).filter(Boolean))]
  // Settings targets the selected inbox — or the only one, so a lone fresh
  // inbox is manageable without first selecting a chip
  const settingsTarget = activeInbox ? inboxById[activeInbox] : (inboxes.length === 1 ? inboxes[0] : null)

  function canActOn(item) {
    const box = inboxById[item.inbox_id]
    return box ? !!box._can_act : isAdmin || scope !== 'business'
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between gap-6">
        <span className="flex items-center gap-2"><h1 className="text-2xl font-bold">Automations</h1><HelpButton section="automations" /></span>
        {view === 'workflows' ? (
          <button onClick={() => setImporting(true)} className="btn-primary text-sm px-4 py-1.5 rounded-full shrink-0">
            + Import Workflow
          </button>
        ) : canManageInboxes ? (
          <button onClick={() => setInboxModal({ creating: true })} className="btn-primary text-sm px-4 py-1.5 rounded-full shrink-0">
            + New Inbox
          </button>
        ) : null}
      </div>

      {/* View pills */}
      <div className="flex gap-1">
        {[
          { id: 'workflows', label: 'Workflows' },
          { id: 'inbox', label: `Inbox${newCount ? ` (${newCount})` : ''}` },
        ].map(v => (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              view === v.id
                ? 'bg-orange-500 text-white'
                : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300'
            }`}
          >
            {v.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-charcoal-400">Loading…</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {view === 'workflows' && !loading && !error && visible.length === 0 && (
        <div className="text-center py-12 text-charcoal-400">
          <p className="text-4xl mb-3">⚡</p>
          <p className="text-sm font-medium">No {scope} workflows yet</p>
          <p className="text-xs mt-1">
            {scope === 'personal'
              ? 'Import an n8n workflow JSON to get started.'
              : isAdmin
                ? 'Import a workflow and set scope to Business.'
                : 'No business workflows have been set up yet.'}
          </p>
        </div>
      )}

      {view === 'workflows' && !loading && visible.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {visible.map(wf => (
            <WorkflowCard
              key={wf.id}
              workflow={wf}
              isAdmin={isAdmin}
              onDelete={handleDelete}
              onRun={handleRun}
              onToggleActive={handleToggleActive}
            />
          ))}
        </div>
      )}

      {view === 'inbox' && (
        <>
          {/* Inbox chips + status filter — chips always visible so a fresh
              inbox is discoverable even before any items arrive */}
          <div className="flex items-center gap-2 flex-wrap">
            {inboxes.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {inboxes.length > 1 && (
                  <button
                    onClick={() => setActiveInbox('')}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      !activeInbox ? 'bg-charcoal-600 text-white' : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-500 dark:text-charcoal-400'
                    }`}
                  >
                    All
                  </button>
                )}
                {inboxes.map(b => (
                  <button
                    key={b.id}
                    onClick={() => setActiveInbox(activeInbox === b.id ? '' : b.id)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      activeInbox === b.id || inboxes.length === 1
                        ? 'bg-charcoal-600 text-white'
                        : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-500 dark:text-charcoal-400'
                    }`}
                  >
                    📥 {b.name}
                  </button>
                ))}
              </div>
            )}
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="input !py-1 !w-auto text-xs ml-auto"
            >
              <option value="new">New</option>
              <option value="reviewed">Reviewed</option>
              <option value="all">All</option>
            </select>
            {canManageInboxes && settingsTarget && (
              <button onClick={() => setInboxModal({ inbox: settingsTarget })} className="btn-ghost text-xs px-2 py-1">
                ⚙ Settings
              </button>
            )}
          </div>

          {shownItems.length === 0 ? (
            <div className="text-center py-12 text-charcoal-400">
              <p className="text-4xl mb-3">📥</p>
              <p className="text-sm font-medium">
                {items.length === 0
                  ? inboxes.length > 0
                    ? `${inboxes.map(b => `“${b.name}”`).join(', ')} ${inboxes.length === 1 ? 'is' : 'are'} ready — no items yet`
                    : 'No inbox items yet'
                  : 'Nothing matches this filter'}
              </p>
              {items.length === 0 && (
                <p className="text-xs mt-1 max-w-sm mx-auto">
                  Workflows post reviewable items here via{' '}
                  <code className="text-[10px]">POST /api/v1/automations/inbox/items</code> with the
                  automation token (Admin → n8n). Items are deduped by external_id.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {shownItems.map(item => (
                <InboxItemRow
                  key={item.id}
                  item={item}
                  canAct={canActOn(item)}
                  canManage={canManageInboxes}
                  onStatus={handleItemStatus}
                  onDelete={handleItemDelete}
                />
              ))}
            </div>
          )}
        </>
      )}

      {importing && (
        <ImportModal
          defaultScope={scope}
          isAdmin={isAdmin}
          onClose={() => setImporting(false)}
          onImported={handleImported}
        />
      )}

      {inboxModal && (
        <InboxSettingsModal
          inbox={inboxModal.inbox || null}
          isBusiness={scope === 'business'}
          workflowKeySuggestions={workflowKeySuggestions}
          onClose={() => setInboxModal(null)}
          onSaved={loadInbox}
        />
      )}
    </div>
  )
}
