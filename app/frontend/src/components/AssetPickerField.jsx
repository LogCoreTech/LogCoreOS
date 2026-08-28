import { useEffect, useState } from 'react'
import { assets as assetsApi } from '../module_packages/assets/frontend/api'
import AssetTreePicker from './AssetTreePicker'

/**
 * Single-asset reference field for dashboard block config — same compact
 * "current selection + Change ▾ toggles an inline tree panel" idiom
 * AssetModal.jsx already uses for its own parent picker, just wired to a
 * plain value/onChange contract instead of a form-state setter. Falls back
 * to a plain text input if the Assets module is unavailable (403), matching
 * ContactPicker's graceful-degradation contract.
 *
 * Props: value (assetId|null), onChange(assetId|null), label, placeholder
 */
export default function AssetPickerField({ value, onChange, label, placeholder }) {
  const [available, setAvailable] = useState(true)
  const [all, setAll] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    assetsApi.list()
      .then(r => setAll(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  const selected = value ? all.find(a => a.id === value) : null

  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <input className="input" placeholder={placeholder} disabled value="Assets unavailable" />
      </div>
    )
  }

  return (
    <div>
      {label && <label className="block text-xs text-charcoal-500 dark:text-charcoal-400 mb-1">{label}</label>}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="input text-left flex items-center justify-between"
      >
        <span className="truncate">
          {selected ? `${selected._template?.icon || '▫️'} ${selected.name}` : (placeholder || 'Select an asset…')}
        </span>
        <span className="text-xs text-charcoal-400 shrink-0 ml-2">{open ? '▲' : 'Change ▾'}</span>
      </button>
      {open && (
        <div className="mt-1 border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-1 max-h-48 overflow-y-auto">
          <AssetTreePicker
            candidates={all}
            disabledId={value || null}
            topLabel="— None —"
            onPick={id => { onChange(id || null); setOpen(false) }}
          />
        </div>
      )}
    </div>
  )
}
