import { useEffect, useState } from 'react'
import { assets as assetsApi } from '../../lib/api'

/**
 * Two-stage picker for a status_button's "set an asset field" action: pick
 * one of the asset's own select-type template fields, then one of that
 * field's own predefined options — both picked, never typed, since select
 * fields already carry their own enumerable options server-side.
 *
 * Props: assetId (from the sibling asset_id config field), value
 * ({field_key, value}|undefined), onChange({field_key, value}), label
 */
export default function AssetSelectFieldPicker({ assetId, value, onChange, label }) {
  const [asset, setAsset] = useState(null)
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    if (!assetId) { setAsset(null); return }
    assetsApi.get(assetId).then(setAsset).catch(() => setAvailable(false))
  }, [assetId])

  if (!assetId) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <p className="text-xs text-charcoal-400">Pick an asset above first.</p>
      </div>
    )
  }
  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <p className="text-xs text-charcoal-400">Could not load this asset&apos;s fields.</p>
      </div>
    )
  }

  const selectFields = (asset?._template?.fields || []).filter(f => f.type === 'select')
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
      {asset && selectFields.length === 0 && (
        <p className="text-xs text-charcoal-400">This asset&apos;s template has no select-type fields.</p>
      )}
    </div>
  )
}
