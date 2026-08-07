// Two-stage picker for a status_button's "update contact data" action: pick
// one of a small, fixed set of genuinely enumerable Contact fields, then one
// of that field's own predefined values — both picked, never typed. Unlike
// AssetSelectFieldPicker, Contacts have no admin-configurable per-instance
// template to read options from, so this list is hardcoded to the fields
// contacts_service.py actually validates as a real enum (see
// docs/MEMORY.md) rather than the many free-text/UI-convention-only fields
// (e.g. income_range, communication_style) that are also private and would
// silently no-op when the clicking viewer isn't the contact's own owner.
const FIELDS = [
  { key: 'gender', label: 'Gender', options: [{ value: 'male', label: 'Male' }, { value: 'female', label: 'Female' }] },
  {
    key: 'marital_status',
    label: 'Marital Status',
    options: ['Single', 'Married', 'Divorced', 'Widowed', 'Partnered'].map(v => ({ value: v, label: v })),
  },
]

/**
 * Props: value ({field_key, value}|undefined), onChange({field_key, value}), label
 */
export default function ContactFieldPicker({ value, onChange, label }) {
  const fieldKey = value?.field_key || ''
  const currentField = FIELDS.find(f => f.key === fieldKey)

  return (
    <div className="space-y-2">
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select
        className="input w-full"
        value={fieldKey}
        onChange={e => onChange({ field_key: e.target.value, value: '' })}
      >
        <option value="">Choose a field…</option>
        {FIELDS.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
      </select>
      {currentField && (
        <select
          className="input w-full"
          value={value?.value || ''}
          onChange={e => onChange({ field_key: fieldKey, value: e.target.value })}
        >
          <option value="">Choose a value…</option>
          {currentField.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
    </div>
  )
}
