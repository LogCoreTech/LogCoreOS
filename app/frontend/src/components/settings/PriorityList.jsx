export function poolMove(pool, setter, from, to) {
  const next = [...pool]
  const [m] = next.splice(from, 1)
  next.splice(to, 0, m)
  setter(next)
}

export function poolRemove(pool, setter, cat) {
  if (pool.length <= 1) return
  setter(pool.filter(c => c !== cat))
}

export function poolAdd(pool, setter, val, clearFn) {
  const v = val.trim()
  if (v && !pool.includes(v)) { setter([...pool, v]); clearFn('') }
}

export default function PriorityList({ label, pool, setter, newVal, setNewVal, dragState, onDragStart, onDragOver, onDragEnd }) {
  return (
    <div>
      <p className="text-sm font-medium mb-2">{label}</p>
      <ul className="space-y-1.5 mb-2">
        {pool.map((cat, i) => (
          <li
            key={cat}
            draggable
            onDragStart={() => onDragStart(label, i)}
            onDragOver={e => onDragOver(e, pool, i, setter)}
            onDragEnd={onDragEnd}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-colors ${
              dragState?.pool === label && dragState?.idx === i
                ? 'border-orange-500 bg-orange-500/10'
                : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
            }`}
          >
            <span className="text-charcoal-400 text-xs w-4 shrink-0">{i + 1}</span>
            <span className="flex-1">{cat}</span>
            <div className="flex flex-col shrink-0 mr-2">
              <button type="button" onClick={() => poolMove(pool, setter, i, i - 1)} disabled={i === 0}
                className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 leading-none px-1 text-xs">▲</button>
              <button type="button" onClick={() => poolMove(pool, setter, i, i + 1)} disabled={i === pool.length - 1}
                className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 leading-none px-1 text-xs">▼</button>
            </div>
            <button type="button" onClick={() => poolRemove(pool, setter, cat)} disabled={pool.length <= 1}
              className="text-charcoal-400 hover:text-red-500 disabled:opacity-20 text-xs shrink-0">✕</button>
            <span className="text-charcoal-300 dark:text-charcoal-600 cursor-grab hidden md:block">⠿</span>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input type="text" value={newVal} onChange={e => setNewVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && poolAdd(pool, setter, newVal, setNewVal)}
          // `.input` alone is already 16px; the `text-sm` override here
          // dropped it under the iOS Safari auto-zoom-on-focus threshold
          // (same bug class as TagInput.jsx, fixed 2026-08-18) — dropped
          // rather than shrunk, the button next to it is the same size regardless.
          placeholder="Add category…" className="input" />
        <button onClick={() => poolAdd(pool, setter, newVal, setNewVal)} className="btn-primary px-3 text-sm">+</button>
      </div>
    </div>
  )
}
