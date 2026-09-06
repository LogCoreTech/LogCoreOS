import { useState, useEffect, useMemo, useRef } from 'react'
import HelpButton from '../../../components/HelpButton'
import TrashLink from '../../../components/TrashLink'
import ConfirmDialog from '../../../components/ConfirmDialog'
import SelectCheckbox from '../../../components/SelectCheckbox'
import BulkActionBar from '../../../components/BulkActionBar'
import useBulkSelect from '../../../lib/useBulkSelect'
import { useSearchParams } from 'react-router-dom'
import { assets as assetsApi } from './api'
import { useAuth } from '../../../lib/auth'
import { useWorkspace } from '../../../lib/workspace'
import { useToast } from '../../../lib/toast'
import AssetModal from './AssetModal'
import TemplateManager from './TemplateManager'
import AssetTreePicker from '../../../components/AssetTreePicker'
import useEscapeToClose from '../../../lib/useEscapeToClose'
import useFocusTrap from '../../../lib/useFocusTrap'
import useScrollLock from '../../../lib/useScrollLock'

const OWNER_CHIP = {
  team: '🧑‍🤝‍🧑 Team',
  household: '🏠 Household',
}

// Recursive tree row — module level per the MEMORY.md rule (components defined
// inside components remount on every parent render).
function AssetRow({ asset, depth, childrenMap, expanded, onToggle, onOpen, onAddChild, onMove, templatesByKey, isAdmin, selectActive, isSelected, onToggleSelect }) {
  const children = childrenMap[asset.id] || []
  const isOpen = expanded.has(asset.id)
  const template = asset._template || templatesByKey[asset.template]
  const status = asset.fields?.status
  const canEdit = !asset._owner || asset._access === 'edit'
  // Contribute viewers with the "children" cap may add inside (but not move)
  const canAddChild = canEdit ||
    (asset._access === 'contribute' && (asset._caps?.add || []).includes('children'))
  const pad = ['pl-0', 'pl-5', 'pl-10', 'pl-14', 'pl-20', 'pl-24'][Math.min(depth, 5)]
  // Mirrors delete_asset()'s own gate — own personal assets are always
  // deletable by their owner, pool assets are admin-only — so a checkbox
  // never appears on an item bulk-delete is guaranteed to fail on.
  const selectable = !asset._owner || isAdmin

  return (
    <>
      <div className={`flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors group ${pad}`}>
        {selectable && (
          <SelectCheckbox
            checked={isSelected(asset)}
            onChange={() => onToggleSelect(asset)}
            label={`Select ${asset.name}`}
            className={selectActive ? 'inline-flex' : 'hidden md:inline-flex'}
          />
        )}
        <button
          onClick={() => children.length && onToggle(asset.id)}
          className={`w-6 text-xl leading-none text-charcoal-400 shrink-0 ${children.length ? 'hover:text-orange-500' : 'opacity-0'}`}
        >
          {isOpen ? '▼' : '▶'}
        </button>
        <button onClick={() => onOpen(asset)} className="flex items-center gap-2 flex-1 min-w-0 text-left">
          <span className="shrink-0">{template?.icon || '▫️'}</span>
          <span className={`text-sm font-medium truncate ${asset.archived ? 'line-through text-charcoal-400' : ''}`}>
            {asset.name}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-charcoal-400 shrink-0 hidden sm:inline">
            {template?.label || asset.template}
          </span>
          {status && (
            <span className="badge text-[10px] shrink-0">{status}</span>
          )}
          {asset._owner && (
            <span className="text-[10px] text-blue-500 shrink-0">
              {OWNER_CHIP[asset._owner] || `↪ ${asset._owner}`}
            </span>
          )}
          {asset.archived && <span className="text-[10px] text-charcoal-400 shrink-0">archived</span>}
          {(asset.attachments || []).length > 0 && (
            <span className="text-xs text-charcoal-400 shrink-0">📎{asset.attachments.length}</span>
          )}
        </button>
        {(canEdit || canAddChild) && (
          <div className="flex items-center shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            {canEdit && (
              <button
                onClick={() => onMove(asset)}
                className="btn-ghost text-xs px-1.5 py-0.5"
                title="Move"
              >
                ⇄
              </button>
            )}
            {canAddChild && (
              <button
                onClick={() => onAddChild(asset)}
                className="btn-ghost text-xs px-1.5 py-0.5"
                title="Add inside"
              >
                ＋
              </button>
            )}
          </div>
        )}
      </div>
      {isOpen && children.map(c => (
        <AssetRow
          key={c.id}
          asset={c}
          depth={depth + 1}
          childrenMap={childrenMap}
          expanded={expanded}
          onToggle={onToggle}
          onOpen={onOpen}
          onAddChild={onAddChild}
          onMove={onMove}
          templatesByKey={templatesByKey}
          isAdmin={isAdmin}
          selectActive={selectActive}
          isSelected={isSelected}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </>
  )
}

// Move an asset to a new parent via a tree/list picker (same owner only —
// changing ownership is the admin Convert action, not a move).
function MovePicker({ asset, allAssets, onClose, onMoved }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const cardRef = useRef(null)

  useEscapeToClose(onClose)
  useFocusTrap(cardRef)
  useScrollLock()

  // Same store, minus self and descendants (can't move under your own child)
  const sameStore = (Array.isArray(allAssets) ? allAssets : []).filter(
    a => (a._owner || '') === (asset._owner || '')
  )
  const blocked = new Set([asset.id])
  let grew = true
  while (grew) {
    grew = false
    for (const a of sameStore) {
      if (a.parent_id && blocked.has(a.parent_id) && !blocked.has(a.id)) {
        blocked.add(a.id); grew = true
      }
    }
  }
  const candidates = sameStore.filter(a => !blocked.has(a.id))

  async function moveTo(parentId) {
    if (saving) return
    setSaving(true); setError('')
    try {
      await assetsApi.update(asset.id, { parent_id: parentId })
      onMoved()
    } catch (err) {
      setError(err.message); setSaving(false)
    }
  }

  return (
    <div className="modal-overlay z-[55]" onClick={onClose}>
      <div ref={cardRef} className="modal-card p-4 max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-sm">Move “{asset.name}” to…</h2>
          <button onClick={onClose} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>
        {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
        <AssetTreePicker
          candidates={candidates}
          onPick={moveTo}
          disabledId={asset.parent_id || null}
          topDisabled={!asset.parent_id}
        />
      </div>
    </div>
  )
}

export default function Assets() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const toast = useToast()
  const isAdmin = user?.role === 'admin'
  const bulkSelect = useBulkSelect()
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const [templates, setTemplates] = useState([])
  const [items, setItems] = useState([])
  const [loaded, setLoaded] = useState(false)
  const loadGeneration = useRef(0)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(new Set())
  const [query, setQuery] = useState('')
  const [filterMode, setFilterMode] = useState('all') // all | mine | shared | pool | tmpl:<key>
  const [showArchived, setShowArchived] = useState(false)
  const [modal, setModal] = useState(null) // {asset} | {creating: true, parentId}
  const [moveAsset, setMoveAsset] = useState(null)
  const [showTemplates, setShowTemplates] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()

  // Deep link (?asset=<id>) — comment notifications' "View →" button and web
  // push clicks land here; open that asset's read-first view once loaded.
  useEffect(() => {
    const target = searchParams.get('asset')
    if (!target || !loaded) return
    const found = items.find(a => a.id === target)
    if (found) setModal({ asset: found })
    searchParams.delete('asset')
    setSearchParams(searchParams, { replace: true })
  }, [loaded, items, searchParams, setSearchParams])

  // Item #3, 2026-09-04 UX Polish Batch — command palette "create" mode.
  useEffect(() => {
    if (searchParams.get('create') !== '1') return
    setModal({ creating: true })
    searchParams.delete('create')
    setSearchParams(searchParams, { replace: true })
  }, [searchParams, setSearchParams])

  async function load() {
    // `load()` is called from a lot of independent places (mount, every
    // delete/save/move/archive handler, bulk-delete) with no relationship to
    // each other — two overlapping calls can have their responses arrive out
    // of order over the network. Without this guard, an older call's slower
    // response can land AFTER a newer call's faster one and silently
    // overwrite the correct up-to-date tree with stale data (a real report:
    // a deleted asset reappeared because an older, still-in-flight `load()`
    // resolved later and won the last `setState`). `loadGeneration` makes
    // only the most-recently-STARTED call's response ever actually apply.
    const myGeneration = ++loadGeneration.current
    setError('')
    try {
      const [t, a] = await Promise.all([
        assetsApi.listTemplates(),
        assetsApi.list({ includeArchived: showArchived }),
      ])
      if (loadGeneration.current !== myGeneration) return
      setTemplates(Array.isArray(t) ? t : [])
      setItems(Array.isArray(a) ? a : [])
    } catch (err) {
      if (loadGeneration.current === myGeneration) setError(err.message)
    } finally {
      if (loadGeneration.current === myGeneration) setLoaded(true)
    }
  }

  // Reload on workspace/filter change only; `load` is redefined every render
  // and isn't memoized, so including it would refetch on every render instead.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [workspace, showArchived])

  async function handleBulkDelete() {
    setConfirmBulkDelete(false)
    setBulkDeleting(true)
    try {
      const result = await assetsApi.bulkDelete([...bulkSelect.selected])
      if (result.failed?.length) {
        toast.error(`${result.deleted.length} deleted, ${result.failed.length} couldn't be deleted.`)
      } else {
        toast.success(`${result.deleted.length} asset${result.deleted.length === 1 ? '' : 's'} deleted`)
      }
      bulkSelect.stop()
      load()
    } catch (err) {
      toast.error(err.message || 'Bulk delete failed.')
    } finally {
      setBulkDeleting(false)
    }
  }

  const templatesByKey = useMemo(
    () => Object.fromEntries(templates.map(t => [t.key, t])),
    [templates]
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items.filter(a => {
      if (filterMode === 'mine' && a._owner) return false
      if (filterMode === 'shared' && !(a._owner && a._owner !== 'team' && a._owner !== 'household')) return false
      if (filterMode === 'pool' && !(a._owner === 'team' || a._owner === 'household')) return false
      if (filterMode.startsWith('tmpl:') && a.template !== filterMode.slice(5)) return false
      if (q) {
        const inName = (a.name || '').toLowerCase().includes(q)
        const inFields = Object.values(a.fields || {}).some(v => String(v).toLowerCase().includes(q))
        if (!inName && !inFields) return false
      }
      return true
    })
  }, [items, query, filterMode])

  const childrenMap = useMemo(() => {
    const map = {}
    const ids = new Set(filtered.map(a => a.id))
    for (const a of filtered) {
      const parent = a.parent_id && ids.has(a.parent_id) ? a.parent_id : '_root'
      ;(map[parent] = map[parent] || []).push(a)
    }
    for (const key of Object.keys(map)) {
      map[key].sort((x, y) => x.name.localeCompare(y.name))
    }
    return map
  }, [filtered])

  function toggle(id) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const roots = childrenMap['_root'] || []
  const usedTemplateKeys = [...new Set(items.map(a => a.template))]

  return (
    <div className="w-full max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="flex items-center gap-2"><h1 className="text-xl font-bold">Assets</h1><HelpButton section="assets" /><TrashLink module="assets" /></span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => (bulkSelect.active ? bulkSelect.stop() : bulkSelect.setActive(true))}
            className="btn-ghost text-xs px-3 py-1.5 md:hidden"
          >
            {bulkSelect.active ? 'Cancel' : 'Select'}
          </button>
          <button onClick={() => setShowTemplates(true)} className="btn-ghost text-xs px-3 py-1.5">
            Templates
          </button>
          <button onClick={() => setModal({ creating: true })} className="btn-primary text-xs px-3 py-1.5">
            ＋ New Asset
          </button>
        </div>
      </div>

      <BulkActionBar
        count={bulkSelect.count}
        onCancel={bulkSelect.stop}
        actions={[
          { label: 'Delete', variant: 'danger', busy: bulkDeleting, onClick: () => setConfirmBulkDelete(true) },
        ]}
      />

      {/* Search + filter */}
      {items.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search assets…"
            className="input flex-1 min-w-[10rem] !py-1.5 text-sm"
          />
          <select
            value={filterMode}
            onChange={e => setFilterMode(e.target.value)}
            className="input !py-1.5 !w-auto text-sm"
          >
            <option value="all">All</option>
            <option value="mine">Owned by me</option>
            <option value="shared">Shared with me</option>
            <option value="pool">{workspace === 'business' ? 'Team' : 'Household'}</option>
            {usedTemplateKeys.length > 0 && <option disabled>──────</option>}
            {usedTemplateKeys.map(k => (
              <option key={k} value={`tmpl:${k}`}>{templatesByKey[k]?.label || k}</option>
            ))}
          </select>
          <button
            onClick={() => setShowArchived(s => !s)}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              showArchived ? 'bg-charcoal-600 text-white' : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {showArchived ? 'Archived shown' : 'Show archived'}
          </button>
        </div>
      )}

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {/* Tree */}
      {!loaded ? (
        <div className="flex items-center justify-center h-24">
          <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <p className="text-sm font-medium">No assets yet</p>
          <p className="text-xs text-charcoal-400 max-w-sm mx-auto">
            {templates.length === 0
              ? 'Start with a blank asset, or set up a template — a premade structure like "Land Parcel" or "Vehicle" with the right fields ready to fill in — for anything you\'ll create more than once.'
              : 'Start blank, or pick one of your templates.'}
          </p>
          <div className="flex items-center justify-center gap-2 mt-1">
            <button onClick={() => setModal({ creating: true })} className="btn-primary text-xs px-4 py-2">
              ＋ New Asset
            </button>
            {templates.length === 0 && (
              <button onClick={() => setShowTemplates(true)} className="btn-ghost text-xs px-4 py-2">
                Create a template
              </button>
            )}
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-charcoal-400">No assets match.</p>
        </div>
      ) : (
        // Always foldered — a match whose parent is filtered out floats to top
        // level (childrenMap promotes it), which is exactly what we want for
        // shared/team views where a parent may not be shared. Each top-level
        // asset gets its OWN card (owner ask, 2026-08-30, applied here too
        // after Goals' own tree got the same treatment) — one card per root,
        // its own subtree rendered inside that same card via the normal
        // recursive expand, instead of every root sharing one big block.
        <div className="space-y-2">
          {roots.map(a => (
            <div key={a.id} className="card p-2">
              <AssetRow
                asset={a}
                depth={0}
                childrenMap={childrenMap}
                expanded={expanded}
                onToggle={toggle}
                onOpen={asset => setModal({ asset })}
                onAddChild={asset => setModal({ creating: true, parentId: asset.id })}
                onMove={asset => setMoveAsset(asset)}
                templatesByKey={templatesByKey}
                isAdmin={isAdmin}
                selectActive={bulkSelect.active}
                isSelected={bulkSelect.isSelected}
                onToggleSelect={bulkSelect.toggle}
              />
            </div>
          ))}
        </div>
      )}

      {confirmBulkDelete && (
        <ConfirmDialog
          title="Delete selected assets?"
          message={`${bulkSelect.count} asset${bulkSelect.count === 1 ? '' : 's'} will be moved to Trash.`}
          danger
          confirmLabel="Delete"
          onConfirm={handleBulkDelete}
          onCancel={() => setConfirmBulkDelete(false)}
        />
      )}

      {modal && (
        <AssetModal
          key={modal.asset?.id || 'new'}
          asset={modal.asset || null}
          templates={templates}
          allAssets={items}
          defaultParentId={modal.parentId || ''}
          user={user}
          workspace={workspace}
          onClose={() => setModal(null)}
          onSaved={load}
          onOpenAsset={asset => setModal({ asset })}
        />
      )}

      {moveAsset && (
        <MovePicker
          asset={moveAsset}
          allAssets={items}
          templatesByKey={templatesByKey}
          onClose={() => setMoveAsset(null)}
          onMoved={() => { setMoveAsset(null); load() }}
        />
      )}

      {showTemplates && (
        <TemplateManager
          templates={templates}
          user={{ ...user, workspace }}
          onClose={() => setShowTemplates(false)}
          onChanged={load}
        />
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
