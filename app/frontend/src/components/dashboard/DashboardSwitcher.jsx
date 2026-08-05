import { useMemo, useState } from 'react'

export default function DashboardSwitcher({ items, activeId, onSelect, onCreate, onClose }) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(d => d.name.toLowerCase().includes(q))
  }, [items, query])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Your dashboards</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>
        <input
          className="input w-full mb-3"
          placeholder="Search dashboards…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          autoFocus
        />
        <div className="space-y-1 max-h-[50vh] overflow-y-auto mb-3">
          {filtered.length === 0 && <p className="text-sm text-charcoal-400 py-2">No dashboards found.</p>}
          {filtered.map(d => (
            <button
              key={d.id}
              onClick={() => onSelect(d.id)}
              className={`w-full text-left flex items-center gap-2 p-2 rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-800 ${d.id === activeId ? 'bg-orange-50 dark:bg-orange-900/20' : ''}`}
            >
              <span>{d.icon}</span>
              <span className="text-sm truncate flex-1">{d.name}</span>
              {d._owner && <span className="text-xs text-charcoal-400 shrink-0">{d._owner}</span>}
            </button>
          ))}
        </div>
        <button className="btn-primary w-full" onClick={onCreate}>+ New Dashboard</button>
      </div>
    </div>
  )
}
