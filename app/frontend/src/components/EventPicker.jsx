import { useEffect, useRef, useState } from 'react'
import { calendar as calendarApi } from '../module_packages/calendar/frontend/api'

/**
 * Search-autocomplete over the user's calendar events, mirroring
 * ContactPicker's established pattern. Single-value contract (id in, id out).
 *
 * Props: value (eventId|null), onChange(eventId|null), label, placeholder
 */
export default function EventPicker({ value, onChange, label, placeholder }) {
  const [available, setAvailable] = useState(true)
  const [all, setAll] = useState([])
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    calendarApi.events()
      .then(r => setAll(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  useEffect(() => {
    if (!value) { setText(''); return }
    const match = all.find(e => e.id === value)
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
        <input className="input" placeholder={placeholder} disabled value="Calendar unavailable" />
      </div>
    )
  }

  const q = text.trim().toLowerCase()
  const matches = (q ? all.filter(e => (e.title || '').toLowerCase().includes(q)) : all).slice(0, 8)

  function pick(e) {
    onChange(e.id)
    setText(e.title)
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
          placeholder={placeholder || 'Search calendar events…'}
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
          {matches.map(e => (
            <button
              key={e.id}
              type="button"
              onClick={() => pick(e)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800 truncate flex items-center justify-between gap-2"
            >
              <span className="truncate">📌 {e.title}</span>
              {e.date && <span className="text-charcoal-400 text-xs shrink-0">{e.date}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
