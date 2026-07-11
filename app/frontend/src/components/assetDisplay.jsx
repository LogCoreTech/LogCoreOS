import { useState, useEffect } from 'react'
import { assets as assetsApi } from '../lib/api'

// Shared asset display helpers used by both the read-only AssetView and the
// AssetModal editor. Kept in their own module so neither component imports the
// other (would be a circular import).

// Render a history entry's changes tolerantly — a change value is normally an
// [old, new] pair, but never trust the shape (legacy/hand-edited data would
// otherwise throw "not iterable" and crash the whole modal via ErrorBoundary).
export function formatChanges(changes) {
  return Object.entries(changes || {})
    .map(([k, v]) => {
      const key = k.replace('fields.', '')
      if (Array.isArray(v)) {
        const [o, n] = v
        return `${key}: ${o ?? '∅'}→${n ?? '∅'}`
      }
      return `${key}: ${v == null ? '∅' : typeof v === 'object' ? JSON.stringify(v) : v}`
    })
    .join(', ')
}

// Human-readable value for one template field in view mode. Returns null when
// the field is empty so the caller can show a muted placeholder. Booleans are
// resolved before the empty check so `false` reads as "No" (not blank).
export function fieldDisplay(def, value) {
  if (def?.type === 'boolean') return value === true ? 'Yes' : 'No'
  if (value === null || value === undefined || value === '') return null
  return String(value)
}

export function AttachmentThumb({ assetId, file, canEdit, onDelete }) {
  const [url, setUrl] = useState(null)
  const isImage = file.mime.startsWith('image/')

  useEffect(() => {
    let objectUrl = null
    if (isImage) {
      assetsApi.fileBlob(assetId, file.id)
        .then(blob => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) })
        .catch(() => {})
    }
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [assetId, file.id])

  async function open() {
    try {
      const blob = await assetsApi.fileBlob(assetId, file.id)
      const u = URL.createObjectURL(blob)
      window.open(u, '_blank')
      setTimeout(() => URL.revokeObjectURL(u), 60000)
    } catch { /* ignore */ }
  }

  return (
    <div className="relative group border border-charcoal-200 dark:border-charcoal-700 rounded-lg overflow-hidden">
      <button type="button" onClick={open} className="block w-full" title={file.filename}>
        {isImage && url ? (
          <img src={url} alt={file.filename} className="w-full h-20 object-cover" />
        ) : (
          <div className="w-full h-20 flex flex-col items-center justify-center text-charcoal-500 dark:text-charcoal-400">
            <span className="text-xl">📄</span>
            <span className="text-[10px] px-1 truncate max-w-full">{file.filename}</span>
          </div>
        )}
      </button>
      {canEdit && (
        <button
          type="button"
          onClick={() => onDelete(file)}
          className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
          title="Delete file"
        >
          ✕
        </button>
      )}
    </div>
  )
}
