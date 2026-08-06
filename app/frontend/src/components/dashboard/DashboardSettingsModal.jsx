import { useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'
import EmojiPicker from '../EmojiPicker'

/**
 * Per-dashboard options menu — rename, change icon, and the actions that
 * used to be a loose row of buttons in the edit toolbar (Share, Set as
 * default, Delete). Consolidating them here also shrinks that toolbar down
 * to just "+ Add Block" / "Save Layout" / "⚙ Settings", which was the
 * likely cause of the edit toolbar overflowing/wrapping awkwardly on narrow
 * mobile screens (owner report, 2026-08-05).
 */
export default function DashboardSettingsModal({ dashboard, isOwner, onClose, onSaved, onShare, onSetDefault, onDelete }) {
  const [name, setName] = useState(dashboard.name || '')
  const [icon, setIcon] = useState(dashboard.icon || '📊')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const dirty = name.trim() !== dashboard.name || icon !== dashboard.icon

  async function save() {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await dashboardsApi.update(dashboard.id, { name: name.trim(), icon })
      await onSaved()
    } catch (e) {
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Dashboard Settings</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>

        <div className="space-y-4">
          {isOwner && (
            <>
              <div className="flex gap-3 items-end">
                <div className="w-28 shrink-0">
                  <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Icon</label>
                  <EmojiPicker value={icon} onChange={setIcon} />
                </div>
                <div className="flex-1 min-w-0">
                  <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Name</label>
                  <input
                    className="input w-full"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    maxLength={80}
                  />
                </div>
              </div>
              {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}
              {dirty && (
                <button className="btn-primary text-sm" onClick={save} disabled={saving}>
                  {saving ? 'Saving…' : 'Save changes'}
                </button>
              )}
              <div className="border-t border-charcoal-200 dark:border-charcoal-700" />
            </>
          )}

          <div className="space-y-1">
            <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800" onClick={onShare}>
              Share
            </button>
            <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800" onClick={onSetDefault}>
              Set as default
            </button>
            <button
              className="w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 hover:bg-red-100 dark:hover:bg-red-900/30"
              onClick={onDelete}
            >
              Delete dashboard
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
