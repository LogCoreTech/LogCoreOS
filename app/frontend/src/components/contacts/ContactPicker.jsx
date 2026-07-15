import { useEffect, useRef, useState } from 'react'
import { contacts as contactsApi } from '../../lib/api'

/**
 * Autocomplete over CRM contacts. Sets both a display name and a contact id.
 * Falls back to a plain free-text input if the Contacts module is unavailable
 * (403) so Finance stays usable standalone.
 *
 * Props: value {name, contactId}, onChange(name, contactId), label, placeholder
 */
export default function ContactPicker({ value, onChange, label, placeholder }) {
  const [available, setAvailable] = useState(true)
  const [all, setAll] = useState([])
  const [text, setText] = useState(value?.name || '')
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    contactsApi.list()
      .then(r => setAll(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  useEffect(() => { setText(value?.name || '') }, [value?.name])

  useEffect(() => {
    if (!open) return
    const close = e => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [open])

  const q = text.trim().toLowerCase()
  const matches = q
    ? all.filter(c => (c.name || '').toLowerCase().includes(q) ||
        (c.emails || []).some(e => e.toLowerCase().includes(q))).slice(0, 6)
    : all.slice(0, 6)
  const exact = all.find(c => (c.name || '').toLowerCase() === q)

  function pick(c) {
    onChange(c.name, c.id)
    setText(c.name)
    setOpen(false)
  }

  async function createNew() {
    const name = text.trim()
    if (!name) return
    setCreating(true)
    try {
      const c = await contactsApi.create({ name, type: 'person' })
      setAll(a => [...a, c])
      pick(c)
    } catch { /* ignore */ } finally { setCreating(false) }
  }

  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <input className="input" placeholder={placeholder} value={text}
          onChange={e => { setText(e.target.value); onChange(e.target.value, null) }} maxLength={120} />
      </div>
    )
  }

  return (
    <div ref={boxRef} className="relative">
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <input
        className="input"
        placeholder={placeholder || 'Search or add a contact…'}
        value={text}
        onChange={e => { setText(e.target.value); onChange(e.target.value, null); setOpen(true) }}
        onFocus={() => setOpen(true)}
        maxLength={120}
      />
      {open && (matches.length > 0 || (q && !exact)) && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-lg shadow-lg overflow-hidden">
          {matches.map(c => (
            <button key={c.id} type="button" onClick={() => pick(c)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800">
              {c.type === 'company' ? '🏢' : '🧑'} {c.name}
              {(c.emails || [])[0] && <span className="text-charcoal-400 text-xs ml-1">{c.emails[0]}</span>}
            </button>
          ))}
          {q && !exact && (
            <button type="button" onClick={createNew} disabled={creating}
              className="w-full text-left px-3 py-2 text-sm text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-900/20 border-t border-charcoal-100 dark:border-charcoal-800">
              {creating ? 'Creating…' : `＋ Create contact “${text.trim()}”`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
