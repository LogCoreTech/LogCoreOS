import { useEffect, useState } from 'react'
import { homes as homesApi } from '../module_packages/homes/frontend/api'

/**
 * Home selector for the Home Health dashboard block's config. A plain
 * <select>, same idiom as FinanceBookPicker.jsx — homes are a small,
 * bounded list per user with no hierarchy, unlike AssetPickerField.jsx's
 * tree-toggle shape. homesApi.list() already returns own + pool homes
 * combined, `_owner`-annotated. Falls back to a disabled input if Homes is
 * unavailable, matching the other pickers' graceful-degradation contract.
 *
 * Props: value (homeId|null), onChange(homeId|null), label
 */
export default function HomePickerField({ value, onChange, label }) {
  const [available, setAvailable] = useState(true)
  const [homes, setHomes] = useState([])

  useEffect(() => {
    homesApi.list()
      .then(r => setHomes(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  if (!available) {
    return (
      <div>
        {label && <label className="block text-sm font-medium mb-1">{label}</label>}
        <input className="input" disabled value="Homes unavailable" />
      </div>
    )
  }

  return (
    <div>
      {label && <label className="block text-sm font-medium mb-1">{label}</label>}
      <select
        className="input"
        value={value || ''}
        onChange={e => onChange(e.target.value || null)}
      >
        {!value && <option value="">Select a home…</option>}
        {homes.map(h => (
          <option key={h.id} value={h.id}>
            {h.icon ? `${h.icon} ` : ''}{h.name}{h._owner ? ` (${h._owner})` : ''}
          </option>
        ))}
      </select>
    </div>
  )
}
