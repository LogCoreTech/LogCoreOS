import { useState, useEffect } from 'react'
import { assets as assetsApi } from '../lib/api'
import EmojiPicker from './EmojiPicker'
import TagInput from './TagInput'

const FIELD_TYPES = ['text', 'number', 'date', 'boolean', 'select', 'contact']
const BLANK_FIELD = { key: '', label: '', type: 'text', options: [], default: '' }

function coerceDefault(f) {
  if (f.type === 'number') return Number(f.default)
  if (f.type === 'boolean') return f.default === true || f.default === 'true'
  return f.default
}

// Templates are the premade object structures (e.g. "Parcel"). Users manage their
// OWN templates; admins manage GLOBAL ones (restrictable by role). Personal
// templates can be shared to roles/users via an accept/decline handshake.
export default function TemplateManager({ templates, user, onClose, onChanged }) {
  const isAdmin = user?.role === 'admin'
  const [view, setView] = useState({ mode: 'list' }) // list | edit | share
  const [form, setForm] = useState(null)
  const [share, setShare] = useState(null) // { template, roles:[], users:[] }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [members, setMembers] = useState([])
  const [roles, setRoles] = useState([])

  useEffect(() => {
    assetsApi.members().then(m => setMembers((m || []).map(x => x.name))).catch(() => {})
    assetsApi.roles().then(r => setRoles(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])

  const own = templates.filter(t => t._scope === 'own')
  const global = templates.filter(t => t._scope === 'global')
  const shared = templates.filter(t => t._scope === 'shared')

  function startNew(owner) {
    setForm({ isNew: true, id: null, owner, key: '', label: '', icon: '', fields: [], restrict_roles: [] })
    setError('')
    setView({ mode: 'edit' })
  }

  function startEdit(t) {
    setForm({
      isNew: false,
      id: t.id,
      owner: t._scope === 'global' ? 'global' : 'me',
      key: t.key,
      label: t.label,
      icon: t.icon || '',
      restrict_roles: t.restrict_roles || [],
      fields: (t.fields || []).map(f => ({
        key: f.key, label: f.label, type: f.type,
        options: f.options || [], default: f.default ?? '',
      })),
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

  function setField(i, patch) {
    setForm(f => ({ ...f, fields: f.fields.map((x, j) => (j === i ? { ...x, ...patch } : x)) }))
  }
  function moveField(i, dir) {
    setForm(f => {
      const fields = [...f.fields]
      const j = i + dir
      if (j < 0 || j >= fields.length) return f
      ;[fields[i], fields[j]] = [fields[j], fields[i]]
      return { ...f, fields }
    })
  }

  async function save() {
    setLoading(true); setError('')
    try {
      const payload = {
        label: form.label || form.key,
        icon: form.icon,
        fields: form.fields.map(f => ({
          key: f.key.trim(),
          label: f.label || f.key,
          type: f.type,
          ...(f.type === 'select' ? { options: f.options } : {}),
          ...(f.default !== '' && f.default !== null ? { default: coerceDefault(f) } : {}),
        })),
      }
      if (form.isNew) {
        await assetsApi.createTemplate({ key: form.key.trim(), owner: form.owner, ...payload })
      } else {
        if (form.owner === 'global') payload.restrict_roles = form.restrict_roles
        await assetsApi.updateTemplate(form.id, payload)
      }
      await onChanged()
      setView({ mode: 'list' })
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  async function saveShare() {
    setLoading(true); setError('')
    try {
      const shared_with = [...share.roles, ...share.users].map(target => ({ target }))
      await assetsApi.templateAccess(share.template.id, { shared_with })
      await onChanged()
      setView({ mode: 'list' })
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  async function remove(t) {
    if (!confirm(`Delete template "${t.label}"?`)) return
    setError('')
    try { await assetsApi.removeTemplate(t.id); await onChanged() }
    catch (err) { setError(err.message) }
  }

  async function leave(t) {
    setError('')
    try { await assetsApi.leaveTemplate(t.id); await onChanged() }
    catch (err) { setError(err.message) }
  }

  async function insertExample(owner) {
    setError('')
    try { await assetsApi.insertExample(owner); await onChanged() }
    catch (err) { setError(err.message) }
  }

  function Row({ t, actions }) {
    return (
      <div className="flex items-center gap-2 p-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors">
        <span className="text-lg w-7 text-center">{t.icon || '▫️'}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{t.label}</p>
          <p className="text-xs text-charcoal-400 truncate">
            {t.key} · {(t.fields || []).length} field{(t.fields || []).length !== 1 ? 's' : ''}
            {t._scope === 'shared' && t._owner ? ` · from ${t._owner}` : ''}
          </p>
        </div>
        {actions}
      </div>
    )
  }

  const title = view.mode === 'edit'
    ? (form.isNew ? 'New Template' : `Edit ${form.label}`)
    : view.mode === 'share' ? `Share ${share.template.label}` : 'Templates'

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-lg">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        {view.mode === 'list' && (
          <div className="space-y-4">
            {/* My templates */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-500">My templates</p>
                <div className="flex gap-2">
                  <button onClick={() => insertExample('me')} className="text-xs text-charcoal-400 hover:text-orange-500">Insert example</button>
                  <button onClick={() => startNew('me')} className="btn-primary text-xs px-2.5 py-1">＋ New</button>
                </div>
              </div>
              {own.length === 0 ? (
                <p className="text-xs text-charcoal-400 py-2">None yet. A template is a reusable object structure (e.g. a "Parcel" with acreage, price, status).</p>
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

            {/* Global */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-500">Global{isAdmin ? ' (admin)' : ''}</p>
                {isAdmin && (
                  <div className="flex gap-2">
                    <button onClick={() => insertExample('global')} className="text-xs text-charcoal-400 hover:text-orange-500">Insert example</button>
                    <button onClick={() => startNew('global')} className="btn-ghost text-xs px-2.5 py-1">＋ New</button>
                  </div>
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

            {/* Shared with me */}
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
                <input type="text" value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} placeholder="Parcel" className="input" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Icon</label>
                <EmojiPicker value={form.icon} onChange={icon => setForm(f => ({ ...f, icon }))} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Key <span className="text-charcoal-400 font-normal">(a-z, 0-9, _ — permanent)</span>
              </label>
              <input
                type="text"
                value={form.key}
                onChange={e => setForm(f => ({ ...f, key: e.target.value.toLowerCase() }))}
                placeholder="parcel"
                disabled={!form.isNew}
                className="input font-mono disabled:opacity-60"
              />
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
              <label className="block text-sm font-medium mb-1">Fields <span className="text-charcoal-400 font-normal">(shown in this order)</span></label>
              <div className="space-y-2">
                {form.fields.map((f, i) => (
                  <div key={i} className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-2 space-y-2">
                    <div className="flex items-center gap-1.5">
                      <input type="text" value={f.key} onChange={e => setField(i, { key: e.target.value.toLowerCase() })} placeholder="key" className="input !py-1 !w-28 font-mono text-xs" />
                      <input type="text" value={f.label} onChange={e => setField(i, { label: e.target.value })} placeholder="Label" className="input !py-1 flex-1" />
                      <select value={f.type} onChange={e => setField(i, { type: e.target.value })} className="input !py-1 !w-24">
                        {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <button type="button" onClick={() => moveField(i, -1)} className="text-charcoal-400 hover:text-orange-500 px-0.5" title="Move up">↑</button>
                      <button type="button" onClick={() => moveField(i, 1)} className="text-charcoal-400 hover:text-orange-500 px-0.5" title="Move down">↓</button>
                      <button type="button" onClick={() => setForm(fm => ({ ...fm, fields: fm.fields.filter((_, j) => j !== i) }))} className="text-red-400 hover:text-red-500 px-0.5">✕</button>
                    </div>
                    {f.type === 'select' && (
                      <TagInput value={f.options || []} onChange={options => setField(i, { options })} placeholder="Add an option…" />
                    )}
                    <input
                      type="text"
                      value={String(f.default ?? '')}
                      onChange={e => setField(i, { default: e.target.value })}
                      placeholder="default (optional)"
                      className="input !py-1 w-full text-xs"
                    />
                  </div>
                ))}
                <button type="button" onClick={() => setForm(f => ({ ...f, fields: [...f.fields, { ...BLANK_FIELD }] }))} className="btn-ghost text-xs px-3 py-1.5">
                  ＋ Add field
                </button>
              </div>
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}
            <div className="flex gap-2 pt-1">
              <button type="button" onClick={() => setView({ mode: 'list' })} className="btn-ghost flex-1">Back</button>
              <button type="button" onClick={save} disabled={loading || !form.key.trim()} className="btn-primary flex-1">
                {loading ? 'Saving…' : 'Save Template'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
