import { useState, useEffect, useMemo } from 'react'
import HelpButton from '../components/HelpButton'
import { useSearchParams } from 'react-router-dom'
import { assets as assetsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import AssetModal from '../components/AssetModal'
import TemplateManager from '../components/TemplateManager'
import AssetTreePicker from '../components/AssetTreePicker'

const OWNER_CHIP = {
  team: '🧑‍🤝‍🧑 Team',
  household: '🏠 Household',
}

// Recursive tree row — module level per the MEMORY.md rule (components defined
// inside components remount on every parent render).
function AssetRow({ asset, depth, childrenMap, expanded, onToggle, onOpen, onAddChild, onMove, templatesByKey }) {
  const children = childrenMap[asset.id] || []
  const isOpen = expanded.has(asset.id)
  const template = asset._template || templatesByKey[asset.template]
  const status = asset.fields?.status
  const canEdit = !asset._owner || asset._access === 'edit'
  // Contribute viewers with the "children" cap may add inside (but not move)
  const canAddChild = canEdit ||
    (asset._access === 'contribute' && (asset._caps?.add || []).includes('children'))
  const pad = ['pl-0', 'pl-5', 'pl-10', 'pl-14', 'pl-20', 'pl-24'][Math.min(depth, 5)]

  return (
    <>
      <div className={`flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors group ${pad}`}>
        <button
          onClick={() => children.length && onToggle(asset.id)}
          className={`w-4 text-xs text-charcoal-400 shrink-0 ${children.length ? 'hover:text-orange-500' : 'opacity-0'}`}
        >
          {isOpen ? '▾' : '▸'}
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
        />
      ))}
    </>
  )
}

// Move an asset to a new parent via a tree/list picker (same owner only —
// changing ownership is the admin Convert action, not a move).
function MovePicker({ asset, allAssets, templatesByKey, onClose, onMoved }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

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
      <div className="modal-card p-4 max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-sm">Move “{asset.name}” to…</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
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
  const isAdmin = user?.role === 'admin'

  const [templates, setTemplates] = useState([])
  const [items, setItems] = useState([])
  const [loaded, setLoaded] = useState(false)
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
  }, [loaded, items, searchParams])

  async function load() {
    setError('')
    try {
      const [t, a] = await Promise.all([
        assetsApi.listTemplates(),
        assetsApi.list({ includeArchived: showArchived }),
      ])
      setTemplates(Array.isArray(t) ? t : [])
      setItems(Array.isArray(a) ? a : [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoaded(true)
    }
  }

  useEffect(() => { load() }, [workspace, showArchived])

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
        <span className="flex items-center gap-2"><h1 className="text-xl font-bold">Assets</h1><HelpButton section="assets" /></span>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowTemplates(true)} className="btn-ghost text-xs px-3 py-1.5">
            Templates
          </button>
          {templates.length > 0 && (
            <button onClick={() => setModal({ creating: true })} className="btn-primary text-xs px-3 py-1.5">
              ＋ New Asset
            </button>
          )}
        </div>
      </div>

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
      ) : templates.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <p className="text-sm font-medium">No templates yet</p>
          <p className="text-xs text-charcoal-400 max-w-sm mx-auto">
            Assets are built from templates — premade structures like "Land Parcel" or
            "Vehicle" with the right fields ready to fill in.
          </p>
          <button onClick={() => setShowTemplates(true)} className="btn-primary text-xs px-4 py-2 mt-2">
            Create your first template
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <p className="text-sm font-medium">No assets yet</p>
          <button onClick={() => setModal({ creating: true })} className="btn-primary text-xs px-4 py-2 mt-1">
            ＋ New Asset
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-charcoal-400">No assets match.</p>
        </div>
      ) : (
        // Always foldered — a match whose parent is filtered out floats to top
        // level (childrenMap promotes it), which is exactly what we want for
        // shared/team views where a parent may not be shared.
        <div className="card p-2">
          {roots.map(a => (
            <AssetRow
              key={a.id}
              asset={a}
              depth={0}
              childrenMap={childrenMap}
              expanded={expanded}
              onToggle={toggle}
              onOpen={asset => setModal({ asset })}
              onAddChild={asset => setModal({ creating: true, parentId: asset.id })}
              onMove={asset => setMoveAsset(asset)}
              templatesByKey={templatesByKey}
            />
          ))}
        </div>
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
    </div>
  )
}
