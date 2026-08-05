import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import HelpButton from '../components/HelpButton'
import GettingStarted from '../components/GettingStarted'
import DashboardGrid from '../components/dashboard/DashboardGrid'
import BlockPicker from '../components/dashboard/BlockPicker'
import DashboardAccessModal from '../components/dashboard/DashboardAccessModal'
import DashboardSwitcher from '../components/dashboard/DashboardSwitcher'
import { BLOCK_REGISTRY } from '../components/dashboard/blockRegistry'
import { auth as authApi, dashboards as dashboardsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
}

export default function Dashboard() {
  const { user, updateUserField } = useAuth()
  const { workspace } = useWorkspace()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [items, setItems] = useState([])
  const [current, setCurrent] = useState(null) // rendered dashboard from GET /render
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [pendingLayouts, setPendingLayouts] = useState(null)
  const [showPicker, setShowPicker] = useState(false)
  const [showAccess, setShowAccess] = useState(false)
  const [showSwitcher, setShowSwitcher] = useState(false)
  const [saving, setSaving] = useState(false)

  const idParam = searchParams.get('id')

  const loadList = useCallback(async () => {
    const res = await dashboardsApi.list()
    setItems(res.items || [])
    return res
  }, [])

  const loadCurrent = useCallback(async (id) => {
    const rendered = await dashboardsApi.render(id)
    setCurrent(rendered)
    setEditing(false)
    setPendingLayouts(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      setLoading(true)
      setError(null)
      try {
        const res = await loadList()
        if (cancelled) return
        const targetId = idParam || res.default_id
        if (!targetId) {
          setCurrent(null)
          setLoading(false)
          return
        }
        if (!idParam) {
          setSearchParams({ id: targetId }, { replace: true })
        }
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
  }, [workspace, idParam])

  async function selectDashboard(id) {
    setShowSwitcher(false)
    setSearchParams({ id })
  }

  async function createDashboard() {
    const d = await dashboardsApi.create('New Dashboard', '📊')
    await loadList()
    setShowSwitcher(false)
    setSearchParams({ id: d.id })
  }

  async function addBlock(type, config) {
    setShowPicker(false)
    if (!current) return
    const meta = BLOCK_REGISTRY[type]
    const w = meta?.defaultLayout?.w || 4
    const h = meta?.defaultLayout?.h || 3
    const newBlock = {
      type,
      config,
      layout: { lg: { x: 0, y: Infinity, w, h }, sm: { x: 0, y: Infinity, w: 2, h } },
    }
    const nextBlocks = [...current.blocks, newBlock]
    await saveBlocks(nextBlocks)
  }

  async function removeBlock(blockId) {
    if (!current) return
    const nextBlocks = current.blocks.filter(b => b.id !== blockId)
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
      await loadCurrent(current.id)
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
    <div key={workspace} className="max-w-5xl mx-auto space-y-4">
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
              {editing ? 'Done editing' : 'Edit Layout'}
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
          <p className="text-charcoal-500 dark:text-charcoal-400 mb-3">You don't have any dashboards yet.</p>
          <button className="btn-primary" onClick={createDashboard}>+ Create your first dashboard</button>
        </div>
      ) : (
        <>
          {editing && (
            <div className="flex items-center gap-2 flex-wrap">
              <button className="btn-primary text-sm" onClick={() => setShowPicker(true)}>+ Add Block</button>
              {pendingLayouts && (
                <button className="btn-ghost text-sm" onClick={saveLayout} disabled={saving}>
                  {saving ? 'Saving…' : 'Save Layout'}
                </button>
              )}
              <button className="btn-ghost text-sm" onClick={() => setShowAccess(true)}>Share</button>
              <button className="btn-ghost text-sm" onClick={setAsDefault}>Set as default</button>
              <button className="btn-ghost text-sm text-red-500" onClick={deleteDashboard}>Delete dashboard</button>
            </div>
          )}

          <DashboardGrid
            blocks={current.blocks}
            editing={editing}
            onRemoveBlock={removeBlock}
            onLayoutChange={onLayoutChange}
          />
        </>
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />

      {showPicker && <BlockPicker onAdd={addBlock} onClose={() => setShowPicker(false)} />}

      {showAccess && current && (
        <DashboardAccessModal
          dashboard={current}
          isPool={current._relation === 'pool'}
          isOwner={isOwner}
          onClose={() => setShowAccess(false)}
          onSaved={() => loadCurrent(current.id)}
        />
      )}

      {showSwitcher && (
        <DashboardSwitcher
          items={items}
          activeId={current?.id}
          onSelect={selectDashboard}
          onCreate={createDashboard}
          onClose={() => setShowSwitcher(false)}
        />
      )}
    </div>
  )
}
