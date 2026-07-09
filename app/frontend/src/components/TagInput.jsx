import { useState, useRef } from 'react'

// GitHub-topics-style chip input. Type + Enter/comma → chip; Backspace on an
// empty field removes the last chip; ✕ removes a chip.
// - Free-text mode: any value becomes a chip (template select options).
// - Selector mode (`suggestions` set): a dropdown offers the remaining options;
//   with `strict`, typed values must match a suggestion (share/hide members).
export default function TagInput({
  value: valueProp = [],
  onChange,
  placeholder = 'Add…',
  suggestions: suggestionsProp = [],
  strict = false,
}) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const inputRef = useRef(null)

  // Never trust the shape — a non-array prop would otherwise crash on .filter
  const value = Array.isArray(valueProp) ? valueProp : []
  const suggestions = Array.isArray(suggestionsProp) ? suggestionsProp : []

  const remaining = suggestions.filter(s => !value.includes(s))
  const matches = text
    ? remaining.filter(s => s.toLowerCase().includes(text.toLowerCase()))
    : remaining

  function add(raw) {
    const v = raw.trim()
    if (!v) return
    if (strict && !suggestions.some(s => s.toLowerCase() === v.toLowerCase())) return
    const canonical = suggestions.find(s => s.toLowerCase() === v.toLowerCase()) || v
    if (!value.includes(canonical)) onChange([...value, canonical])
    setText('')
    setOpen(false)
  }

  function removeAt(i) {
    onChange(value.filter((_, j) => j !== i))
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add(text)
    } else if (e.key === 'Backspace' && !text && value.length) {
      removeAt(value.length - 1)
    }
  }

  return (
    <div className="relative">
      <div
        className="input flex flex-wrap gap-1.5 items-center min-h-[2.25rem] cursor-text"
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag, i) => (
          <span
            key={tag + i}
            className="inline-flex items-center gap-1 bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-xs px-2 py-0.5 rounded-full"
          >
            {tag}
            <button type="button" onClick={() => removeAt(i)} className="hover:text-red-500">✕</button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={text}
          onChange={e => { setText(e.target.value); setOpen(true) }}
          onKeyDown={onKeyDown}
          onFocus={() => setOpen(true)}
          onBlur={() => { setTimeout(() => setOpen(false), 120); if (!strict) add(text) }}
          placeholder={value.length ? '' : placeholder}
          className="flex-1 min-w-[6rem] bg-transparent outline-none text-sm py-0.5"
        />
      </div>
      {/* Inline (not absolute) so it can't be clipped by a scrolling modal —
          a complete, self-scrolling box capped at ~4 rows. */}
      {open && suggestions.length > 0 && matches.length > 0 && (
        <div className="mt-1 max-h-32 overflow-y-auto border border-charcoal-200 dark:border-charcoal-700 rounded-lg">
          {matches.slice(0, 30).map(s => (
            <button
              key={s}
              type="button"
              onMouseDown={e => { e.preventDefault(); add(s) }}
              className="block w-full text-left text-sm px-3 py-1.5 hover:bg-charcoal-50 dark:hover:bg-charcoal-800"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
