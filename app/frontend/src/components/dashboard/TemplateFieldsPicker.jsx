import { useEffect, useState } from 'react'
import { assets as assetsApi } from '../../module_packages/assets/frontend/api'

/**
 * Multi-select of a chosen asset template's own field keys — the Collection
 * block's "which columns show" config. Checkboxes, not typed keys, since the
 * template already enumerates exactly what's pickable.
 *
 * Props: templateId (from the sibling template_id config field), value
 * (string[]|undefined), onChange(string[]), label
 */
export default function TemplateFieldsPicker({ templateId, value, onChange, label }) {
  const [template, setTemplate] = useState(null)
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    if (!templateId) { setTemplate(null); return }
    assetsApi.listTemplates()
      .then(list => setTemplate((Array.isArray(list) ? list : []).find(t => t.id === templateId) || null))
      .catch(() => setAvailable(false))
  }, [templateId])

  if (!templateId) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <p className="text-xs text-charcoal-400">Pick a template above first.</p>
      </div>
    )
  }
  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <p className="text-xs text-charcoal-400">Could not load this template&apos;s fields.</p>
      </div>
    )
  }

  const fields = template?.fields || []
  const selected = value || []

  function toggle(key) {
    onChange(selected.includes(key) ? selected.filter(k => k !== key) : [...selected, key])
  }

  return (
    <div>
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      {fields.length === 0 ? (
        <p className="text-xs text-charcoal-400">This template has no fields yet.</p>
      ) : (
        <div className="space-y-1 mt-1">
          {fields.map(f => (
            <label key={f.key} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={selected.includes(f.key)} onChange={() => toggle(f.key)} />
              {f.label || f.key}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
