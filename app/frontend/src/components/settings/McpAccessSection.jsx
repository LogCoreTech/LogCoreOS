import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useSearchParams } from 'react-router-dom'
import { mcpAccess } from '../../lib/api'
import { useToast } from '../../lib/toast'
import useEscapeToClose from '../../lib/useEscapeToClose'
import useFocusTrap from '../../lib/useFocusTrap'
import useScrollLock from '../../lib/useScrollLock'
import ConfirmDialog from '../ConfirmDialog'

// Settings → Account → MCP (docs/MEMORY.md 2026-10-25). An admin sets up MCP
// access for a person; it lands here (and as a notification deep-linking to
// ?mcp=<id>). The person reviews exactly which tools it grants and accepts
// with their password — the key is generated at that moment and shown once.
// Hitting Copy takes it off the screen for good. They can also approve or
// reject an admin's request to add tools, revoke their key, or ask for access.
// They can never create a key or change its tools themselves.

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString() : '—'
}

const WS_LABELS = { business: 'Business', personal: 'Personal' }

// Grouped by workspace, then module — Business and Personal data are
// separate, and a key can have different tools in each.
function ToolList({ tools }) {
  const byWs = {}
  for (const t of tools || []) {
    const ws = (byWs[t.workspace] ||= {})
    ;(ws[t.label] ||= []).push(t)
  }
  return (
    <div className="space-y-3 max-h-72 overflow-y-auto border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-2.5">
      {Object.entries(byWs).map(([ws, groups]) => (
        <div key={ws}>
          <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 mb-1">
            {WS_LABELS[ws] || ws} workspace
          </p>
          <div className="space-y-2 pl-1">
            {Object.entries(groups).map(([label, list]) => (
              <div key={label}>
                <p className="text-sm font-medium">{label}</p>
                <ul className="pl-3 space-y-0.5">
                  {list.map(t => (
                    <li key={t.name} className="text-xs">
                      <span className="font-mono">{t.name}</span>
                      {t.read_only
                        ? <span className="ml-1 text-charcoal-400">reads</span>
                        : <span className="ml-1 text-amber-600 dark:text-amber-400">changes data</span>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function workspacesOf(key) {
  return Object.keys(key.grants || {}).map(w => WS_LABELS[w] || w).join(' + ')
}

export default function McpAccessSection() {
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [modal, setModal] = useState(null) // {type: 'review'|'change'|'request', key?}
  const [password, setPassword] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [newKey, setNewKey] = useState('')
  const [copied, setCopied] = useState(false)
  const [revoking, setRevoking] = useState(null)
  const cardRef = useRef(null)

  useEscapeToClose(() => close())
  useFocusTrap(cardRef, !!modal)
  useScrollLock(!!modal)

  function load() {
    return mcpAccess.list().then(setData).catch(() => setData({ enabled: false, keys: [] }))
  }

  useEffect(() => { load() }, [])

  // Notification deep link: ?mcp=<key id> opens the right review straight away.
  useEffect(() => {
    const id = searchParams.get('mcp')
    if (!id || !data) return
    const key = data.keys.find(k => k.id === id)
    if (key?.status === 'pending') setModal({ type: 'review', key })
    else if (key?.proposed_tools) setModal({ type: 'change', key })
    searchParams.delete('mcp')
    setSearchParams(searchParams, { replace: true })
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  function close() {
    setModal(null)
    setPassword('')
    setNote('')
    setError('')
    setNewKey('')
    setCopied(false)
  }

  async function run(fn, fallback) {
    setError('')
    setBusy(true)
    try {
      await fn()
    } catch (err) {
      setError(err.message || fallback)
    } finally {
      setBusy(false)
    }
  }

  const accept = () => run(async () => {
    const result = await mcpAccess.accept(modal.key.id, password)
    setPassword('')
    setNewKey(result.key)
    load()
  }, 'Could not accept')

  const decline = () => run(async () => {
    await mcpAccess.decline(modal.key.id)
    toast.success('Declined.')
    close()
    load()
  }, 'Could not decline')

  const respondChange = accept => run(async () => {
    await mcpAccess.respondChange(modal.key.id, accept)
    toast.success(accept ? 'Approved — the new tools are on.' : 'Kept your current tools.')
    close()
    load()
  }, 'Could not save')

  const sendRequest = () => run(async () => {
    await mcpAccess.request(note)
    toast.success('Request sent to your admins.')
    close()
    load()
  }, 'Could not send the request')

  async function copyAndForget() {
    try {
      await navigator.clipboard.writeText(newKey)
      setNewKey('') // gone from the screen for good once it's on the clipboard
      setCopied(true)
    } catch {
      setError("Couldn't copy automatically — select the key and copy it by hand.")
    }
  }

  async function revoke() {
    const key = revoking
    setRevoking(null)
    try {
      await mcpAccess.revoke(key.id)
      toast.success(`Revoked “${key.name}”.`)
      load()
    } catch (err) {
      toast.error(err.message || 'Could not revoke')
    }
  }

  if (!data) return null
  const pending = data.keys.filter(k => k.status === 'pending')
  const active = data.keys.filter(k => k.status === 'active')
  if (!data.enabled && !active.length) return null

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">MCP (AI app access)</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
        Lets an AI app like Claude use LogCore as you, with only the tools an admin picked and you
        accepted. Admins set it up; you can revoke it any time.
      </p>

      <div className="space-y-3">
        {pending.map(k => (
          <div key={k.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border border-amber-500/40 bg-amber-500/5">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{k.name}</p>
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                Set up by {k.created_by_name} · {k.granted_tools.length} tools · waiting for you
              </p>
            </div>
            <button onClick={() => setModal({ type: 'review', key: k })} className="btn-primary text-sm shrink-0">Review</button>
          </div>
        ))}

        {active.map(k => (
          <div key={k.id} className="flex items-start justify-between gap-3 border-t border-charcoal-100 dark:border-charcoal-800 pt-3 first:border-0 first:pt-0">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{k.name}</p>
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                {k.granted_tools.length} tools · {workspacesOf(k)} · expires {k.expires_at ? formatDate(k.expires_at) : 'never'} · last used {formatDate(k.last_used_at)}
              </p>
              {k.proposed_tools && (
                <button onClick={() => setModal({ type: 'change', key: k })} className="text-xs text-amber-600 dark:text-amber-400 underline">
                  An admin wants to add tools — review
                </button>
              )}
            </div>
            <div className="flex flex-col gap-1 shrink-0">
              <button onClick={() => setModal({ type: 'tools', key: k })} className="btn-ghost text-sm">Tools</button>
              <button onClick={() => setRevoking(k)} className="btn-ghost text-sm text-red-500">Revoke</button>
            </div>
          </div>
        ))}

        {!pending.length && !active.length && (
          data.has_open_request ? (
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400">Your request is with the admins.</p>
          ) : (
            <button onClick={() => setModal({ type: 'request' })} disabled={!data.enabled} className="btn-ghost text-sm">
              Request MCP access
            </button>
          )
        )}
      </div>

      {/* Portaled: this section is a .card (backdrop-filter), which would
          otherwise trap a fixed overlay inside its own box — same reason
          ConfirmDialog portals (see its 2026-09-05 note). */}
      {modal && createPortal(
        <div className="modal-overlay">
          <div ref={cardRef} className="modal-card p-5 max-w-md max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">
                {modal.type === 'review' && (newKey || copied ? 'Your MCP key' : `Review “${modal.key.name}”`)}
                {modal.type === 'change' && `More tools for “${modal.key.name}”`}
                {modal.type === 'tools' && `“${modal.key.name}” can use`}
                {modal.type === 'request' && 'Request MCP access'}
              </h2>
              <button onClick={close} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
            </div>

            {modal.type === 'review' && !newKey && !copied && (
              <div className="space-y-3">
                <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                  {modal.key.created_by_name} set this up so an AI app can act as you with these
                  {' '}tools ({workspacesOf(modal.key)}). The app picks the workspace each time it uses one. Tools that change data run
                  {' '}without asking inside LogCore — only your AI app&apos;s own prompt stands in between.
                </p>
                <ToolList tools={modal.key.granted_tools} />
                <div>
                  <label className="block text-sm font-medium mb-1" htmlFor="mcp-pw">Your password, to accept</label>
                  <input
                    id="mcp-pw"
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    autoComplete="current-password"
                    className="input w-full text-base"
                  />
                </div>
                {error && <p className="text-red-500 text-sm">{error}</p>}
                <div className="flex gap-2">
                  <button onClick={decline} disabled={busy} className="btn-ghost flex-1">Decline</button>
                  <button onClick={accept} disabled={busy || !password} className="btn-primary flex-1">
                    {busy ? 'Working…' : 'Accept'}
                  </button>
                </div>
              </div>
            )}

            {modal.type === 'review' && (newKey || copied) && (
              <div className="space-y-3">
                {copied ? (
                  <p className="text-sm text-green-600 dark:text-green-400">
                    Copied. The key is no longer shown anywhere — paste it into your AI app now. If you
                    lose it, revoke it here and ask an admin for a new one.
                  </p>
                ) : (
                  <>
                    <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                      This is the only time it&apos;s shown. Copy it into your AI app — it disappears from
                      here once copied.
                    </p>
                    <code className="block p-3 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 text-xs break-all select-all">
                      {newKey}
                    </code>
                  </>
                )}
                {error && <p className="text-red-500 text-sm">{error}</p>}
                <div className="flex gap-2">
                  {!copied && <button onClick={copyAndForget} className="btn-primary flex-1">Copy</button>}
                  <button onClick={close} className={copied ? 'btn-primary flex-1' : 'btn-ghost flex-1'}>Done</button>
                </div>
              </div>
            )}

            {modal.type === 'change' && (
              <div className="space-y-3">
                <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                  An admin wants this key to be able to use the tools below. Until you approve, it keeps
                  only what you already accepted.
                </p>
                <ToolList tools={modal.key.proposed_tools} />
                {error && <p className="text-red-500 text-sm">{error}</p>}
                <div className="flex gap-2">
                  <button onClick={() => respondChange(false)} disabled={busy} className="btn-ghost flex-1">Keep current</button>
                  <button onClick={() => respondChange(true)} disabled={busy} className="btn-primary flex-1">Approve</button>
                </div>
              </div>
            )}

            {modal.type === 'tools' && (
              <div className="space-y-3">
                <ToolList tools={modal.key.granted_tools} />
                <button onClick={close} className="btn-primary w-full">Done</button>
              </div>
            )}

            {modal.type === 'request' && (
              <div className="space-y-3">
                <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                  Your admins get a notification. They choose which tools the key gets; you&apos;ll review it before it works.
                </p>
                <div>
                  <label className="block text-sm font-medium mb-1" htmlFor="mcp-note">What do you want to use it for? (optional)</label>
                  <textarea
                    id="mcp-note"
                    value={note}
                    onChange={e => setNote(e.target.value)}
                    maxLength={500}
                    rows={3}
                    className="input w-full text-base"
                  />
                </div>
                {error && <p className="text-red-500 text-sm">{error}</p>}
                <div className="flex gap-2">
                  <button onClick={close} className="btn-ghost flex-1">Cancel</button>
                  <button onClick={sendRequest} disabled={busy} className="btn-primary flex-1">Send request</button>
                </div>
              </div>
            )}
          </div>
        </div>,
        document.body
      )}

      {revoking && (
        <ConfirmDialog
          title="Revoke your MCP key?"
          message={`“${revoking.name}” stops working immediately. Your AI app will lose access until an admin sets up a new one.`}
          confirmLabel="Revoke"
          danger
          onConfirm={revoke}
          onCancel={() => setRevoking(null)}
        />
      )}
    </div>
  )
}
