import { useEffect, useRef, useState } from 'react'
import { tasks as tasksApi } from '../lib/api'

/**
 * Search-autocomplete over the user's own tasks, mirroring ContactPicker's
 * established pattern. Single-value contract (id in, id out) since dashboard
 * block config only ever stores the id, never a display name.
 *
 * Props: value (taskId|null), onChange(taskId|null), label, placeholder
 */
export default function TaskPicker({ value, onChange, label, placeholder }) {
  const [available, setAvailable] = useState(true)
  const [all, setAll] = useState([])
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    tasksApi.list()
      .then(r => setAll(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  useEffect(() => {
    if (!value) { setText(''); return }
    const match = all.find(t => t.id === value)
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
        <input className="input" placeholder={placeholder} disabled value="Tasks unavailable" />
      </div>
    )
  }

  const q = text.trim().toLowerCase()
  const matches = (q ? all.filter(t => (t.title || '').toLowerCase().includes(q)) : all).slice(0, 8)

  function pick(t) {
    onChange(t.id)
    setText(t.title)
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
          placeholder={placeholder || 'Search your tasks…'}
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
          {matches.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => pick(t)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800 truncate"
            >
              {t.status === 'done' ? '✅' : '⬜'} {t.title}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
