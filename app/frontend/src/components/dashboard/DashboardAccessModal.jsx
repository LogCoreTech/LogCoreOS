import { useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'

export default function DashboardAccessModal({ dashboard, isPool, isOwner, onClose, onSaved }) {
  const [shared, setShared] = useState(dashboard.shared_with || [])
  const [contributors, setContributors] = useState(dashboard.contributors || [])
  const [hidden, setHidden] = useState((dashboard.hidden_from || []).join(', '))
  const [newTarget, setNewTarget] = useState('')
  const [newAccess, setNewAccess] = useState('read')
  const [shareData, setShareData] = useState(!!dashboard.share_underlying_data)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function addEntry() {
    if (!newTarget.trim()) return
    const entry = { target: newTarget.trim(), access: newAccess }
    if (isPool) setContributors([...contributors, entry])
    else setShared([...shared, entry])
    setNewTarget('')
  }

  function removeEntry(idx) {
    if (isPool) setContributors(contributors.filter((_, i) => i !== idx))
    else setShared(shared.filter((_, i) => i !== idx))
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const hiddenList = hidden.split(',').map(s => s.trim()).filter(Boolean)
      await dashboardsApi.updateAccess(dashboard.id, {
        shared_with: isPool ? null : shared.map(s => ({ target: s.target, access: s.access })),
        contributors: isPool ? contributors.map(c => ({ target: c.target, access: c.access })) : null,
        hidden_from: hiddenList,
      })
      if (isOwner) {
        await dashboardsApi.setShareUnderlyingData(dashboard.id, shareData)
      }
      onSaved?.()
      onClose()
    } catch (e) {
      setError(e.message || 'Failed to save sharing settings')
    } finally {
      setSaving(false)
    }
  }

  const entries = isPool ? contributors : shared

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Share "{dashboard.name}"</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>

        {error && <p className="text-sm text-red-500 mb-3">{error}</p>}

        <div className="space-y-2 mb-4">
          {entries.length === 0 && <p className="text-sm text-charcoal-400">Not shared with anyone yet.</p>}
          {entries.map((s, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span>{s.target} <span className="text-charcoal-400">({s.access})</span></span>
              <button onClick={() => removeEntry(i)} className="text-charcoal-400 hover:text-red-500">✕</button>
            </div>
          ))}
        </div>

        <div className="flex gap-2 mb-4">
          <input
            className="input flex-1"
            placeholder={isPool ? 'user name or "household"/"team"' : 'user name'}
            value={newTarget}
            onChange={e => setNewTarget(e.target.value)}
          />
          <select className="input" value={newAccess} onChange={e => setNewAccess(e.target.value)}>
            <option value="read">read</option>
            <option value="contribute">contribute</option>
            <option value="edit">edit</option>
          </select>
          <button className="btn-ghost" onClick={addEntry}>Add</button>
        </div>

        {!isPool && (
          <div className="mb-4">
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Hidden from (comma-separated names)</label>
            <input className="input w-full" value={hidden} onChange={e => setHidden(e.target.value)} />
          </div>
        )}

        {isOwner && (
          <label className="flex items-start gap-2 mb-4 p-3 rounded-lg border border-charcoal-200 dark:border-charcoal-700 bg-charcoal-50 dark:bg-charcoal-800/50">
            <input
              type="checkbox"
              checked={shareData}
              onChange={e => setShareData(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-sm">
              <span className="font-medium">Share underlying data</span>
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">
                When on, everyone this dashboard is shared with sees every block's live data as
                YOU would see it — even data they normally couldn't access on their own. Off by
                default. They never see more than you can see yourself.
              </p>
            </span>
          </label>
        )}

        <div className="flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </div>
    </div>
  )
}
