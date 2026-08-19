import { useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'
import EmojiPicker from '../EmojiPicker'
import ContactPicker from '../contacts/ContactPicker'
import AssetPickerField from '../AssetPickerField'

/**
 * Per-dashboard options menu — rename, change icon, and the actions that
 * used to be a loose row of buttons in the edit toolbar (Share, Set as
 * default, Delete). Consolidating them here also shrinks that toolbar down
 * to just "+ Add Block" / "Save Layout" / "⚙ Settings", which was the
 * likely cause of the edit toolbar overflowing/wrapping awkwardly on narrow
 * mobile screens (owner report, 2026-08-05).
 */
export default function DashboardSettingsModal({ dashboard, isOwner, user, workspace, onClose, onSaved, onShare, onSetDefault, onDelete }) {
  const [name, setName] = useState(dashboard.name || '')
  const [icon, setIcon] = useState(dashboard.icon || '📊')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [changingSubject, setChangingSubject] = useState(false)
  const [subjectId, setSubjectId] = useState(dashboard.subject_id || null)
  const [crossWorkspace, setCrossWorkspace] = useState(!!dashboard.cross_workspace)
  const otherWorkspace = workspace === 'business' ? 'personal' : 'business'

  const dirty = name.trim() !== dashboard.name || icon !== dashboard.icon
  const isTemplated = !!dashboard.template_id

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

  async function saveSubject() {
    setSaving(true)
    setError(null)
    try {
      await dashboardsApi.setSubject(dashboard.id, subjectId)
      setChangingSubject(false)
      await onSaved()
    } catch (e) {
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  // Settings-only toggle (2026-08-18, owner: "dashboards need the toggle
  // option to set to one workspace only or both. even with both workspaces
  // allowed for that user. just so it doesnt spam the picker on either
  // workspace"). Off by default — a dashboard stays scoped to the workspace
  // it was created in, same as before this existed, unless explicitly opted
  // in. Saved immediately on toggle (like the pool-visibility toggles
  // elsewhere in this app) rather than batched with the Save changes button
  // above, since it's a structural setting, not a form field.
  async function saveCrossWorkspace(next) {
    setCrossWorkspace(next)
    setSaving(true)
    setError(null)
    try {
      await dashboardsApi.update(dashboard.id, { cross_workspace: next })
      await onSaved()
    } catch (e) {
      setCrossWorkspace(!next)
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function detach() {
    if (!window.confirm('Detach from template? This dashboard keeps its current blocks and layout, but stops updating when the template changes, and its blocks become individually editable again.')) return
    setSaving(true)
    setError(null)
    try {
      await dashboardsApi.detachTemplate(dashboard.id)
      await onSaved()
    } catch (e) {
      setError(e.message || 'Failed to detach')
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
              {dirty && (
                <button className="btn-primary text-sm" onClick={save} disabled={saving}>
                  {saving ? 'Saving…' : 'Save changes'}
                </button>
              )}
              {(user?.workspaces || []).length > 1 && (
                <label className="flex items-center justify-between gap-3 cursor-pointer">
                  <span className="text-sm">Also show in my {otherWorkspace} workspace</span>
                  <input
                    type="checkbox"
                    checked={crossWorkspace}
                    onChange={e => saveCrossWorkspace(e.target.checked)}
                    disabled={saving}
                  />
                </label>
              )}
              <div className="border-t border-charcoal-200 dark:border-charcoal-700" />
            </>
          )}

          {isTemplated && (
            <>
              <div className="space-y-2">
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  Uses template: <span className="font-medium">{dashboard.template_label || 'template'}</span>
                  {' '}— blocks stay in sync with it; layout is yours to customize.
                </p>

                {changingSubject ? (
                  <div className="space-y-2">
                    {dashboard.subject_type === 'contact' && (
                      <ContactPicker
                        label="Contact"
                        value={{ contactId: subjectId }}
                        onChange={(_name, id) => setSubjectId(id)}
                        placeholder="Search contacts…"
                      />
                    )}
                    {dashboard.subject_type === 'asset' && (
                      <AssetPickerField label="Asset" value={subjectId} onChange={setSubjectId} />
                    )}
                    <div className="flex gap-2">
                      <button className="btn-ghost text-sm flex-1" onClick={() => { setChangingSubject(false); setSubjectId(dashboard.subject_id || null) }}>Cancel</button>
                      <button className="btn-primary text-sm flex-1" onClick={saveSubject} disabled={saving || !subjectId}>
                        {saving ? 'Saving…' : 'Save subject'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800" onClick={() => setChangingSubject(true)}>
                    Change subject
                  </button>
                )}

                {isOwner && !changingSubject && (
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800" onClick={detach} disabled={saving}>
                    Detach from template
                  </button>
                )}
              </div>
              <div className="border-t border-charcoal-200 dark:border-charcoal-700" />
            </>
          )}

          {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}

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
