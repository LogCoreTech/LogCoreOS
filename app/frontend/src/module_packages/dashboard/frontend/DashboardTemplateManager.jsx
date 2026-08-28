import { useEffect, useState } from 'react'
import { dashboardTemplates as templatesApi, dashboards as dashboardsApi } from './api'
import EmojiPicker from '../../../components/EmojiPicker'
import TagInput from '../../../components/TagInput'
import BlockPicker from '../../../components/dashboard/BlockPicker'
import { BLOCK_REGISTRY } from '../../../components/dashboard/blockRegistry'

const SUBJECT_TYPES = [
  { value: '', label: 'None — just a reusable block set' },
  { value: 'contact', label: 'A contact (e.g. one dashboard per client)' },
  { value: 'asset', label: 'An asset (e.g. one dashboard per property)' },
]

// Dashboard templates are the "same dashboard, many instances" mechanism —
// structurally mirrors TemplateManager.jsx (list/edit/share, own/global/shared
// sections, admin gating for global) but the per-template form manages a
// BLOCK LIST instead of field definitions, since what's reusable here is a
// dashboard's block set, not an object's schema. No layout/grid editing here
// by design — a newly-synced block always starts auto-stacked and each
// dashboard instance customizes its own position from there (see
// dashboards_service.py's _sync_blocks_from_template).
export default function DashboardTemplateManager({ templates, user, onClose, onChanged }) {
  const isAdmin = user?.role === 'admin'
  const [view, setView] = useState({ mode: 'list' })
  const [form, setForm] = useState(null)
  const [share, setShare] = useState(null)
  const [blockEditor, setBlockEditor] = useState(null) // { index: null|number } — null = adding new
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [members, setMembers] = useState([])
  const [roles, setRoles] = useState([])

  useEffect(() => {
    dashboardsApi.members().then(m => setMembers((m || []).map(x => x.name))).catch(() => {})
    dashboardsApi.roles().then(r => setRoles(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])

  const own = templates.filter(t => t._scope === 'own')
  const global = templates.filter(t => t._scope === 'global')
  const shared = templates.filter(t => t._scope === 'shared')

  function startNew(owner) {
    setForm({ isNew: true, id: null, owner, label: '', icon: '📊', subject_type: '', blocks: [], restrict_roles: [] })
    setError('')
    setView({ mode: 'edit' })
  }

  function startEdit(t) {
    setForm({
      isNew: false,
      id: t.id,
      owner: t._scope === 'global' ? 'global' : 'me',
      label: t.label,
      icon: t.icon || '📊',
      subject_type: t.subject_type || '',
      blocks: t.blocks || [],
      restrict_roles: t.restrict_roles || [],
    })
    setError('')
    setView({ mode: 'edit' })
  }

  function startShare(t) {
    const targets = (t.shared_with || []).map(s => s.target)
    setShare({
      template: t,
      roles: targets.filter(x => roles.includes(x) || x === 'team' || x === 'household'),
      users: targets.filter(x => members.includes(x)),
    })
    setError('')
    setView({ mode: 'share' })
  }

  async function save() {
    setLoading(true); setError('')
    try {
      const payload = {
        label: form.label || 'Untitled Template',
        icon: form.icon,
        subject_type: form.subject_type || null,
        blocks: form.blocks,
      }
      if (form.isNew) {
        await templatesApi.create({ owner: form.owner, ...payload })
      } else {
        if (form.owner === 'global') payload.restrict_roles = form.restrict_roles
        await templatesApi.update(form.id, payload)
      }
      await onChanged()
      setView({ mode: 'list' })
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  async function saveShare() {
    setLoading(true); setError('')
    try {
      const shared_with = [...share.roles, ...share.users].map(target => ({ target }))
      await templatesApi.access(share.template.id, { shared_with })
      await onChanged()
      setView({ mode: 'list' })
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  async function remove(t) {
    if (!confirm(`Delete template "${t.label}"? Dashboards already using it must be deleted or detached first.`)) return
    setError('')
    try { await templatesApi.remove(t.id); await onChanged() }
    catch (err) { setError(err.message) }
  }

  async function leave(t) {
    setError('')
    try { await templatesApi.leave(t.id); await onChanged() }
    catch (err) { setError(err.message) }
  }

  function addBlock(type, config) {
    setBlockEditor(null)
    setForm(f => ({ ...f, blocks: [...f.blocks, { type, config }] }))
  }

  function saveBlockConfig(config) {
    const i = blockEditor.index
    setBlockEditor(null)
    setForm(f => ({ ...f, blocks: f.blocks.map((b, j) => (j === i ? { ...b, config } : b)) }))
  }

  function removeBlock(i) {
    setForm(f => ({ ...f, blocks: f.blocks.filter((_, j) => j !== i) }))
  }

  function moveBlock(i, dir) {
    setForm(f => {
      const blocks = [...f.blocks]
      const j = i + dir
      if (j < 0 || j >= blocks.length) return f
      ;[blocks[i], blocks[j]] = [blocks[j], blocks[i]]
      return { ...f, blocks }
    })
  }

  function blockUsesSubject(block) {
    return Object.values(block.config || {}).some(v => v === '$subject')
  }

  function Row({ t, actions }) {
    return (
      <div className="flex items-center gap-2 p-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors">
        <span className="text-lg w-7 text-center">{t.icon || '📊'}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{t.label}</p>
          <p className="text-xs text-charcoal-400 truncate">
            {(t.blocks || []).length} block{(t.blocks || []).length !== 1 ? 's' : ''}
            {t.subject_type ? ` · per-${t.subject_type}` : ''}
            {t._scope === 'shared' && t._owner ? ` · from ${t._owner}` : ''}
          </p>
        </div>
        {actions}
      </div>
    )
  }

  const title = view.mode === 'edit'
    ? (form.isNew ? 'New Dashboard Template' : `Edit ${form.label}`)
    : view.mode === 'share' ? `Share ${share.template.label}` : 'Dashboard Templates'

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-lg">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        {view.mode === 'list' && (
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-500">My templates</p>
                <button onClick={() => startNew('me')} className="btn-primary text-xs px-2.5 py-1">＋ New</button>
              </div>
              {own.length === 0 ? (
                <p className="text-xs text-charcoal-400 py-2">
                  None yet. A template is a reusable dashboard block set — build it once, create as many
                  dashboards from it as you need, and editing the template updates all of them.
                </p>
              ) : own.map(t => (
                <Row key={t.id} t={t} actions={
                  <>
                    <button onClick={() => startShare(t)} className="btn-ghost text-xs px-2 py-1">Share</button>
                    <button onClick={() => startEdit(t)} className="btn-ghost text-xs px-2 py-1">Edit</button>
                    <button onClick={() => remove(t)} className="text-red-400 hover:text-red-500 text-xs px-1">✕</button>
                  </>
                } />
              ))}
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-500">Global{isAdmin ? ' (admin)' : ''}</p>
                {isAdmin && (
                  <button onClick={() => startNew('global')} className="btn-ghost text-xs px-2.5 py-1">＋ New</button>
                )}
              </div>
              {global.length === 0 ? (
                <p className="text-xs text-charcoal-400 py-2">No global templates.</p>
              ) : global.map(t => (
                <Row key={t.id} t={t} actions={isAdmin ? (
                  <>
                    <button onClick={() => startEdit(t)} className="btn-ghost text-xs px-2 py-1">Edit</button>
                    <button onClick={() => remove(t)} className="text-red-400 hover:text-red-500 text-xs px-1">✕</button>
                  </>
                ) : <span className="text-[10px] text-charcoal-400">available</span>} />
              ))}
            </div>

            {shared.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-500 mb-1">Shared with me</p>
                {shared.map(t => (
                  <Row key={t.id} t={t} actions={
                    <button onClick={() => leave(t)} className="text-red-400 hover:text-red-500 text-xs px-2 py-1">Leave</button>
                  } />
                ))}
              </div>
            )}
            {error && <p className="text-red-500 text-sm">{error}</p>}
          </div>
        )}

        {view.mode === 'share' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Share with roles</label>
              <TagInput
                value={share.roles}
                onChange={r => setShare(s => ({ ...s, roles: r }))}
                suggestions={[...roles, 'team', 'household']}
                strict
                placeholder="Pick roles…"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Share with people</label>
              <TagInput
                value={share.users}
                onChange={u => setShare(s => ({ ...s, users: u }))}
                suggestions={members.filter(m => m !== user?.name)}
                strict
                placeholder="Pick people…"
              />
            </div>
            <p className="text-[10px] text-charcoal-400">Each person gets a request to accept before the template appears for them.</p>
            {error && <p className="text-red-500 text-sm">{error}</p>}
            <div className="flex gap-2 pt-1">
              <button onClick={() => setView({ mode: 'list' })} className="btn-ghost flex-1">Back</button>
              <button onClick={saveShare} disabled={loading} className="btn-primary flex-1">{loading ? 'Saving…' : 'Save sharing'}</button>
            </div>
          </div>
        )}

        {view.mode === 'edit' && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <label className="block text-sm font-medium mb-1">Label</label>
                <input type="text" value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} placeholder="Client Overview" className="input" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Icon</label>
                <EmojiPicker value={form.icon} onChange={icon => setForm(f => ({ ...f, icon }))} />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Subject</label>
              <select
                className="input w-full"
                value={form.subject_type}
                onChange={e => setForm(f => ({ ...f, subject_type: e.target.value }))}
              >
                {SUBJECT_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <p className="text-[10px] text-charcoal-400 mt-1">
                Optional. When set, each dashboard made from this template picks one contact/asset, and
                any block field marked &quot;use this dashboard&apos;s own {form.subject_type || 'subject'}&quot;
                shows that dashboard&apos;s own record instead of a fixed one.
              </p>
            </div>

            {form.owner === 'global' && (
              <div>
                <label className="block text-sm font-medium mb-1">Restrict to roles <span className="text-charcoal-400 font-normal">(empty = everyone)</span></label>
                <TagInput
                  value={form.restrict_roles}
                  onChange={rr => setForm(f => ({ ...f, restrict_roles: rr }))}
                  suggestions={roles}
                  strict
                  placeholder="Pick roles…"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-1">Blocks <span className="text-charcoal-400 font-normal">(shown in this order; every dashboard from this template stays synced to this set)</span></label>
              <div className="space-y-1.5">
                {form.blocks.map((b, i) => {
                  const meta = BLOCK_REGISTRY[b.type]
                  return (
                    <div key={b.id || i} className="flex items-center gap-1.5 border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-2">
                      <span className="w-6 text-center shrink-0">{meta?.icon || '▫️'}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{meta?.label || b.type}</p>
                        {blockUsesSubject(b) && <p className="text-[10px] text-orange-500">🔗 uses this dashboard&apos;s subject</p>}
                      </div>
                      <button type="button" onClick={() => moveBlock(i, -1)} className="text-charcoal-400 hover:text-orange-500 px-0.5 shrink-0" title="Move up">↑</button>
                      <button type="button" onClick={() => moveBlock(i, 1)} className="text-charcoal-400 hover:text-orange-500 px-0.5 shrink-0" title="Move down">↓</button>
                      <button type="button" onClick={() => setBlockEditor({ index: i })} className="text-charcoal-400 hover:text-orange-500 px-1 shrink-0 text-xs">Edit</button>
                      <button type="button" onClick={() => removeBlock(i)} className="text-red-400 hover:text-red-500 px-0.5 shrink-0">✕</button>
                    </div>
                  )
                })}
                {form.blocks.length === 0 && (
                  <p className="text-xs text-charcoal-400 py-1">No blocks yet.</p>
                )}
                <button type="button" onClick={() => setBlockEditor({ index: null })} className="btn-ghost text-xs px-3 py-1.5">
                  ＋ Add block
                </button>
              </div>
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}
            <div className="flex gap-2 pt-1">
              <button type="button" onClick={() => setView({ mode: 'list' })} className="btn-ghost flex-1">Back</button>
              <button type="button" onClick={save} disabled={loading} className="btn-primary flex-1">
                {loading ? 'Saving…' : 'Save Template'}
              </button>
            </div>
          </div>
        )}
      </div>

      {blockEditor && (
        <BlockPicker
          editingBlock={blockEditor.index !== null ? form.blocks[blockEditor.index] : null}
          onAdd={addBlock}
          onSave={saveBlockConfig}
          onClose={() => setBlockEditor(null)}
          templateMode
          subjectType={form.subject_type || null}
        />
      )}
    </div>
  )
}
