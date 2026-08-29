import { useEffect, useRef, useState } from 'react'
import { goals as goalsApi } from './api'

// Client-side mirror of the backend's collect_subtree_ids — excludes a goal
// and everything under it from the picker, since re-parenting a goal under
// its own descendant is guaranteed to 400 server-side (the cycle guard in
// goals_service.update_goal); no point offering an option that can't work.
function subtreeIds(goals, rootId) {
  const children = {}
  for (const g of goals) {
    const key = g.parent_id || '_root'
    children[key] = children[key] || []
    children[key].push(g.id)
  }
  const out = new Set()
  const stack = [rootId]
  while (stack.length) {
    const id = stack.pop()
    if (out.has(id)) continue
    out.add(id)
    for (const c of children[id] || []) stack.push(c)
  }
  return out
}

/**
 * Search-autocomplete over goals, for "link an existing goal as a subgoal"
 * (re-parenting) — mirrors TaskPicker.jsx's own shape. Excludes excludeId
 * and its own subtree. Shows each match's current parent title (if any) so
 * re-parenting isn't a surprise, per the owner's own scoping request.
 *
 * Props: value (goalId|null), onChange(goalId|null), excludeId, pool, label, placeholder
 */
export default function GoalPicker({ value, onChange, excludeId, pool = false, label, placeholder }) {
  const [available, setAvailable] = useState(true)
  const [all, setAll] = useState([])
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    goalsApi.list()
      .then(r => setAll(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  useEffect(() => {
    if (!value) { setText(''); return }
    const match = all.find(g => g.id === value)
    if (match) setText(match.title)
  }, [value, all])

  useEffect(() => {
    if (!open) return
    const close = e => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [open])

  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <input className="input" placeholder={placeholder} disabled value="Goals unavailable" />
      </div>
    )
  }

  const excluded = excludeId ? subtreeIds(all, excludeId) : new Set()
  const isPoolGoal = g => !!g._owner && g._owner.startsWith('_')
  const candidates = all.filter(g => !excluded.has(g.id) && isPoolGoal(g) === pool)
  const byId = Object.fromEntries(all.map(g => [g.id, g]))

  const q = text.trim().toLowerCase()
  const matches = (q ? candidates.filter(g => (g.title || '').toLowerCase().includes(q)) : candidates).slice(0, 8)

  function pick(g) {
    onChange(g.id)
    setText(g.title)
    setOpen(false)
  }

  function clear() {
    onChange(null)
    setText('')
  }

  return (
    <div ref={boxRef} className="relative">
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <div className="flex gap-1">
        <input
          className="input flex-1"
          placeholder={placeholder || 'Search goals…'}
          value={text}
          onChange={e => { setText(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
        />
        {value && (
          <button type="button" className="btn-ghost px-2 text-xs shrink-0" onClick={clear}>✕</button>
        )}
      </div>
      {open && matches.length > 0 && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-lg shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {matches.map(g => {
            const parent = g.parent_id ? byId[g.parent_id] : null
            return (
              <button
                key={g.id}
                type="button"
                onClick={() => pick(g)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800 truncate"
              >
                {g.title}
                {parent && <span className="text-xs text-charcoal-400"> — currently under &quot;{parent.title}&quot;</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
