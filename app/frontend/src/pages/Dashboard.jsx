import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import HelpButton from '../components/HelpButton'
import GettingStarted from '../components/GettingStarted'
import DashboardGrid, { MOBILE_COLS } from '../components/dashboard/DashboardGrid'
import BlockPicker from '../components/dashboard/BlockPicker'
import DashboardAccessModal from '../components/dashboard/DashboardAccessModal'
import DashboardSettingsModal from '../components/dashboard/DashboardSettingsModal'
import DashboardSwitcher from '../components/dashboard/DashboardSwitcher'
import CreateDashboardModal from '../components/dashboard/CreateDashboardModal'
import DashboardTemplateManager from '../components/dashboard/DashboardTemplateManager'
import DashboardHero from '../components/dashboard/DashboardHero'
import { BLOCK_REGISTRY } from '../components/dashboard/blockRegistry'
import { auth as authApi, dashboardTemplates as dashboardTemplatesApi, dashboards as dashboardsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
}

// "Last opened dashboard" (2026-08-18, owner: "make it where that as long as
// you reopen the module within [a window] it will go back to the last
// opened dashboard instead of the default... make switching back and forth
// easy") — same client-only, per-workspace localStorage-pointer shape
// Chat.jsx's own "last opened chat" already established (lc_chat_last_id_*),
// just with an expiry added, which Chat's version doesn't need (it always
// restores regardless of elapsed time). 30 minutes: long enough to survive
// a real task-switch or a short break without snapping back to the
// computed default, short enough that returning the next day still lands
// on a sensible default rather than something left open the night before —
// adjust freely if a different window feels better in practice.
const LAST_OPENED_WINDOW_MS = 30 * 60 * 1000

function lastDashboardKey(ws) {
  return `lc_dashboard_last_id_${ws}`
}

// Bottom-stacked row for a newly added block at this breakpoint. Was
// `y: Infinity` — JSON.stringify silently turns Infinity into null, so the
// server stored a literal null instead of a real row number. A concrete
// integer is required here since this value goes straight over the wire.
function nextY(blocks, breakpoint) {
  return blocks.reduce((max, b) => {
    const l = b.layout?.[breakpoint]
    if (!l) return max
    return Math.max(max, (Number(l.y) || 0) + (Number(l.h) || 0))
  }, 0)
}

