import { useState } from 'react'
import { contacts as contactsApi } from './api'

// Bulk "convert personal contacts into the shared pool" (owner ask,
// 2026-08-17: "have so many" to move one at a time via ContactModal's own
// single Convert button). Defaults to everything selected — the owner's own
// framing was "I have so many," not "let me carefully pick a few" — with
// per-row checkboxes to exclude specific ones rather than an all-or-nothing
// action. `contacts` is pre-filtered by the caller to the eligible set
// (the viewer's own personal, non-self contacts) — this component doesn't
// re-derive eligibility itself.
export default function BulkConvertContactsModal({ contacts, workspace, onClose, onDone }) {
  const poolLabel = workspace === 'business' ? 'Team' : 'Household'
  const [selected, setSelected] = useState(() => new Set(contacts.map(c => c.id)))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function toggle(id) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    setSelected(prev => (prev.size === contacts.length ? new Set() : new Set(contacts.map(c => c.id))))
  }

  async function submit() {
    if (selected.size === 0) return
    setBusy(true)
    setError('')
    try {
      const res = await contactsApi.convertBulk([...selected])
      onDone(res)
    } catch (err) {
      setError(err.message || 'Convert failed')
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-md p-5">
        <h2 className="font-semibold mb-1">Convert to {poolLabel}</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Everyone with access to {poolLabel} will be able to see whichever contacts you convert.
        </p>
        <div className="flex items-center justify-between mb-2">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={selected.size === contacts.length} onChange={toggleAll} />
            Select all ({contacts.length})
          </label>
          <span className="text-xs text-charcoal-400">{selected.size} selected</span>
        </div>
        <div className="max-h-64 overflow-y-auto border border-charcoal-200 dark:border-charcoal-700 rounded-lg divide-y divide-charcoal-100 dark:divide-charcoal-800">
          {contacts.map(c => (
            <label key={c.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800">
              <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
              <span className="truncate">{c.type === 'company' ? '🏢' : '🧑'} {c.name}</span>
            </label>
          ))}
        </div>
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
        <div className="flex gap-2 pt-4">
          <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          <button type="button" onClick={submit} disabled={busy || selected.size === 0} className="btn-primary flex-1">
            {busy ? 'Converting…' : `Convert ${selected.size}`}
          </button>
        </div>
      </div>
    </div>
  )
}
