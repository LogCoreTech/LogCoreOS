import { useEffect, useState } from 'react'
import { assets as assetsApi } from '../../module_packages/assets/frontend/api'

/**
 * Two-stage picker: pick one of a source's own select-type template fields,
 * then one of that field's own predefined options — both picked, never
 * typed, since select fields already carry their own enumerable options
 * server-side. The source is either one specific asset (status_button's
 * "set an asset field" action — its own template is resolved server-side and
 * embedded as `_template`) or a whole template directly (the Collection
 * block's "status field" config, which has no single asset instance to read
 * from yet). Exactly one of assetId/templateId is passed by any given caller.
 *
 * Props: assetId?, templateId?, value ({field_key, value}|undefined),
 * onChange({field_key, value}), label
 */
export default function AssetSelectFieldPicker({ assetId, templateId, value, onChange, label }) {
  const [fields, setFields] = useState(null)
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    if (assetId) {
      assetsApi.get(assetId).then(a => setFields(a?._template?.fields || [])).catch(() => setAvailable(false))
    } else if (templateId) {
      assetsApi.listTemplates()
        .then(list => setFields((Array.isArray(list) ? list : []).find(t => t.id === templateId)?.fields || []))
        .catch(() => setAvailable(false))
    } else {
      setFields(null)
    }
  }, [assetId, templateId])

  if (!assetId && !templateId) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <p className="text-xs text-charcoal-400">Pick an asset or template above first.</p>
      </div>
    )
  }
  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <p className="text-xs text-charcoal-400">Could not load select-type fields.</p>
      </div>
    )
  }

  const selectFields = (fields || []).filter(f => f.type === 'select')
  const fieldKey = value?.field_key || ''
  const currentField = selectFields.find(f => f.key === fieldKey)

  return (
    <div className="space-y-2">
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select
        className="input w-full"
        value={fieldKey}
        onChange={e => onChange({ field_key: e.target.value, value: '' })}
      >
        <option value="">Choose a field…</option>
        {selectFields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
      </select>
      {currentField && (
        <select
          className="input w-full"
          value={value?.value || ''}
          onChange={e => onChange({ field_key: fieldKey, value: e.target.value })}
        >
          <option value="">Choose a value…</option>
          {(currentField.options || []).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      )}
      {fields && selectFields.length === 0 && (
        <p className="text-xs text-charcoal-400">This template has no select-type fields.</p>
      )}
    </div>
  )
}
