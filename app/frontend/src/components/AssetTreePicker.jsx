import { useState, useMemo } from 'react'

// Foldered asset picker (expand/collapse), reused by Move and by the create-asset
// parent chooser. Renders the real tree over `candidates`; a node whose parent
// isn't in the candidate set floats to top level. Calls onPick(assetId | null).
function PickRow({ node, depth, childrenMap, expanded, onToggle, onPick, templatesByKey, disabledId }) {
  const kids = childrenMap[node.id] || []
  const isOpen = expanded.has(node.id)
  const pad = ['pl-0', 'pl-4', 'pl-8', 'pl-12', 'pl-16', 'pl-20'][Math.min(depth, 5)]
  return (
    <>
      <div className={`flex items-center gap-1 ${pad}`}>
        <button
          type="button"
          onClick={() => kids.length && onToggle(node.id)}
          className={`w-4 text-xs text-charcoal-400 shrink-0 ${kids.length ? 'hover:text-orange-500' : 'opacity-0'}`}
        >
          {isOpen ? '▾' : '▸'}
        </button>
        <button
          type="button"
          disabled={node.id === disabledId}
          onClick={() => onPick(node.id)}
          className="flex-1 min-w-0 text-left text-sm px-2 py-1.5 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 disabled:opacity-40 truncate"
        >
          {templatesByKey[node.template]?.icon || '▫️'} {node.name}
          {node.id === disabledId && <span className="text-xs text-charcoal-400"> (current)</span>}
        </button>
      </div>
      {isOpen && kids.map(k => (
        <PickRow
          key={k.id}
          node={k}
          depth={depth + 1}
          childrenMap={childrenMap}
          expanded={expanded}
          onToggle={onToggle}
          onPick={onPick}
          templatesByKey={templatesByKey}
          disabledId={disabledId}
        />
      ))}
    </>
  )
}

export default function AssetTreePicker({ candidates, templatesByKey, onPick, disabledId = null, topLabel = '⬆ Top level', topDisabled = false }) {
  const [expanded, setExpanded] = useState(new Set())
  const list = Array.isArray(candidates) ? candidates : []

  const childrenMap = useMemo(() => {
    const map = {}
    const ids = new Set(list.map(a => a.id))
    for (const a of list) {
      const parent = a.parent_id && ids.has(a.parent_id) ? a.parent_id : '_root'
      ;(map[parent] = map[parent] || []).push(a)
    }
    for (const key of Object.keys(map)) map[key].sort((x, y) => (x.name || '').localeCompare(y.name || ''))
    return map
  }, [list])

  function toggle(id) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const roots = childrenMap['_root'] || []

  return (
    <div className="space-y-0.5">
      <button
        type="button"
        onClick={() => onPick(null)}
        disabled={topDisabled}
        className="block w-full text-left text-sm px-3 py-1.5 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 disabled:opacity-40"
      >
        {topLabel}
      </button>
      {roots.map(a => (
        <PickRow
          key={a.id}
          node={a}
          depth={0}
          childrenMap={childrenMap}
          expanded={expanded}
          onToggle={toggle}
          onPick={onPick}
          templatesByKey={templatesByKey}
          disabledId={disabledId}
        />
      ))}
      {roots.length === 0 && (
        <p className="text-xs text-charcoal-400 px-3 py-2">No other assets to nest under.</p>
      )}
    </div>
  )
}
