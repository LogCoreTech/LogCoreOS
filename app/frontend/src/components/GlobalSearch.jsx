import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { search as searchApi, tags as tagsApi } from '../lib/api'
import { ALL_MODULES } from '../lib/constants'
import { deepLinkUrl } from '../lib/deepLinks'
import TagInput from './TagInput'

// Global, app-wide search — a magnifying-glass icon in the header (Layout.jsx)
// opens this modal. Modeled directly on DashboardSwitcher.jsx's own
// .modal-overlay/.modal-card shape (mobile-safe bottom-sheet, dark-mode
// themed), but server-filtered via a live fan-out (services/search_service.py)
// instead of an in-memory list — search_service.search() already returns []
// for an empty query with no tags, so there's nothing to debounce/fetch until
// the caller has actually typed or picked a tag.
export default function GlobalSearch({ onClose }) {
  const [query, setQuery] = useState('')
  const [selectedTags, setSelectedTags] = useState([])
  const [tagSuggestions, setTagSuggestions] = useState([])
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const debounceRef = useRef(null)

  useEffect(() => {
    Promise.all([tagsApi.list(false).catch(() => ({ tags: [] })), tagsApi.list(true).catch(() => ({ tags: [] }))])
      .then(([personal, pool]) => {
        const seen = new Map()
        for (const t of [...(personal.tags || []), ...(pool.tags || [])]) {
          const key = t.toLowerCase()
          if (!seen.has(key)) seen.set(key, t)
        }
        setTagSuggestions([...seen.values()])
      })
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!query.trim() && selectedTags.length === 0) {
      setResults([])
      return
    }
    setLoading(true)
    debounceRef.current = setTimeout(() => {
      searchApi.query(query.trim(), selectedTags)
        .then(r => setResults(r.results || []))
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 250)
    return () => clearTimeout(debounceRef.current)
  }, [query, selectedTags])

  const grouped = useMemo(() => {
    const byModule = new Map()
    for (const r of results) {
      if (!byModule.has(r._module)) byModule.set(r._module, [])
      byModule.get(r._module).push(r)
    }
    return [...byModule.entries()].map(([moduleId, items]) => ({
      moduleId,
      module: ALL_MODULES.find(m => m.id === moduleId),
      items,
    }))
  }, [results])

  function openResult(moduleId, recordId) {
    onClose()
    navigate(deepLinkUrl(moduleId, recordId))
  }

  const hasQuery = query.trim() || selectedTags.length > 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Search</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>
        <input
          className="input w-full mb-2"
          placeholder="Search tasks, notes, goals, contacts…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          autoFocus
        />
        <div className="mb-3">
          <TagInput
            value={selectedTags}
            onChange={setSelectedTags}
            suggestions={tagSuggestions}
            strict
            placeholder="Filter by tag…"
          />
        </div>
        <div className="space-y-3 max-h-[50vh] overflow-y-auto">
          {!hasQuery && (
            <p className="text-sm text-charcoal-400 py-2">Type to search, or filter by a tag above.</p>
          )}
          {hasQuery && !loading && results.length === 0 && (
            <p className="text-sm text-charcoal-400 py-2">No results found.</p>
          )}
          {grouped.map(g => (
            <div key={g.moduleId}>
              <p className="flex items-center gap-1.5 px-1 py-1 text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
                <span className="normal-case">{g.module?.icon}</span>
                <span>{g.module?.label || g.moduleId}</span>
              </p>
              <div className="space-y-1">
                {g.items.map(r => (
                  <button
                    key={r.record_id}
                    onClick={() => openResult(g.moduleId, r.record_id)}
                    className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-800"
                  >
                    <span className="text-sm block truncate">{r.title}</span>
                    {r.snippet && (
                      <span className="text-xs text-charcoal-400 block truncate">{r.snippet}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
