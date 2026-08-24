import { useEffect, useState } from 'react'
import { modStore as modStoreApi } from '../../../lib/api'
import { useAuth } from '../../../lib/auth'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

// A module's real state is two signals, not one — see docs/MEMORY.md (2026-08-24):
// `installed` (the marker, flips the instant Install/Uninstall is clicked) and
// `active` (what's genuinely registered in the running backend process, only
// updated by a restart). "Pending restart" is either direction: just installed
// but not yet active, or just uninstalled but still active in this process.
function rowState(entry, activeIds) {
  if (entry.status === 'error') return 'error'
  if (entry.status === 'coming_soon') return 'coming_soon'
  if (entry.uninstallable) return 'always_active'
  const active = activeIds.includes(entry.id)
  if (entry.installed && active) return 'active'
  if (entry.installed && !active) return 'pending_install'
  if (!entry.installed && active) return 'pending_uninstall'
  return 'not_installed'
}

const STATE_LABEL = {
  not_installed: 'Not installed',
  pending_install: 'Installed — restart to activate',
  pending_uninstall: 'Uninstalled — restart to finish',
  active: 'Active',
  always_active: 'Always active',
  coming_soon: 'Coming soon',
  error: 'Error — check server logs',
}

const STATE_BADGE = {
  not_installed: 'bg-charcoal-100 text-charcoal-600 dark:bg-charcoal-800 dark:text-charcoal-300',
  pending_install: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  pending_uninstall: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  active: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
  always_active: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
  coming_soon: 'bg-charcoal-100 text-charcoal-500 dark:bg-charcoal-800 dark:text-charcoal-400',
  error: 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400',
}

export default function ModStore() {
  const { refreshActiveModules } = useAuth()
  const [catalog, setCatalog] = useState([])
  const [activeIds, setActiveIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [restarting, setRestarting] = useState(false)
  const [msg, setMsg] = useState(null)

  async function load() {
    try {
      const [{ modules }, { active }] = await Promise.all([
        modStoreApi.catalog(),
        modStoreApi.active(),
      ])
      setCatalog(modules || [])
      setActiveIds(active || [])
    } catch (e) {
      setMsg({ ok: false, text: e.message || 'Failed to load the Mod Store catalog' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 4000)
  }

  async function handleInstall(entry) {
    setBusyId(entry.id)
    try {
      await modStoreApi.install(entry.id)
      flash(true, `${entry.name} installed — restart to activate it.`)
      await load()
    } catch (e) {
      flash(false, e.message || 'Install failed')
    } finally {
      setBusyId(null)
    }
  }

  async function handleUninstall(entry) {
    if (!window.confirm(
      `Uninstall ${entry.name}? Its data stays on disk and reinstalling brings it right back, ` +
      `but the feature disappears for everyone until you do.`
    )) return
    setBusyId(entry.id)
    try {
      await modStoreApi.uninstall(entry.id)
      flash(true, `${entry.name} uninstalled — its data was not touched.`)
      await load()
    } catch (e) {
      flash(false, e.message || 'Uninstall failed')
    } finally {
      setBusyId(null)
    }
  }

  async function doRestart(force) {
    setRestarting(true)
    try {
      const result = await modStoreApi.restart(force)
      if (result.conflict) {
        const names = result.onlineUsers.join(', ')
        setRestarting(false)
        if (window.confirm(`${result.message} (${names}). Restart anyway?`)) {
          await doRestart(true)
        }
        return
      }
      flash(true, 'Restarting… this takes a few seconds. Refresh once the app comes back.')
      await refreshActiveModules()
      await load()
    } catch (e) {
      flash(false, e.message || 'Restart failed')
    } finally {
      setRestarting(false)
    }
  }

  const pendingRestart = catalog.some(e => {
    const s = rowState(e, activeIds)
    return s === 'pending_install' || s === 'pending_uninstall'
  })

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Mod Store" backTo="/settings/admin" backLabel="Admin Settings" />

      <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
        First-party modules that extend LogCoreOS with an install. Everything here is
        built and reviewed before it's listed — nothing here is community-submitted.
      </p>

      {pendingRestart && (
        <div className="card p-4 flex items-center justify-between gap-3 border-orange-300 dark:border-orange-700">
          <p className="text-sm text-orange-700 dark:text-orange-300">
            Changes are pending — restart to apply them.
          </p>
          <button
            onClick={() => doRestart(false)}
            disabled={restarting}
            className="btn-primary text-xs shrink-0 disabled:opacity-50"
          >
            {restarting ? 'Restarting…' : 'Restart Now'}
          </button>
        </div>
      )}

      {msg && (
        <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-16 bg-charcoal-100 dark:bg-charcoal-800 rounded animate-pulse" />)}
        </div>
      ) : catalog.length === 0 ? (
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">No modules in the catalog yet.</p>
      ) : (
        <div className="space-y-3">
          {catalog.map(entry => {
            const state = rowState(entry, activeIds)
            const busy = busyId === entry.id
            return (
              <div key={entry.id} className="card p-4 flex items-start gap-3">
                <span className="text-2xl leading-none">{entry.icon || '🧩'}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold">{entry.name}</h3>
                    {entry.version && (
                      <span className="text-[10px] text-charcoal-400 dark:text-charcoal-500">v{entry.version}</span>
                    )}
                    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${STATE_BADGE[state]}`}>
                      {STATE_LABEL[state]}
                    </span>
                  </div>
                  <p className="text-sm text-charcoal-500 dark:text-charcoal-400">{entry.description}</p>
                  {state === 'error' && entry.error && (
                    <p className="text-xs text-red-500 mt-1">{entry.error}</p>
                  )}
                </div>
                {state === 'not_installed' && (
                  <button
                    onClick={() => handleInstall(entry)}
                    disabled={busy}
                    className="btn-ghost text-xs shrink-0 disabled:opacity-50"
                  >
                    {busy ? 'Installing…' : 'Install'}
                  </button>
                )}
                {(state === 'active' || state === 'pending_install') && (
                  <button
                    onClick={() => handleUninstall(entry)}
                    disabled={busy}
                    className="btn-ghost text-xs shrink-0 disabled:opacity-50"
                  >
                    {busy ? 'Uninstalling…' : 'Uninstall'}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
