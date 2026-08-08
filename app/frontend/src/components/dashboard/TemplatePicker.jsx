import { useEffect, useState } from 'react'
import { assets as assetsApi } from '../../lib/api'

/**
 * Asset-template picker for the Collection block's "show records from" field
 * — a plain <select> over the templates this viewer can build assets from,
 * same shape as every other dashboard picker in this directory. Deliberately
 * not the AssetTreePicker/AssetPickerField used elsewhere — this picks a
 * TEMPLATE (a kind of record), not one specific asset instance.
 *
 * Props: value (templateId|null), onChange(templateId|null), label
 */
export default function TemplatePicker({ value, onChange, label }) {
  const [available, setAvailable] = useState(true)
  const [templates, setTemplates] = useState([])

  useEffect(() => {
    assetsApi.listTemplates()
      .then(r => setTemplates(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <input className="input" disabled value="Templates unavailable" />
      </div>
    )
  }

  return (
    <div>
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select className="input w-full" value={value || ''} onChange={e => onChange(e.target.value || null)}>
        {!value && <option value="">Choose a template…</option>}
        {templates.map(t => (
          <option key={t.id} value={t.id}>{t.icon ? `${t.icon} ` : ''}{t.label}</option>
        ))}
      </select>
      {templates.length === 0 && (
        <p className="text-[10px] text-charcoal-400 mt-1">No asset templates yet — create one in Assets first.</p>
      )}
    </div>
  )
}
