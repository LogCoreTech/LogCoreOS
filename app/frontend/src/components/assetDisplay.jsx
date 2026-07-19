import { useState, useEffect } from 'react'
import { assets as assetsApi, contacts as contactsApi } from '../lib/api'
import ContactPicker from './contacts/ContactPicker'

// Shared asset display helpers used by both the read-only AssetView and the
// AssetModal editor. Kept in their own module so neither component imports the
// other (would be a circular import).

// Render a history entry's changes tolerantly — a change value is normally an
// [old, new] pair, but never trust the shape (legacy/hand-edited data would
// otherwise throw "not iterable" and crash the whole modal via ErrorBoundary).
export function formatChanges(changes) {
  return Object.entries(changes || {})
    .map(([k, v]) => {
      const key = k.replace('fields.', '')
      if (Array.isArray(v)) {
        const [o, n] = v
        return `${key}: ${o ?? '∅'}→${n ?? '∅'}`
      }
      return `${key}: ${v == null ? '∅' : typeof v === 'object' ? JSON.stringify(v) : v}`
    })
    .join(', ')
}

// Human-readable value for one template field in view mode. Returns null when
// the field is empty so the caller can show a muted placeholder. Booleans are
// resolved before the empty check so `false` reads as "No" (not blank).
export function fieldDisplay(def, value) {
  if (def?.type === 'boolean') return value === true ? 'Yes' : 'No'
  if (value === null || value === undefined || value === '') return null
  return String(value)
}

// Contact-type field: picker over CRM contacts, stores the contact id.
// Self-contained (fetches the list itself) so every FieldInput caller gets it
// without prop drilling; falls back to plain text when Contacts is off.
export function ContactFieldInput({ def, value, onChange }) {
  const [all, setAll] = useState([])
  useEffect(() => {
    contactsApi.list().then(r => setAll(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])
  const name = all.find(c => c.id === value)?.name || (value ? '(contact)' : '')
  return (
    <ContactPicker
      label={def.label}
      placeholder="Pick a contact…"
      value={{ name, contactId: value || null }}
      onChange={(_n, contactId) => onChange(contactId || '')}
    />
  )
}

// Field input for one template field definition — shared by the editor form and
// the read-first view's inline contribute controls. Module-level per MEMORY.md rule.
export function FieldInput({ def, value, onChange }) {
  if (def.type === 'contact') {
    return <ContactFieldInput def={def} value={value} onChange={onChange} />
  }
  if (def.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-sm py-2 cursor-pointer">
        <input
          type="checkbox"
          checked={value === true}
          onChange={e => onChange(e.target.checked)}
          className="accent-orange-500 w-4 h-4"
        />
        <span>{def.label}</span>
      </label>
    )
  }
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{def.label}</label>
      {def.type === 'select' ? (
        <select value={value ?? ''} onChange={e => onChange(e.target.value)} className="input">
          <option value="">—</option>
          {(def.options || []).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : def.type === 'number' ? (
        <input
          type="number"
          step="any"
          value={value ?? ''}
          onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          className="input"
        />
      ) : def.type === 'date' ? (
        <input type="date" value={value ?? ''} onChange={e => onChange(e.target.value)} className="input" />
      ) : (
        <input type="text" value={value ?? ''} onChange={e => onChange(e.target.value)} className="input" />
      )}
    </div>
  )
}

const CAP_ADDS = [
  { id: 'comments', label: 'Comments' },
  { id: 'files', label: 'Files' },
  { id: 'children', label: 'Items inside' },
]

// Inline checkbox panel configuring what a "contribute" share/contributor can
// touch: which template fields they may change + what they may add. Rendered
// inline (not absolutely positioned) so a scrolling modal can't clip it.
export function CapsSelector({ caps, onChange, templateFields }) {
  const value = caps || { fields: [], add: ['comments'] }

  function toggle(listKey, id) {
    const list = value[listKey] || []
    const next = list.includes(id) ? list.filter(x => x !== id) : [...list, id]
    onChange({ ...value, [listKey]: next })
  }

  return (
    <div className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-2 space-y-2 text-xs">
      <div>
        <p className="font-medium text-charcoal-500 dark:text-charcoal-400 mb-1">Can change</p>
        {(templateFields || []).length === 0 ? (
          <p className="text-charcoal-400">No template fields</p>
        ) : (
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {templateFields.map(f => (
              <label key={f.key} className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(value.fields || []).includes(f.key)}
                  onChange={() => toggle('fields', f.key)}
                  className="accent-orange-500 w-3.5 h-3.5"
                />
                {f.label || f.key}
              </label>
            ))}
          </div>
        )}
      </div>
      <div>
        <p className="font-medium text-charcoal-500 dark:text-charcoal-400 mb-1">Can add</p>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {CAP_ADDS.map(a => (
            <label key={a.id} className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={(value.add || []).includes(a.id)}
                onChange={() => toggle('add', a.id)}
                className="accent-orange-500 w-3.5 h-3.5"
              />
              {a.label}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}

export function AttachmentThumb({ assetId, file, canEdit, onDelete }) {
  const [url, setUrl] = useState(null)
  const isImage = file.mime.startsWith('image/')

  useEffect(() => {
    let objectUrl = null
    if (isImage) {
      assetsApi.fileBlob(assetId, file.id)
        .then(blob => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) })
        .catch(() => {})
    }
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [assetId, file.id])

  async function open() {
    try {
      const blob = await assetsApi.fileBlob(assetId, file.id)
      const u = URL.createObjectURL(blob)
      window.open(u, '_blank')
      setTimeout(() => URL.revokeObjectURL(u), 60000)
    } catch { /* ignore */ }
  }

  return (
    <div className="relative group border border-charcoal-200 dark:border-charcoal-700 rounded-lg overflow-hidden">
      <button type="button" onClick={open} className="block w-full" title={file.filename}>
        {isImage && url ? (
          <img src={url} alt={file.filename} className="w-full h-20 object-cover" />
        ) : (
          <div className="w-full h-20 flex flex-col items-center justify-center text-charcoal-500 dark:text-charcoal-400">
            <span className="text-xl">📄</span>
            <span className="text-[10px] px-1 truncate max-w-full">{file.filename}</span>
          </div>
        )}
      </button>
      {canEdit && (
        <button
          type="button"
          onClick={() => onDelete(file)}
          className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
          title="Delete file"
        >
          ✕
        </button>
      )}
    </div>
  )
}
