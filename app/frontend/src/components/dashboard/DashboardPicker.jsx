import { useEffect, useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'

/**
 * Dashboard selector for a nav_button's "specific record" mode — lets a
 * button jump to one particular dashboard instead of just wherever "/"
 * currently resolves to (your default, which can change). A plain <select>
 * over dashboardsApi.list(), the same list the in-app dashboard switcher
 * already uses, so it only ever offers dashboards this user can actually see.
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

  return (
    <div>
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select
        className="input"
        value={value || ''}
        onChange={e => onChange(e.target.value || null)}
      >
        {!value && <option value="">Choose a dashboard…</option>}
        {items.map(d => (
          <option key={d.id} value={d.id}>{d.icon ? `${d.icon} ` : ''}{d.name}</option>
        ))}
      </select>
    </div>
  )
}
