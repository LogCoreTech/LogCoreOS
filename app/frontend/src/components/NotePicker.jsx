import { useEffect, useRef, useState } from 'react'
import { notes as notesApi } from '../module_packages/notes/frontend/api'

/**
 * Search-autocomplete over the user's notes, mirroring ContactPicker's
 * established pattern. Keys off `path` (not an id) since that's what the
 * note_embed block's resolver reads. Filters the list to actual note files —
 * folders aren't embeddable. Default list call already excludes archived.
 *
 * Props: value (path|null), onChange(path|null), label, placeholder
 */
export default function NotePicker({ value, onChange, label, placeholder }) {
  const [available, setAvailable] = useState(true)
  const [all, setAll] = useState([])
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    notesApi.list()
      .then(r => setAll(Array.isArray(r) ? r.filter(n => n.type === 'note') : []))
      .catch(() => setAvailable(false))
  }, [])

  useEffect(() => {
    if (!value) { setText(''); return }
    const match = all.find(n => n.path === value)
    if (match) setText(match.name || match.path)
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
        <input className="input" placeholder={placeholder} disabled value="Notes unavailable" />
      </div>
    )
  }

  const q = text.trim().toLowerCase()
  const matches = (q
    ? all.filter(n => (n.name || n.path || '').toLowerCase().includes(q))
    : all
  ).slice(0, 8)

  function pick(n) {
    onChange(n.path)
    setText(n.name || n.path)
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
          placeholder={placeholder || 'Search your notes…'}
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
          {matches.map(n => (
            <button
              key={n.path}
              type="button"
              onClick={() => pick(n)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800 truncate"
            >
              📝 {n.name || n.path}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
