import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { search as searchApi, tags as tagsApi } from '../lib/api'
import { ALL_MODULES, QUICK_CREATE_ACTIONS } from '../lib/constants'
import { deepLinkUrl, quickCreateUrl } from '../lib/deepLinks'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import { useToast } from '../lib/toast'
import TagInput from './TagInput'
import useEscapeToClose from '../lib/useEscapeToClose'
import useFocusTrap from '../lib/useFocusTrap'

// Global, app-wide search — a magnifying-glass icon in the header (Layout.jsx)
// opens this modal. Modeled directly on DashboardSwitcher.jsx's own
// .modal-overlay/.modal-card shape (mobile-safe bottom-sheet, dark-mode
// themed), but server-filtered via a live fan-out (services/search_service.py)
// instead of an in-memory list — search_service.search() already returns []
// for an empty query with no tags, so there's nothing to debounce/fetch until
// the caller has actually typed or picked a tag.
//
// 2026-09-04 UX Polish Batch item #10 (fast-follow): cross-workspace search
// (only offered when the user actually has more than one workspace) and a
// per-provider "show more" link once a group's real total (provider_totals)
// exceeds what's shown. Clicking a cross-workspace result auto-switches the
// active workspace (with a toast confirming it) before navigating — the
// destination page's own existing access check is the real permission
// check, same as any other navigation in this app; this never adds a
// second, separate one.
export default function GlobalSearch({ onClose }) {
  const [query, setQuery] = useState('')
  const [selectedTags, setSelectedTags] = useState([])
  const [tagSuggestions, setTagSuggestions] = useState([])
  const [results, setResults] = useState([])
  const [providerTotals, setProviderTotals] = useState({})
  const [loading, setLoading] = useState(false)
  const [crossWorkspace, setCrossWorkspace] = useState(false)
  const [showMoreLoading, setShowMoreLoading] = useState(null) // provider key currently fetching
  const navigate = useNavigate()
  const debounceRef = useRef(null)
  const { user } = useAuth()
  const { workspace, switchWorkspace } = useWorkspace()
  const toast = useToast()
  const hasMultipleWorkspaces = (user?.workspaces || []).length > 1
  const cardRef = useRef(null)

  useEscapeToClose(onClose)
  useFocusTrap(cardRef)

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
      setProviderTotals({})
      return
    }
    setLoading(true)
    debounceRef.current = setTimeout(() => {
      searchApi.query(query.trim(), selectedTags, { crossWorkspace })
        .then(r => {
          setResults(r.results || [])
          setProviderTotals(r.provider_totals || {})
        })
        .catch(() => {
          setResults([])
          setProviderTotals({})
        })
        .finally(() => setLoading(false))
    }, 250)
    return () => clearTimeout(debounceRef.current)
  }, [query, selectedTags, crossWorkspace])

  const grouped = useMemo(() => {
    const byModule = new Map()
    for (const r of results) {
      if (!byModule.has(r._module)) byModule.set(r._module, [])
      byModule.get(r._module).push(r)
    }
    return [...byModule.entries()].map(([moduleId, items]) => {
      // A module can own more than one search provider (e.g. Household owns
      // tasks/goals/events separately) — track each provider's own real
      // total vs. how many of its own results are actually shown here, so
      // "show more" only fires for a provider that's genuinely truncated.
      const shownByProvider = new Map()
      for (const item of items) {
        shownByProvider.set(item._provider, (shownByProvider.get(item._provider) || 0) + 1)
      }
      const moreByProvider = [...shownByProvider.entries()]
        .map(([providerKey, shown]) => ({ providerKey, remaining: (providerTotals[providerKey] || 0) - shown }))
        .filter(p => p.remaining > 0)
      return {
        moduleId,
        module: ALL_MODULES.find(m => m.id === moduleId),
        items,
        moreByProvider,
      }
    })
  }, [results, providerTotals])

  function showMore(providerKey) {
    setShowMoreLoading(providerKey)
    searchApi.query(query.trim(), selectedTags, { crossWorkspace, provider: providerKey })
      .then(r => {
        const rest = (r.results || [])
        setResults(prev => [...prev.filter(item => item._provider !== providerKey), ...rest])
      })
      .finally(() => setShowMoreLoading(null))
  }

  // Item #3, 2026-09-04 UX Polish Batch — "create" mode surfaces as this
  // modal's own empty state (typing anything replaces it with real results)
  // rather than a second overlay. Filtered live to the user's own selected
  // actions AND their currently-enabled modules, never a static list.
  const quickActions = user?.commandPaletteEnabled !== false
    ? QUICK_CREATE_ACTIONS.filter(a =>
        (user?.commandPaletteActions || []).includes(a.module) &&
        !(user?.disabledModules || []).includes(a.module)
      )
    : []

  function openQuickCreate(moduleId) {
    onClose()
    navigate(quickCreateUrl(moduleId))
  }

  function openResult(r) {
    onClose()
    if (r._workspace !== workspace) {
      switchWorkspace(r._workspace)
      toast.success(`Switched to ${r._workspace === 'business' ? 'Business' : 'Personal'} workspace`)
    }
    navigate(deepLinkUrl(r._module, r.record_id))
  }

  const hasQuery = query.trim() || selectedTags.length > 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div ref={cardRef} className="modal-card max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Search</h2>
          <button onClick={onClose} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-600">✕</button>
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
        {hasMultipleWorkspaces && (
          <label className="flex items-center gap-1.5 text-xs text-charcoal-500 dark:text-charcoal-400 mb-3 cursor-pointer">
            <input
              type="checkbox"
              className="accent-orange-500"
              checked={crossWorkspace}
              onChange={e => setCrossWorkspace(e.target.checked)}
            />
            Also search my other workspace
          </label>
        )}
        <div className="space-y-3 max-h-[50vh] overflow-y-auto">
          {!hasQuery && (
            <>
              <p className="text-sm text-charcoal-400 py-2">Type to search, or filter by a tag above.</p>
              {quickActions.length > 0 && (
                <div className="pb-2">
                  <p className="px-1 py-1 text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
                    Create new
                  </p>
                  <div className="flex flex-wrap gap-2 px-1">
                    {quickActions.map(action => (
                      <button
                        key={action.module}
                        type="button"
                        onClick={() => openQuickCreate(action.module)}
                        className="px-3 py-1.5 rounded-lg border border-charcoal-200 dark:border-charcoal-700 text-xs hover:border-orange-500 hover:text-orange-500 transition-colors"
                      >
                        + {action.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
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
                    key={`${r._workspace}-${r.record_id}`}
                    onClick={() => openResult(r)}
                    className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-800"
                  >
                    <span className="text-sm flex items-center gap-1.5 truncate">
                      {r.title}
                      {crossWorkspace && r._workspace !== workspace && (
                        <span className="shrink-0 text-[10px] px-1 py-0.5 rounded bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-500 dark:text-charcoal-400 normal-case">
                          {r._workspace === 'business' ? 'Business' : 'Personal'}
                        </span>
                      )}
                    </span>
                    {r.snippet && (
                      <span className="text-xs text-charcoal-400 block truncate">{r.snippet}</span>
                    )}
                  </button>
                ))}
                {g.moreByProvider.map(({ providerKey, remaining }) => (
                  <button
                    key={providerKey}
                    onClick={() => showMore(providerKey)}
                    disabled={showMoreLoading === providerKey}
                    className="w-full text-left px-2 py-1 text-xs text-orange-500 hover:text-orange-600 disabled:opacity-50"
                  >
                    {showMoreLoading === providerKey ? 'Loading…' : `Show ${remaining} more…`}
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
