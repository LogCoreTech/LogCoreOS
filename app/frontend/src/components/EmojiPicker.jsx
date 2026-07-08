import { useState, useRef, useEffect } from 'react'

// Curated, self-contained emoji set (no external picker/CDN). Covers the common
// "what kind of thing is this" icons people reach for on desktop, where typing
// an emoji is awkward. Manual type/paste still works via the text field.
const EMOJIS = [
  '📦', '🗂️', '📁', '📄', '📐', '🏠', '🏡', '🏢', '🏬', '🏭', '🏗️', '🧱', '🚪', '🗝️',
  '🌾', '🌳', '🌲', '🏞️', '⛰️', '🏔️', '🗺️', '📍', '🧭', '🚜', '🛻', '🚗', '🚙', '🚕',
  '🚐', '🚚', '🚛', '🏍️', '🚲', '⛵', '🚤', '✈️', '🚁', '🛥️', '🔧', '🔨', '🛠️', '⚙️',
  '🧰', '🪛', '🔩', '⛏️', '🪚', '🧲', '🔌', '🔋', '💡', '🖥️', '💻', '⌨️', '🖨️', '📱',
  '📷', '🎥', '📹', '🎛️', '🎚️', '📡', '💰', '💵', '💳', '🧾', '📊', '📈', '📉', '🏦',
  '🔑', '🔒', '🛡️', '📋', '📝', '📚', '🗃️', '🗄️', '🏷️', '📌', '⭐', '❤️', '🔥', '⚡',
  '🐄', '🐖', '🐎', '🐕', '🐈', '🌿', '🪴', '🍇', '🍎', '🥕', '🏥', '🏫', '⛪', '🏛️',
]

export default function EmojiPicker({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="input !w-12 text-center text-lg"
          title="Pick an icon"
        >
          {value || '🙂'}
        </button>
        <input
          type="text"
          value={value || ''}
          onChange={e => onChange(e.target.value)}
          placeholder="or type"
          className="input flex-1"
          maxLength={8}
        />
      </div>
      {open && (
        <div className="absolute z-50 left-0 mt-1 w-64 max-h-48 overflow-y-auto p-2 bg-white dark:bg-charcoal-900 border border-charcoal-200 dark:border-charcoal-700 rounded-lg shadow-lg grid grid-cols-8 gap-1">
          <button
            type="button"
            onClick={() => { onChange(''); setOpen(false) }}
            className="col-span-8 text-xs text-charcoal-400 hover:text-red-500 mb-1"
          >
            Clear icon
          </button>
          {EMOJIS.map(e => (
            <button
              key={e}
              type="button"
              onClick={() => { onChange(e); setOpen(false) }}
              className="text-lg rounded hover:bg-charcoal-100 dark:hover:bg-charcoal-800 p-0.5"
            >
              {e}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
