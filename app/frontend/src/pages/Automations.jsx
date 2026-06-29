import { useEffect, useRef, useState } from 'react'
import { automations as api } from '../lib/api'
import { useAuth } from '../lib/auth'

function fmt(iso) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
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
  const isAdmin                   = user?.role === 'admin'
  const disabled                  = new Set(user?.disabledModules || [])

  const TABS = [
    !disabled.has('automations')          && { id: 'personal',  label: 'Personal'  },
    !disabled.has('automations_business') && { id: 'business',  label: 'Business'  },
  ].filter(Boolean)

  const [tab, setTab]             = useState(() => TABS[0]?.id || 'personal')
  const [workflows, setWorkflows] = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState('')
  const [importing, setImporting] = useState(false)

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

  useEffect(() => { load() }, [])

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

  const visible = workflows.filter(w => w.scope === tab)

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Automations</h1>
        <button onClick={() => setImporting(true)} className="btn-primary text-sm px-3 py-1.5">
          + Import Workflow
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors ${
              tab === id
                ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                : 'text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-charcoal-400">Loading…</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {!loading && !error && visible.length === 0 && (
        <div className="text-center py-12 text-charcoal-400">
          <p className="text-4xl mb-3">⚡</p>
          <p className="text-sm font-medium">No {tab} workflows yet</p>
          <p className="text-xs mt-1">
            {tab === 'personal'
              ? 'Import an n8n workflow JSON to get started.'
              : isAdmin
                ? 'Import a workflow and set scope to Business.'
                : 'No business workflows have been set up yet.'}
          </p>
        </div>
      )}

      {!loading && visible.length > 0 && (
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

      {importing && (
        <ImportModal
          defaultScope={tab}
          isAdmin={isAdmin}
          onClose={() => setImporting(false)}
          onImported={handleImported}
        />
      )}
    </div>
  )
}
