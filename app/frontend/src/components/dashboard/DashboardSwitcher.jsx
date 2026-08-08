import { useMemo, useState } from 'react'

// Groups by the dashboard's own template (the "folder" the owner asked for —
// makes browsing manageable with a large number of per-client/per-asset
// dashboards). _template_label/_template_icon are denormalized onto every
// list item server-side (dashboards_service.list_visible_dashboards), so
// grouping works even for a shared dashboard whose template this viewer
// doesn't own. A live search flattens back to a plain filtered list —
// browsing structure and searching for one item are different tasks, and
// collapsed groups would just hide search matches.
function groupByTemplate(items) {
  const groups = new Map()
  const other = []
  for (const d of items) {
    if (d._template_label) {
      if (!groups.has(d._template_label)) {
        groups.set(d._template_label, { label: d._template_label, icon: d._template_icon, items: [] })
      }
      groups.get(d._template_label).items.push(d)
    } else {
      other.push(d)
    }
  }
  return { templated: [...groups.values()], other }
}

export default function DashboardSwitcher({ items, activeId, onSelect, onCreateNew, onManageTemplates, onClose }) {
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState({})

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(d => d.name.toLowerCase().includes(q))
  }, [items, query])

  const grouped = useMemo(() => (query.trim() ? null : groupByTemplate(items)), [items, query])

  function Row({ d }) {
    return (
      <button
        onClick={() => onSelect(d.id)}
        className={`w-full text-left flex items-center gap-2 p-2 rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-800 ${d.id === activeId ? 'bg-orange-50 dark:bg-orange-900/20' : ''}`}
      >
        <span>{d.icon}</span>
        <span className="text-sm truncate flex-1">{d.name}</span>
        {d._owner && <span className="text-xs text-charcoal-400 shrink-0">{d._owner}</span>}
      </button>
    )
  }

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

          {grouped ? (
            <>
              {grouped.templated.map(g => (
                <div key={g.label}>
                  <button
                    onClick={() => setCollapsed(c => ({ ...c, [g.label]: !c[g.label] }))}
                    className="w-full flex items-center gap-1.5 px-1 py-1 text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400"
                  >
                    <span className="w-3 shrink-0">{collapsed[g.label] ? '▸' : '▾'}</span>
                    <span className="normal-case">{g.icon}</span>
                    <span className="truncate">{g.label}</span>
                    <span className="font-normal normal-case text-charcoal-400">({g.items.length})</span>
                  </button>
                  {!collapsed[g.label] && g.items.map(d => <Row key={d.id} d={d} />)}
                </div>
              ))}
              {grouped.other.length > 0 && (
                <div>
                  {grouped.templated.length > 0 && (
                    <p className="px-1 py-1 text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">Other</p>
                  )}
                  {grouped.other.map(d => <Row key={d.id} d={d} />)}
                </div>
              )}
            </>
          ) : (
            filtered.map(d => <Row key={d.id} d={d} />)
          )}
        </div>
        <div className="flex gap-2">
          <button className="btn-primary flex-1" onClick={onCreateNew}>+ New Dashboard</button>
          <button className="btn-ghost text-sm" onClick={onManageTemplates}>Templates</button>
        </div>
      </div>
    </div>
  )
}