export default function Dashboard() {
  const { user, updateUserField } = useAuth()
  const { workspace } = useWorkspace()
  const [searchParams, setSearchParams] = useSearchParams()

  const [items, setItems] = useState([])
  const [current, setCurrent] = useState(null) // rendered dashboard from GET /render
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [pendingLayouts, setPendingLayouts] = useState(null)
  const [showPicker, setShowPicker] = useState(false)
  const [editingBlockConfig, setEditingBlockConfig] = useState(null)
  const [showAccess, setShowAccess] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showSwitcher, setShowSwitcher] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showTemplateManager, setShowTemplateManager] = useState(false)
  const [templates, setTemplates] = useState([])
  const [saving, setSaving] = useState(false)

  const loadList = useCallback(async () => {
    const res = await dashboardsApi.list()
    setItems(res.items || [])
    return res
  }, [])

  const loadCurrent = useCallback(async (id, { resetEditing = true } = {}) => {
    const rendered = await dashboardsApi.render(id)
    setCurrent(rendered)
    if (resetEditing) setEditing(false)
    setPendingLayouts(null)
  }, [])

  // Deliberately depends on [workspace] ONLY, not idParam — the previous
  // version depended on both, and its own `setSearchParams(...)` call
  // mutated idParam, which is itself a dependency, guaranteeing a second
  // full run of this same effect on every single fresh load (loadList() +
  // loadCurrent() both fired twice back to back). `cancelled` only guarded
  // this effect's own catch/finally, never loadCurrent()'s unconditional
  // setCurrent() call, so the second run's result could still land after
  // the first — the deterministic root cause of "dashboard not found every
  // time the module opens the first time, never on a manual pick" (owner
  // report, 2026-08-18; a manual pick via selectDashboard() below never hit
  // this because it set an already-truthy idParam, so the effect only ran
  // once). A deliberate, explicit user pick or a just-created dashboard now
  // calls loadCurrent() directly instead of relying on this effect to
  // notice a URL change — see selectDashboard()/onDashboardCreated() below.
  //
  // This restructuring also closes two more owner reports in one pass:
  // - A `?id=` left over from BEFORE a workspace switch is no longer
  //   trusted blindly — it's checked against this workspace's own freshly
  //   fetched `visibleIds` first, so a dashboard that only exists in the
  //   other workspace gets replaced with a real one for the workspace
  //   you're actually on now, instead of 404ing or hanging around stale.
  //   A dashboard explicitly marked visible from both workspaces (the new
  //   cross_workspace toggle) correctly stays selected either way, since
  //   the server now includes it in `items` for both.
  // - The "last opened" pointer (see LAST_OPENED_WINDOW_MS above) is
  //   checked between a stale/absent URL id and the computed default.
  useEffect(() => {
    let cancelled = false
    async function boot() {
      setLoading(true)
      setError(null)
      try {
        const res = await loadList()
        if (cancelled) return
        const visibleIds = new Set((res.items || []).map(d => d.id))
        let targetId = null

        const urlId = searchParams.get('id')
        if (urlId && visibleIds.has(urlId)) {
          targetId = urlId
        }

        if (!targetId) {
          try {
            const raw = localStorage.getItem(lastDashboardKey(workspace))
            const stored = raw ? JSON.parse(raw) : null
            if (stored?.id && visibleIds.has(stored.id) && Date.now() - stored.savedAt < LAST_OPENED_WINDOW_MS) {
              targetId = stored.id
            }
          } catch { /* malformed/unavailable storage — fall through to default */ }
        }

        if (!targetId) targetId = res.default_id

        if (!targetId) {
          setCurrent(null)
          setSearchParams({}, { replace: true })
          setLoading(false)
          return
        }
        setSearchParams({ id: targetId }, { replace: true })
        await loadCurrent(targetId)
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load dashboard')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    boot()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace])

  // Persist "last opened" whenever the shown dashboard changes, for the
  // window-limited restore above — mirrors Chat.jsx's identical per-workspace
  // localStorage-pointer effect (keyed on chatId there, current.id here).
  useEffect(() => {
    if (!current?.id) return
    try {
      localStorage.setItem(lastDashboardKey(workspace), JSON.stringify({ id: current.id, savedAt: Date.now() }))
    } catch { /* private-browsing/storage-full — just skip persistence */ }
  }, [current?.id, workspace])

  // Auto-refresh (owner ask, 2026-08-17): a block created elsewhere (e.g. a
  // task added from another tab/session) previously never appeared — and
  // never got its own action buttons — until a manual reload, since this
  // page only ever fetched on mount/action before. Same setInterval +
  // visibilitychange pattern Chat's presence-ping effect already
  // established (Chat.jsx), just a much longer interval since dashboard
  // data changes far less often than chat presence. Skipped entirely while
  // actively editing so a background refetch never clobbers an in-progress
  // drag/resize/config change.
  useEffect(() => {
    if (!current?.id || editing) return
    function refresh() {
      if (document.visibilityState === 'visible') loadCurrent(current.id, { resetEditing: false })
    }
    const interval = setInterval(refresh, 45000)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [current?.id, editing, loadCurrent])

  async function selectDashboard(id) {
    setShowSwitcher(false)
    setSearchParams({ id })
    await loadCurrent(id)
  }

  async function onDashboardCreated(d) {
    await loadList()
    setShowSwitcher(false)
    setShowCreateModal(false)
    setSearchParams({ id: d.id })
    await loadCurrent(d.id)
  }

  async function refreshTemplates() {
    setTemplates(await dashboardTemplatesApi.list().catch(() => []))
  }

  async function openTemplateManager() {
    await refreshTemplates()
    setShowSwitcher(false)
    setShowTemplateManager(true)
  }

  async function addBlock(type, config) {
    setShowPicker(false)
    if (!current) return
    const meta = BLOCK_REGISTRY[type]
    const w = meta?.defaultLayout?.w || 12
    const h = meta?.defaultLayout?.h || 9
    const newBlock = {
      type,
      config,
      layout: {
        lg: { x: 0, y: nextY(current.blocks, 'lg'), w, h },
        sm: { x: 0, y: nextY(current.blocks, 'sm'), w: MOBILE_COLS, h },
      },
    }
    const nextBlocks = [...current.blocks, newBlock]
    await saveBlocks(nextBlocks)
  }

  async function removeBlock(blockId) {
    if (!current) return
    const block = current.blocks.find(b => b.id === blockId)
    const label = BLOCK_REGISTRY[block?.type]?.label || 'this block'
    if (!window.confirm(`Remove "${label}" from this dashboard?`)) return
    const nextBlocks = current.blocks.filter(b => b.id !== blockId)
    await saveBlocks(nextBlocks)
  }

  function openBlockConfigEditor(block) {
    setEditingBlockConfig(block)
  }

  async function saveBlockConfig(newConfig) {
    if (!current || !editingBlockConfig) return
    const nextBlocks = current.blocks.map(b =>
      b.id === editingBlockConfig.id ? { ...b, config: newConfig } : b
    )
    setEditingBlockConfig(null)
    await saveBlocks(nextBlocks)
  }

  function onLayoutChange(allLayouts) {
    setPendingLayouts(allLayouts)
  }

  async function saveBlocks(blocks) {
    setSaving(true)
    try {
      await dashboardsApi.update(current.id, {
        blocks: blocks.map(b => ({ id: b.id, type: b.type, config: b.config, layout: b.layout })),
      })
      // Adding/editing/removing a block is a mid-edit action, not a dashboard
      // switch — staying in Edit mode afterward is the whole point of "Save
      // Layout" and repeated "+ Add Block" clicks existing side by side.
      await loadCurrent(current.id, { resetEditing: false })
    } catch (e) {
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function saveLayout() {
    if (!pendingLayouts || !current) return
    const blocks = current.blocks.map(b => {
      const lg = pendingLayouts.lg?.find(l => l.i === b.id)
      const sm = pendingLayouts.sm?.find(l => l.i === b.id)
      return {
        id: b.id,
        type: b.type,
        config: b.config,
        layout: {
          lg: lg ? { x: lg.x, y: lg.y, w: lg.w, h: lg.h } : b.layout.lg,
          sm: sm ? { x: sm.x, y: sm.y, w: sm.w, h: sm.h } : b.layout.sm,
        },
      }
    })
    await saveBlocks(blocks)
  }

  async function deleteDashboard() {
    if (!current) return
    if (!window.confirm(`Delete "${current.name}"? This can't be undone.`)) return
    try {
      await dashboardsApi.remove(current.id)
      const res = await loadList()
      setSearchParams(res.default_id ? { id: res.default_id } : {})
    } catch (e) {
      setError(e.message || 'Failed to delete dashboard')
    }
  }

  async function setAsDefault() {
    if (!current) return
    const defaults = { ...(user?.defaultDashboardId || {}), [workspace]: current.id }
    await authApi.updateMe({ default_dashboard_id: defaults })
    updateUserField('defaultDashboardId', defaults)
  }

  const todayDate = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  const canEdit = current?._access === 'edit' || current?._access === 'contribute'
  const isOwner = current?.owner === user?.name

  return (
    <div key={workspace} className="w-full max-w-5xl mx-auto space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <span className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">Good {greeting()}, {user?.name?.split(' ')[0]}</h1>
            <HelpButton section="dashboard" />
          </span>
          <p className="text-charcoal-500 dark:text-charcoal-400 text-sm mt-0.5">{todayDate}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button className="btn-ghost text-sm" onClick={() => setShowSwitcher(true)}>
            {current ? `${current.icon} ${current.name}` : 'Dashboards'} ▾
          </button>
          {current && canEdit && (
            <button className="btn-ghost text-sm" onClick={() => setEditing(e => !e)}>
              {editing ? 'Done editing' : 'Edit Dashboard'}
            </button>
          )}
        </div>
      </div>

      <GettingStarted />

      {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-24 bg-charcoal-100 dark:bg-charcoal-700 rounded-lg animate-pulse" />)}
        </div>
      ) : !current ? (
        <div className="card p-8 text-center">
          <p className="text-charcoal-500 dark:text-charcoal-400 mb-3">You don&apos;t have any dashboards yet.</p>
          <button className="btn-primary" onClick={() => setShowCreateModal(true)}>+ Create your first dashboard</button>
        </div>
      ) : (
        <>
          <DashboardHero subject={current.subject} templateLabel={current.template_label} />

          {editing && (
            <div className="flex items-center gap-2 flex-wrap">
              {!current.template_id && (
                <button className="btn-primary text-sm" onClick={() => setShowPicker(true)}>+ Add Block</button>
              )}
              {pendingLayouts && (
                <button className="btn-ghost text-sm" onClick={saveLayout} disabled={saving}>
                  {saving ? 'Saving…' : 'Save Layout'}
                </button>
              )}
              <button className="btn-ghost text-sm" onClick={() => setShowSettings(true)}>⚙ Settings</button>
            </div>
          )}

          <DashboardGrid
            blocks={current.blocks}
            editing={editing}
            blocksLocked={!!current.template_id}
            onRemoveBlock={removeBlock}
            onEditBlock={openBlockConfigEditor}
            onBlockAction={() => loadCurrent(current.id, { resetEditing: false })}
            onLayoutChange={onLayoutChange}
          />
        </>
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />

      {showPicker && <BlockPicker onAdd={addBlock} onClose={() => setShowPicker(false)} />}

      {editingBlockConfig && (
        <BlockPicker
          editingBlock={editingBlockConfig}
          onSave={saveBlockConfig}
          onClose={() => setEditingBlockConfig(null)}
        />
      )}

      {showAccess && current && (
        <DashboardAccessModal
          dashboard={current}
          isPool={current._relation === 'pool'}
          isOwner={isOwner}
          onClose={() => setShowAccess(false)}
          onSaved={() => loadCurrent(current.id, { resetEditing: false })}
        />
      )}

      {showSettings && current && (
        <DashboardSettingsModal
          dashboard={current}
          isOwner={isOwner}
          user={user}
          workspace={workspace}
          onClose={() => setShowSettings(false)}
          onSaved={async () => { await loadCurrent(current.id, { resetEditing: false }); setShowSettings(false) }}
          onShare={() => { setShowSettings(false); setShowAccess(true) }}
          onSetDefault={async () => { await setAsDefault(); setShowSettings(false) }}
          onDelete={() => { setShowSettings(false); deleteDashboard() }}
        />
      )}

      {showSwitcher && (
        <DashboardSwitcher
          items={items}
          activeId={current?.id}
          onSelect={selectDashboard}
          onCreateNew={() => { setShowSwitcher(false); setShowCreateModal(true) }}
          onManageTemplates={openTemplateManager}
          onClose={() => setShowSwitcher(false)}
        />
      )}

      {showCreateModal && (
        <CreateDashboardModal
          onCreated={onDashboardCreated}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {showTemplateManager && (
        <DashboardTemplateManager
          templates={templates}
          user={user}
          onClose={() => setShowTemplateManager(false)}
          onChanged={refreshTemplates}
        />
      )}
    </div>
  )
}
