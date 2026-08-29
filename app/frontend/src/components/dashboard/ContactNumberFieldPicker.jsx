import { useEffect, useState } from 'react'
import { contacts as contactsApi } from '../../module_packages/contacts/frontend/api'

/**
 * Picks one of the instance's admin-defined number-type custom fields on
 * Contacts. Unlike AssetSelectFieldPicker (which needs a specific asset or
 * template to read fields from, since Assets' fields are per-template),
 * Contacts' custom field DEFINITIONS are global — one instance-wide list —
 * so this needs no assetId/templateId-style dependency at all.
 *
 * Props: value (field key string), onChange(key), label
 */
export default function ContactNumberFieldPicker({ value, onChange, label }) {
  const [fields, setFields] = useState(null)

  useEffect(() => {
    contactsApi.fields().then(setFields).catch(() => setFields([]))
  }, [])

  const numberFields = (fields || []).filter(f => f.type === 'number')

  return (
    <div>
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      {fields === null ? (
        <p className="text-xs text-charcoal-400">Loading…</p>
      ) : numberFields.length === 0 ? (
        <p className="text-xs text-charcoal-400">
          No number-type custom fields defined yet — an admin can add one in Settings → Contact Fields.
        </p>
      ) : (
        <select className="input w-full" value={value || ''} onChange={e => onChange(e.target.value)}>
          <option value="">Choose a field…</option>
          {numberFields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
        </select>
      )}
    </div>
  )
}
