import { useState } from 'react'
import { admin as adminApi } from '../../../../lib/api'

const OTHER = '__other__'

// Reusable model field: a <select> built from staticModels (always ending in
// "Other" — a curated list is a convenience, never a hard ceiling), plus an
// optional "Load Models" live-fetch action. The fetch button only renders when
// allowFetch is true — a structural prop, not a disabled state, so there's no
// path to it at all when the instance-level toggle is off.
export default function ModelPicker({ providerId, staticModels, allowFetch, formSnapshot, value, onChange }) {
  const [fetched, setFetched]   = useState(null) // null = not fetched this session
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  const [warning, setWarning]   = useState(null)

  const list = fetched || staticModels
  const knownIds = new Set(list.map(m => m.id))
  const isOther = value !== '' && !knownIds.has(value)

  async function loadModels() {
    setLoading(true)
    setError(null)
    setWarning(null)
    try {
      const res = await adminApi.loadAiModels({
        ai_provider: providerId,
        ai_api_key: formSnapshot.ai_api_key,
        ai_base_url: formSnapshot.ai_base_url,
      })
      setFetched(res.models || [])
      setWarning(res.warning || null)
      // Keep the current value even if it's not in the fetched list —
      // never destructively clobber something already filled in.
    } catch (err) {
      setError(err.message || 'Could not load models.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <label className="block text-sm font-medium mb-1">Model</label>
      <div className="flex gap-2">
        <select
          value={isOther ? OTHER : value || ''}
          onChange={e => onChange(e.target.value === OTHER ? '' : e.target.value)}
          className="input flex-1"
        >
          <option value="" disabled>Select a model…</option>
          {list.map(m => (
            <option key={m.id} value={m.id}>{m.label || m.display_name || m.id}</option>
          ))}
          <option value={OTHER}>Other (type manually)</option>
        </select>
        {allowFetch && (
          <button
            type="button"
            onClick={loadModels}
            disabled={loading}
            className="btn-ghost text-xs shrink-0 disabled:opacity-50"
          >
            {loading ? 'Loading…' : 'Load Models'}
          </button>
        )}
      </div>

      {isOther && (
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="Type the exact model id/name"
          className="input mt-2"
        />
      )}

      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      {warning && <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-1">{warning}</p>}

      {fetched && !error && (
        <ul className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-2 space-y-0.5">
          {fetched.map(m => {
            const specs = []
            if (m.max_input_tokens) specs.push(`${m.max_input_tokens.toLocaleString()} tok context`)
            if (m.max_output_tokens) specs.push(`${m.max_output_tokens.toLocaleString()} tok output`)
            return specs.length > 0 ? (
              <li key={m.id}><span className="font-mono">{m.id}</span> — {specs.join(', ')}</li>
            ) : null
          })}
        </ul>
      )}
    </div>
  )
}
