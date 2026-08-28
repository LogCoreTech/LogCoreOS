import { useEffect, useState } from 'react'
import { dashboards as dashboardsApi } from '../../module_packages/dashboard/frontend/api'

/**
 * Dashboard selector for a nav_button's "specific record" mode — lets a
 * button jump to one particular dashboard instead of just wherever "/"
 * currently resolves to (your default, which can change). A plain <select>
 * over dashboardsApi.list(), the same list the in-app dashboard switcher
 * already uses, so it only ever offers dashboards this user can actually see.
 * Options are grouped by template via native <optgroup> — still "a dropdown
 * for quick and easy selection" (owner's own words), just organized the same
 * way DashboardSwitcher.jsx groups its own list, using the same
 * _template_label every list item already carries.
 *
 * Props: value (dashboardId|null), onChange(dashboardId|null), label
 */
export default function DashboardPicker({ value, onChange, label }) {
  const [available, setAvailable] = useState(true)
  const [items, setItems] = useState([])

  useEffect(() => {
    dashboardsApi.list()
      .then(r => setItems(r?.items || []))
      .catch(() => setAvailable(false))
  }, [])

  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <input className="input" disabled value="Dashboards unavailable" />
      </div>
    )
  }

  const groups = new Map()
  const ungrouped = []
  for (const d of items) {
    if (d._template_label) {
      if (!groups.has(d._template_label)) groups.set(d._template_label, [])
      groups.get(d._template_label).push(d)
    } else {
      ungrouped.push(d)
    }
  }

  function optionFor(d) {
    return <option key={d.id} value={d.id}>{d.icon ? `${d.icon} ` : ''}{d.name}</option>
  }

  return (
    <div>
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select
        className="input"
        value={value || ''}
        onChange={e => onChange(e.target.value || null)}
      >
        {!value && <option value="">Choose a dashboard…</option>}
        {[...groups.entries()].map(([groupLabel, ds]) => (
          <optgroup key={groupLabel} label={groupLabel}>
            {ds.map(optionFor)}
          </optgroup>
        ))}
        {ungrouped.length > 0 && groups.size > 0 ? (
          <optgroup label="Other">{ungrouped.map(optionFor)}</optgroup>
        ) : ungrouped.map(optionFor)}
      </select>
    </div>
  )
}
