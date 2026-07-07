import { useState, useEffect, useMemo } from 'react'
import { assets as assetsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import AssetModal from '../components/AssetModal'
import TemplateManager from '../components/TemplateManager'

const OWNER_CHIP = {
  team: '🧑‍🤝‍🧑 Team',
  household: '🏠 Household',
}

// Recursive tree row — module level per the MEMORY.md rule (components defined
// inside components remount on every parent render).
function AssetRow({ asset, depth, childrenMap, expanded, onToggle, onOpen, onAddChild, templatesByKey }) {
  const children = childrenMap[asset.id] || []
  const isOpen = expanded.has(asset.id)
  const template = templatesByKey[asset.template]
  const status = asset.fields?.status
  const canAddChild = !asset._owner || asset._access === 'edit'
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
        {canAddChild && (
          <button
            onClick={() => onAddChild(asset)}
            className="opacity-0 group-hover:opacity-100 btn-ghost text-xs px-2 py-0.5 shrink-0 transition-opacity"
            title="Add inside"
          >
            ＋
          </button>
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
          templatesByKey={templatesByKey}
        />
      ))}
    </>
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
  const [filter, setFilter] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [modal, setModal] = useState(null) // {asset} | {creating: true, parentId}
  const [showTemplates, setShowTemplates] = useState(false)

  async function load() {
    setError('')
    try {
      const [t, a] = await Promise.all([
        assetsApi.listTemplates(),
        assetsApi.list({ includeArchived: showArchived }),
      ])
      setTemplates(t || [])
      setItems(a || [])
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

  const filtered = useMemo(
    () => (filter ? items.filter(a => a.template === filter) : items),
    [items, filter]
  )

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

  function closeAndReload() {
    setModal(null)
    load()
  }

  const roots = childrenMap['_root'] || []
  const usedTemplateKeys = [...new Set(items.map(a => a.template))]

  return (
    <div className="w-full max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h1 className="text-xl font-bold">Assets</h1>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <button onClick={() => setShowTemplates(true)} className="btn-ghost text-xs px-3 py-1.5">
              Templates
            </button>
          )}
          {templates.length > 0 && (
            <button onClick={() => setModal({ creating: true })} className="btn-primary text-xs px-3 py-1.5">
              ＋ New Asset
            </button>
          )}
        </div>
      </div>

      {/* Filters */}
      {items.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setFilter('')}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              !filter ? 'bg-orange-500 text-white' : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300'
            }`}
          >
            All
          </button>
          {usedTemplateKeys.map(k => (
            <button
              key={k}
              onClick={() => setFilter(filter === k ? '' : k)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === k ? 'bg-orange-500 text-white' : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300'
              }`}
            >
              {templatesByKey[k]?.icon ? `${templatesByKey[k].icon} ` : ''}{templatesByKey[k]?.label || k}
            </button>
          ))}
          <button
            onClick={() => setShowArchived(s => !s)}
            className={`ml-auto px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              showArchived ? 'bg-charcoal-600 text-white' : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {showArchived ? 'Hiding nothing' : 'Show archived'}
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
          {isAdmin ? (
            <button onClick={() => setShowTemplates(true)} className="btn-primary text-xs px-4 py-2 mt-2">
              Create your first template
            </button>
          ) : (
            <p className="text-xs text-charcoal-400">Ask your admin to create templates.</p>
          )}
        </div>
      ) : roots.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <p className="text-sm font-medium">No assets yet</p>
          <button onClick={() => setModal({ creating: true })} className="btn-primary text-xs px-4 py-2 mt-1">
            ＋ New Asset
          </button>
        </div>
      ) : (
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
              templatesByKey={templatesByKey}
            />
          ))}
        </div>
      )}

      {modal && (
        <AssetModal
          asset={modal.asset || null}
          templates={templates}
          allAssets={items}
          defaultParentId={modal.parentId || ''}
          user={user}
          workspace={workspace}
          onClose={() => setModal(null)}
          onSaved={closeAndReload}
        />
      )}

      {showTemplates && (
        <TemplateManager
          templates={templates}
          onClose={() => setShowTemplates(false)}
          onChanged={load}
        />
      )}
    </div>
  )
}
