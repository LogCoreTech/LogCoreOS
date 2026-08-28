import { useEffect, useState } from 'react'
import { contacts as contactsApi } from '../../../module_packages/contacts/frontend/api'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'
import TagInput from '../../../components/TagInput'

const FIELD_TYPES = ['text', 'number', 'date', 'boolean', 'select']
const BLANK_FIELD = { key: '', label: '', type: 'text', options: [], applies_to: ['person', 'company'] }

// Instance-level custom field definitions for Contacts — the same 5 scalar
// types Assets templates use, but a single flat global list (no per-user
// ownership/sharing) since Contacts custom fields have always been
// admin-only. Each field is scoped to person, company, or both; a company
// contact never sees a person-only field and vice versa (ContactModal.jsx /
// ContactDetail.jsx filter by contact.type on the way in).
export default function ContactFields() {
  const [fields, setFields] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    contactsApi.fields()
      .then(r => setFields((Array.isArray(r) ? r : []).map(f => ({ ...f, applies_to: f.applies_to || ['person', 'company'] }))))
      .catch(() => setError('Failed to load custom fields'))
      .finally(() => setLoading(false))
  }, [])

  function setField(i, patch) {
    setFields(fs => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)))
  }

  function moveField(i, dir) {
    setFields(fs => {
      const next = [...fs]
      const j = i + dir
      if (j < 0 || j >= next.length) return fs
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }

  function removeField(i) {
    setFields(fs => fs.filter((_, j) => j !== i))
  }

  function addField() {
    setFields(fs => [...fs, { ...BLANK_FIELD }])
  }

  // A field with applies_to: [] would be saved by the backend as "both"
  // anyway (its own safety default) — block that mismatch client-side by
  // never letting the last checked type be unchecked, same guard shape as
  // ContactModal's PrioritiesEditor keeping at least one category.
  function toggleAppliesTo(i, type) {
    setFields(fs => fs.map((f, j) => {
      if (j !== i) return f
      const current = f.applies_to || []
      if (current.includes(type) && current.length <= 1) return f
      const next = current.includes(type) ? current.filter(t => t !== type) : [...current, type]
      return { ...f, applies_to: next }
    }))
  }

  async function save() {
    setSaving(true); setError(''); setMsg('')
    try {
      const cleaned = fields.filter(f => f.key.trim() && f.label.trim())
      const saved = await contactsApi.setFields(cleaned)
      setFields((Array.isArray(saved) ? saved : []).map(f => ({ ...f, applies_to: f.applies_to || ['person', 'company'] })))
      setMsg('Saved.')
      setTimeout(() => setMsg(''), 3000)
    } catch (err) {
      setError(err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Contact Fields" backTo="/settings/admin" backLabel="Admin Settings" />

      <div className="card p-5 space-y-4">
        <div>
          <h2 className="font-semibold mb-1">Custom Fields</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
            Extra fields shown on every contact, alongside the built-in ones. Scope each field to person
            contacts, company contacts, or both — a company-only field never shows on a person, and vice versa.
          </p>
        </div>

        {loading ? (
          <p className="text-sm text-charcoal-400">Loading…</p>
        ) : (
          <div className="space-y-2">
            {fields.length === 0 && (
              <p className="text-xs text-charcoal-400 py-2">No custom fields yet.</p>
            )}
            {fields.map((f, i) => (
              <div key={i} className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-3 space-y-2">
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={f.key}
                    onChange={e => setField(i, { key: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                    placeholder="key"
                    className="input !py-1 !w-28 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={f.label}
                    onChange={e => setField(i, { label: e.target.value })}
                    placeholder="Label"
                    className="input !py-1 flex-1"
                  />
                  <select value={f.type} onChange={e => setField(i, { type: e.target.value })} className="input !py-1 !w-24">
                    {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <button type="button" onClick={() => moveField(i, -1)} className="text-charcoal-400 hover:text-orange-500 px-0.5" title="Move up">↑</button>
                  <button type="button" onClick={() => moveField(i, 1)} className="text-charcoal-400 hover:text-orange-500 px-0.5" title="Move down">↓</button>
                  <button type="button" onClick={() => removeField(i)} className="text-red-400 hover:text-red-500 px-0.5">✕</button>
                </div>
                {f.type === 'select' && (
                  <TagInput value={f.options || []} onChange={options => setField(i, { options })} placeholder="Add an option…" />
                )}
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-charcoal-400">Shows on:</span>
                  {['person', 'company'].map(type => (
                    <label key={type} className="flex items-center gap-1 cursor-pointer capitalize">
                      <input
                        type="checkbox"
                        checked={(f.applies_to || []).includes(type)}
                        onChange={() => toggleAppliesTo(i, type)}
                        className="accent-orange-500 w-3.5 h-3.5"
                      />
                      {type}
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <button type="button" onClick={addField} className="btn-ghost text-xs px-3 py-1.5">＋ Add field</button>
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}
        {msg && <p className="text-green-600 dark:text-green-400 text-sm">{msg}</p>}
        <button type="button" onClick={save} disabled={saving || loading} className="btn-primary w-full text-sm">
          {saving ? 'Saving…' : 'Save Fields'}
        </button>
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
