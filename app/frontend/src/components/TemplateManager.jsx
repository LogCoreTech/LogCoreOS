import { useState } from 'react'
import { assets as assetsApi } from '../lib/api'
import EmojiPicker from './EmojiPicker'
import TagInput from './TagInput'

const FIELD_TYPES = ['text', 'number', 'date', 'boolean', 'select']

const BLANK_FIELD = { key: '', label: '', type: 'text', options: [], default: '' }

// Admin-only template editor: templates are the premade object structures
// (e.g. "Parcel") users instantiate from. Field order here IS the display order.
export default function TemplateManager({ templates, onClose, onChanged }) {
  const [editing, setEditing] = useState(null) // null = list view; {} = new; {key,...} = edit
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function startNew() {
    setForm({ key: '', label: '', icon: '', fields: [] })
    setEditing({ isNew: true })
    setError('')
  }

  function startEdit(t) {
    setForm({
      key: t.key,
      label: t.label,
      icon: t.icon || '',
      fields: (t.fields || []).map(f => ({
        key: f.key,
        label: f.label,
        type: f.type,
        options: f.options || [],
        default: f.default ?? '',
      })),
    })
    setEditing({ isNew: false })
    setError('')
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
    setLoading(true)
    setError('')
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
      if (editing.isNew) {
        await assetsApi.createTemplate({ key: form.key.trim(), ...payload })
      } else {
        await assetsApi.updateTemplate(form.key, payload)
      }
      await onChanged()
      setEditing(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function coerceDefault(f) {
    if (f.type === 'number') return Number(f.default)
    if (f.type === 'boolean') return f.default === true || f.default === 'true'
    return f.default
  }

  async function remove(t) {
    if (!confirm(`Delete template "${t.label}"?`)) return
    setError('')
    try {
      await assetsApi.removeTemplate(t.key)
      await onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  async function insertExample() {
    setError('')
    try {
      await assetsApi.insertExample()
      await onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-lg">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">{editing ? (editing.isNew ? 'New Template' : `Edit ${form.label}`) : 'Templates'}</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        {!editing ? (
          <div className="space-y-2">
            {templates.length === 0 && (
              <p className="text-sm text-charcoal-400 py-4 text-center">
                No templates yet. A template is the premade structure of an object — e.g. a
                "Parcel" with acreage, price, and status fields. Create one, or insert an
                editable example.
              </p>
            )}
            {templates.map(t => (
              <div key={t.key} className="flex items-center gap-2 p-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors">
                <span className="text-lg w-7 text-center">{t.icon || '▫️'}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{t.label}</p>
                  <p className="text-xs text-charcoal-400 truncate">
                    {t.key} · {(t.fields || []).length} field{(t.fields || []).length !== 1 ? 's' : ''}
                  </p>
                </div>
                <button onClick={() => startEdit(t)} className="btn-ghost text-xs px-2 py-1">Edit</button>
                <button onClick={() => remove(t)} className="text-red-400 hover:text-red-500 text-xs px-1">✕</button>
              </div>
            ))}
            {error && <p className="text-red-500 text-sm">{error}</p>}
            <div className="flex gap-2 pt-2">
              <button onClick={insertExample} className="btn-ghost text-xs px-3 py-1.5">Insert example</button>
              <button onClick={startNew} className="btn-primary text-xs px-3 py-1.5 ml-auto">＋ New Template</button>
            </div>
          </div>
        ) : (
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
                Key {editing.isNew ? <span className="text-charcoal-400 font-normal">(a-z, 0-9, _ — permanent)</span> : <span className="text-charcoal-400 font-normal">(permanent)</span>}
              </label>
              <input
                type="text"
                value={form.key}
                onChange={e => setForm(f => ({ ...f, key: e.target.value.toLowerCase() }))}
                placeholder="parcel"
                disabled={!editing.isNew}
                className="input font-mono disabled:opacity-60"
              />
            </div>

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
                      <TagInput
                        value={f.options || []}
                        onChange={options => setField(i, { options })}
                        placeholder="Add an option…"
                      />
                    )}
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        value={String(f.default ?? '')}
                        onChange={e => setField(i, { default: e.target.value })}
                        placeholder="default (optional)"
                        className="input !py-1 flex-1 text-xs"
                      />
                    </div>
                  </div>
                ))}
                <button type="button" onClick={() => setForm(f => ({ ...f, fields: [...f.fields, { ...BLANK_FIELD }] }))} className="btn-ghost text-xs px-3 py-1.5">
                  ＋ Add field
                </button>
              </div>
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}

            <div className="flex gap-2 pt-1">
              <button type="button" onClick={() => setEditing(null)} className="btn-ghost flex-1">Back</button>
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
