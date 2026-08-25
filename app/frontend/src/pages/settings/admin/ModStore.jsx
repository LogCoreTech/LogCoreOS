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
  pending_install: 'Restart to activate',
  pending_uninstall: 'Restart to finish',
  active: 'Active',
  always_active: 'Always active',
  coming_soon: 'Coming soon',
  error: 'Error — check logs',
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

  // Returns the freshly-fetched {modules, active} (not just the state setters)
  // so a caller like the restart poll below can check what actually came back
  // this round — reading catalog/activeIds state right after calling load()
  // would see whatever the last completed render had, not this fetch's result.
  // `silent` skips the error flash — used while polling through a restart,
  // where a failed fetch just means the container is momentarily down
  // between the old process dying and the new one coming up, not a real
  // error worth alarming the admin about.
  async function load(silent = false) {
    try {
      const [{ modules }, { active }] = await Promise.all([
        modStoreApi.catalog(),
        modStoreApi.active(),
      ])
      setCatalog(modules || [])
      setActiveIds(active || [])
      return { modules: modules || [], active: active || [] }
    } catch (e) {
      if (!silent) setMsg({ ok: false, text: e.message || 'Failed to load the Mod Store catalog' })
      return null
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

  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

  // The backend defers the actual container restart by ~2s and the restart
  // itself (stop old process, start new one, boot the app) takes real time —
  // loading right after the request returns just re-shows the same pending
  // state (the "banner never disappeared, worked again after reopening the
  // page" report). Poll instead, and keep `restarting` (which disables this
  // button) true for the whole window, not just the initial request, so a
  // second click can't land while the first restart is still in flight —
  // that's what turned into the "pressing again returned an error" report.
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
      flash(true, 'Restarting… this can take up to a minute.')

      const deadline = Date.now() + 60_000
      while (Date.now() < deadline) {
        await sleep(2000)
        const fresh = await load(true)
        if (!fresh) continue // container between old-dead and new-ready — keep polling through the gap
        const stillPending = fresh.modules.some(e => {
          const s = rowState(e, fresh.active)
          return s === 'pending_install' || s === 'pending_uninstall'
        })
        if (!stillPending) {
          await refreshActiveModules()
          flash(true, 'Restarted — changes are live.')
          return
        }
      }
      flash(false, 'Restart is taking longer than expected — reopen this page in a moment.')
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
        built and reviewed before it&apos;s listed — nothing here is community-submitted.
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
              // Keyed on state+busy, not just entry.id, so React fully remounts
              // this row on every visually-relevant transition instead of
              // mutating it in place. Reported bug: the badge/button got cut
              // short/clipped mid-transition (install ↔ uninstall, busy ↔ not)
              // on mobile, fixed only by a full page reload — i.e. broken on
              // in-place update, correct on a fresh mount. `.card`'s
              // backdrop-blur-sm is the suspected mechanism (this app has hit
              // backdrop-filter compositing bugs before — see docs/MEMORY.md
              // 2026-08-18's ContactRow popover-clipping entry), but forcing a
              // remount fixes the symptom regardless of the exact cause, and
              // costs nothing on a row this small.
              <div key={`${entry.id}:${state}:${busy}`} className="card p-4 flex items-start gap-3">
                <span className="text-2xl leading-none shrink-0">{entry.icon || '🧩'}</span>
                <div className="flex-1 min-w-0">
                  {/* Badge pinned to its own corner, not wrapped inline with the
                      title — on a narrow viewport, name + version + a longer
                      badge label used to fight for the same line and wrap the
                      badge itself half off-screen. justify-between keeps the
                      badge fixed at top-right (shrink-0, never wraps); the
                      name truncates instead if it's the one that's too long. */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex items-baseline gap-2">
                      <h3 className="font-semibold truncate">{entry.name}</h3>
                      {entry.version && (
                        <span className="text-[10px] text-charcoal-400 dark:text-charcoal-500 shrink-0">v{entry.version}</span>
                      )}
                    </div>
                    <span className={`shrink-0 whitespace-nowrap text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${STATE_BADGE[state]}`}>
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
