import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { handleTabListKeyDown } from '../lib/tabListKeyboard'
import { trash as trashApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import { useToast } from '../lib/toast'
import ConfirmDialog from '../components/ConfirmDialog'
import EmptyState from '../components/EmptyState'
import PullToRefreshIndicator from '../components/PullToRefreshIndicator'
import usePullToRefresh from '../lib/usePullToRefresh'

const MODULE_LABELS = {
  tasks: 'Tasks',
  calendar: 'Calendar',
  goals: 'Goals',
  journal: 'Journal',
  notes: 'Notes',
  assets: 'Assets',
  contacts: 'Contacts',
  finance: 'Finance',
  dashboard: 'Dashboards',
}

function daysLeft(expiresAt) {
  const ms = new Date(expiresAt).getTime() - Date.now()
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)))
}

export default function Trash() {
  const { user, activeModuleIds } = useAuth()
  const { workspace } = useWorkspace()
  const toast = useToast()
  const [searchParams] = useSearchParams()
  const moduleFilter = searchParams.get('module')

  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('personal') // 'personal' | 'pool'
  const tabRefs = useRef([])
  const [confirmState, setConfirmState] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const isAdmin = user?.role === 'admin'
  const poolId = workspace === 'business' ? 'team' : 'household'
  const poolLabel = workspace === 'business' ? 'Team' : 'Household'
  // Pool trash review is admin-only (2026-09-05) — a non-admin's own /trash
  // request never even returns pool-scope entries, so this tab only makes
  // sense to show at all when both conditions hold.
  const poolAvailable =
    isAdmin && activeModuleIds?.includes(poolId) && !user?.disabledModules?.includes(poolId)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    return trashApi
      .list()
      .then(setEntries)
      .catch(() => setError('Could not load the trash.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!poolAvailable && tab === 'pool') setTab('personal')
  }, [poolAvailable, tab])

  const pull = usePullToRefresh(load)

  const visible = useMemo(() => {
    let list = entries.filter((e) => e.scope === (poolAvailable && tab === 'pool' ? 'pool' : 'personal'))
    if (moduleFilter) list = list.filter((e) => e.module === moduleFilter)
    return list
  }, [entries, tab, poolAvailable, moduleFilter])

  const grouped = useMemo(() => {
    const groups = {}
    for (const entry of visible) {
      ;(groups[entry.module] ||= []).push(entry)
    }
    return groups
  }, [visible])

  function removeFromList(entryId) {
    setEntries((prev) => prev.filter((e) => e.id !== entryId))
  }

  async function handleRestore(entry) {
    setBusyId(entry.id)
    try {
      await trashApi.restore(entry.store_user, entry.id)
      toast.success(`Restored "${entry.title}"`)
      removeFromList(entry.id)
    } catch (err) {
      toast.error(err.message || 'Could not restore this item.')
    } finally {
      setBusyId(null)
    }
  }

  function confirmPurge(entry) {
    setConfirmState({
      title: 'Delete permanently?',
      message: `"${entry.title}" will be gone for good — this can't be undone.`,
      danger: true,
      confirmLabel: 'Delete permanently',
      onConfirm: async () => {
        setConfirmState(null)
        setBusyId(entry.id)
        try {
          await trashApi.purge(entry.store_user, entry.id)
          toast.success(`Permanently deleted "${entry.title}"`)
          removeFromList(entry.id)
        } catch (err) {
          toast.error(err.message || 'Could not delete this item.')
        } finally {
          setBusyId(null)
        }
      },
    })
  }

  const tabs = poolAvailable ? [['personal', 'Personal'], ['pool', poolLabel]] : null

  return (
    <div className="w-full max-w-2xl mx-auto space-y-5 overflow-x-hidden">
      <PullToRefreshIndicator {...pull} />
      <h1 className="text-2xl font-bold">Trash</h1>

      {tabs && (
        <div
          role="tablist"
          aria-label="Trash scope"
          className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1"
        >
          {tabs.map(([t, label], i, arr) => (
            <button
              key={t}
              ref={(el) => {
                tabRefs.current[i] = el
              }}
              role="tab"
              aria-selected={tab === t}
              tabIndex={tab === t ? 0 : -1}
              onClick={() => setTab(t)}
              onKeyDown={(e) =>
                handleTabListKeyDown(e, {
                  tabs: arr.map(([id]) => id),
                  activeIndex: i,
                  onActivate: setTab,
                  refs: tabRefs,
                })
              }
              className={`flex-1 py-1.5 rounded-md text-sm font-medium transition-colors ${
                tab === t
                  ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                  : 'text-charcoal-500 dark:text-charcoal-400'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-500">{error}</p>
      ) : visible.length === 0 ? (
        <EmptyState
          icon="🗑"
          title="Nothing here"
          description="Deleted items stay here for 30 days before they're gone for good."
        />
      ) : (
        Object.entries(grouped).map(([mod, items]) => (
          <div key={mod} className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
              {MODULE_LABELS[mod] || mod}
            </h2>
            <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
              {items.map((entry) => (
                <div key={entry.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">{entry.title}</p>
                    <p className="text-xs text-charcoal-500 dark:text-charcoal-400 truncate">
                      {entry.subtitle ? `${entry.subtitle} · ` : ''}
                      {daysLeft(entry.expires_at)}d left
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleRestore(entry)}
                      disabled={busyId === entry.id}
                      className="btn-ghost text-sm"
                    >
                      Restore
                    </button>
                    <button
                      type="button"
                      onClick={() => confirmPurge(entry)}
                      disabled={busyId === entry.id}
                      className="btn-ghost text-sm text-red-500 hover:text-red-600"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          message={confirmState.message}
          danger={confirmState.danger}
          confirmLabel={confirmState.confirmLabel}
          onConfirm={confirmState.onConfirm}
          onCancel={() => setConfirmState(null)}
        />
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
