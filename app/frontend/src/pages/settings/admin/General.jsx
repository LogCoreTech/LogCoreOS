import { useEffect, useRef, useState } from 'react'
import { admin as adminApi, update as updateApi } from '../../../lib/api'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const SESSION_OPTIONS = [
  { label: '1 hour',  value: 60     },
  { label: '1 day',   value: 1440   },
  { label: '7 days',  value: 10080  },
  { label: '30 days', value: 43200  },
  { label: '90 days', value: 129600 },
]

function RegistrationSection() {
  const [allowed, setAllowed] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    adminApi.getSettings()
      .then(d => setAllowed(d.allow_open_registration ?? false))
      .catch(() => {})
  }, [])

  async function toggle() {
    const next = !allowed
    setSaving(true)
    setMsg(null)
    try {
      const updated = await adminApi.updateSettings({ allow_open_registration: next })
      setAllowed(updated.allow_open_registration)
      setMsg({ ok: true, text: next ? 'Registration is now open.' : 'Registration is now closed.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Failed to save' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Registration</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        When closed, only admins can create new accounts.
      </p>

      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Open registration</p>
          <p className="text-xs text-charcoal-400">
            {allowed ? 'Anyone can create an account.' : 'New sign-ups are disabled.'}
          </p>
        </div>

        <button
          onClick={toggle}
          disabled={saving}
          className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
            allowed ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-700'
          } disabled:opacity-50`}
          role="switch"
          aria-checked={allowed}
        >
          <span
            className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ${
              allowed ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {msg && (
        <p className={`text-sm mt-3 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}

const WORKSPACES = [
  { id: 'personal', label: 'Personal', desc: 'Personal life OS: household, journal, smart home.' },
  { id: 'business', label: 'Business', desc: 'Business workspace: team pool, business automations.' },
]

function WorkspaceVisibilitySection() {
  const [enabled, setEnabled] = useState(['personal', 'business'])
  const [saving, setSaving]   = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    adminApi.getSettings()
      .then(d => setEnabled(d.enabled_workspaces || ['personal', 'business']))
      .catch(() => {})
  }, [])

  async function toggle(ws) {
    const next = enabled.includes(ws) ? enabled.filter(w => w !== ws) : [...enabled, ws]
    if (next.length === 0) {
      setMsg({ ok: false, text: 'At least one workspace must stay enabled.' })
      setTimeout(() => setMsg(null), 4000)
      return
    }
    setSaving(true)
    setMsg(null)
    try {
      const updated = await adminApi.updateSettings({ enabled_workspaces: next })
      setEnabled(updated.enabled_workspaces || next)
      setMsg({ ok: true, text: 'Workspace visibility updated.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Failed to save' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Workspaces</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Hide a workspace across the whole instance — even for admins. Use this for a
        personal-only or business-only install.
      </p>

      <div className="space-y-3">
        {WORKSPACES.map(ws => {
          const on = enabled.includes(ws.id)
          return (
            <div key={ws.id} className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">{ws.label}</p>
                <p className="text-xs text-charcoal-400">{ws.desc}</p>
              </div>
              <button
                onClick={() => toggle(ws.id)}
                disabled={saving}
                className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
                  on ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-700'
                } disabled:opacity-50`}
                role="switch"
                aria-checked={on}
              >
                <span
                  className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ${
                    on ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          )
        })}
      </div>

      {msg && (
        <p className={`text-sm mt-3 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}

function SessionLengthSection() {
  const [sessionMinutes, setSessionMinutes] = useState(10080)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    adminApi.getSettings().then(d => setSessionMinutes(d.session_minutes ?? 10080)).catch(() => {})
  }, [])

  async function save() {
    setSaving(true)
    try {
      const updated = await adminApi.updateSettings({ session_minutes: sessionMinutes })
      setSessionMinutes(updated.session_minutes ?? sessionMinutes)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save session length:', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-semibold">Session Length</h2>
        {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
      </div>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
        How long everyone stays signed in before needing to log in again. Applies instance-wide —
        there is no per-user override. Changing this only affects logins from this point forward;
        already-active sessions are not forced to re-authenticate.
      </p>
      <div className="flex gap-2">
        <select
          value={sessionMinutes}
          onChange={e => setSessionMinutes(Number(e.target.value))}
          className="input flex-1"
        >
          {SESSION_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <button onClick={save} disabled={saving} className="btn-primary px-4 disabled:opacity-50">
          {saving ? '…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

function UpdateSection() {
  const [status, setStatus]         = useState(null)
  const [log, setLog]               = useState([])
  const [showLog, setShowLog]       = useState(false)
  const [applying, setApplying]     = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [togglingAuto, setTogglingAuto] = useState(false)
  const [msg, setMsg]               = useState(null)
  const [showResync, setShowResync] = useState(false)
  const pollRef                     = useRef(null)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 6000)
  }

  async function loadStatus() {
    try {
      setStatus(await updateApi.status())
    } catch { /* silent — backend may be restarting */ }
  }

  async function loadLog() {
    try {
      const r = await updateApi.log(120)
      setLog(r.lines || [])
    } catch {}
  }

  useEffect(() => { loadStatus() }, [])

  useEffect(() => {
    clearInterval(pollRef.current)
    if (status?.update_pending || status?.resync_pending || status?.update_running) {
      pollRef.current = setInterval(() => { loadStatus(); if (showLog) loadLog() }, 8000)
    }
    return () => clearInterval(pollRef.current)
  }, [status?.update_pending, status?.resync_pending, status?.update_running, showLog])

  async function applyUpdate() {
    if (!status?.daemon_active) {
      flash(false, 'Update daemon is not running. The update cannot be applied. See setup instructions below.')
      return
    }
    if (!confirm('Apply update now?\n\nThe daemon will back up your Brain, pull the latest code, rebuild, and restart. Rolls back automatically if anything fails.')) return
    setApplying(true)
    try {
      await updateApi.apply()
      flash(true, 'Update queued — the daemon will apply it within 60 seconds.')
      loadStatus()
    } catch (e) {
      flash(false, e.message || 'Failed to queue update')
    } finally {
      setApplying(false)
    }
  }

  async function toggleAutoUpdate() {
    if (!status) return
    const newVal = !status.auto_update_enabled
    setTogglingAuto(true)
    try {
      await updateApi.patchSettings({ auto_update: newVal })
      setStatus(s => ({ ...s, auto_update_enabled: newVal }))
    } catch (e) {
      flash(false, e.message || 'Failed to save setting')
    } finally {
      setTogglingAuto(false)
    }
  }

  const isWorking = status?.update_pending || status?.resync_pending || status?.update_running
  const ffFailed = status?.last_update?.result === 'ff-failed' && !isWorking

  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-semibold">Updates</h2>
        {status?.update_available && !isWorking && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 font-medium">
            Update available
          </span>
        )}
        {!status?.update_available && !isWorking && status && (
          <span className="text-xs text-green-600 dark:text-green-400">✓ Up to date</span>
        )}
      </div>

      {!status ? (
        <p className="text-sm text-charcoal-500">Loading…</p>
      ) : (
        <>
          <div className="text-sm space-y-1.5">
            <div className="flex justify-between">
              <span className="text-charcoal-500 dark:text-charcoal-400">Installed</span>
              <span className="font-mono">{status.current_version}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-charcoal-500 dark:text-charcoal-400">Latest</span>
              <span className="font-mono">
                {status.latest_version
                  ? <a href={status.release_url} target="_blank" rel="noreferrer" className="hover:text-orange-500 transition-colors">{status.latest_version}</a>
                  : (status.check_error ? 'unavailable' : '—')}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-charcoal-500 dark:text-charcoal-400">Daemon</span>
              <span className={`text-xs font-medium ${status.daemon_active ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
                {status.daemon_active ? '● active' : '○ not running'}
              </span>
            </div>
          </div>

          {!status.daemon_active && (
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3 text-xs text-yellow-800 dark:text-yellow-300 space-y-1">
              <p className="font-medium">Update daemon not running</p>
              <p>Updates can&apos;t be applied without it. Start it on the host:</p>
              <code className="block bg-yellow-100 dark:bg-yellow-900/40 px-2 py-1 rounded mt-1">bash launch.sh</code>
              <p className="text-yellow-600 dark:text-yellow-400">launch.sh installs the update cron automatically on every run.</p>
            </div>
          )}

          <div className="flex items-center justify-between py-1 border-t border-charcoal-100 dark:border-charcoal-800">
            <div>
              <p className="text-sm font-medium">Auto-update</p>
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                Apply new versions automatically when detected
              </p>
            </div>
            <button
              onClick={toggleAutoUpdate}
              disabled={togglingAuto}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                status.auto_update_enabled ? 'bg-orange-500' : 'bg-charcoal-300 dark:bg-charcoal-600'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                status.auto_update_enabled ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>

          {status.check_error && (
            <p className="text-xs text-charcoal-400">Check error: {status.check_error}</p>
          )}

          {isWorking && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
              {status.update_running
                ? '⟳ Update in progress — app will restart momentarily.'
                : status.resync_pending
                ? '⏳ Resync queued — daemon will apply it within 60 seconds.'
                : '⏳ Update queued — daemon will apply it within 60 seconds.'}
            </div>
          )}

          {status.last_update?.result && !['success', 'up-to-date'].includes(status.last_update.result) && !isWorking && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300 space-y-2">
              <p>
              {status.last_update.result === 'rollback'
                ? '⚠ Last update failed and was rolled back automatically. Check the log below.'
                : status.last_update.result === 'fetch-failed'
                ? '⚠ Last update could not fetch new code from GitHub (nothing was changed). Check the host repo\'s remote URL/credentials and the log below.'
                : status.last_update.result === 'success-stamp-failed'
                ? '⚠ Last update deployed, but the new version could not be recorded — check brain/_system permissions and the log below.'
                : status.last_update.result === 'resync-failed'
                ? '⚠ The resync fix itself failed — this needs manual attention. Check the log below.'
                : status.last_update.result === 'ff-failed'
                ? '⚠ Last update refused to apply — this instance\'s git history no longer shares commits with the latest release (most likely the project rewrote its history upstream since this instance last updated). Nothing was changed.'
                : `⚠ Last update did not complete (${status.last_update.result}). Check the log below.`}
              </p>
              {ffFailed && (
                <button
                  onClick={() => setShowResync(true)}
                  className="text-sm font-medium underline hover:no-underline"
                >
                  Fix Automatically →
                </button>
              )}
            </div>
          )}

          {msg && (
            <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</p>
          )}

          <div className="flex gap-2 flex-wrap">
            {status.update_available && !isWorking && (
              <button
                onClick={applyUpdate}
                disabled={applying || !status.daemon_active}
                className="btn-primary text-sm flex-1 disabled:opacity-50"
                title={!status.daemon_active ? 'Daemon not running' : ''}
              >
                {applying ? 'Queuing…' : 'Apply Update'}
              </button>
            )}
            <button
              onClick={() => { setShowLog(v => !v); if (!showLog) loadLog() }}
              className="btn-ghost text-sm"
            >
              {showLog ? 'Hide Log' : 'View Log'}
            </button>
            <button
              onClick={async () => {
                setRefreshing(true)
                try { setStatus(await updateApi.check()) } catch { await loadStatus() }
                setRefreshing(false)
              }}
              disabled={refreshing}
              className="text-sm text-charcoal-500 hover:text-orange-500 transition-colors disabled:opacity-50 px-2"
              title="Check for updates now (bypasses the cache)"
            >
              {refreshing ? '…' : '↺'}
            </button>
          </div>

          {showLog && (
            <div className="bg-charcoal-900 dark:bg-black rounded-lg p-3 text-xs font-mono text-charcoal-100 max-h-56 overflow-y-auto space-y-0.5">
              {log.length === 0
                ? <span className="text-charcoal-500">No update log yet.</span>
                : log.map((line, i) => <div key={i}>{line}</div>)
              }
            </div>
          )}
        </>
      )}

      {showResync && (
        <ResyncModal
          onClose={() => setShowResync(false)}
          onQueued={() => { setShowResync(false); loadStatus() }}
          flash={flash}
          currentVersion={status.current_version}
          latestVersion={status.latest_version}
        />
      )}
    </div>
  )
}

function ResyncModal({ onClose, onQueued, flash, currentVersion, latestVersion }) {
  const [running, setRunning] = useState(false)
  const [copied, setCopied]   = useState(false)
  const fixCommand = 'git fetch origin --force --tags && git reset --hard origin/master'
  const compareUrl = currentVersion && latestVersion
    ? `https://github.com/LogCoreTech/LogCoreOS/compare/v${currentVersion}...v${latestVersion}`
    : null

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(fixCommand)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard permission denied — the text is still selectable */ }
  }

  async function runFix() {
    if (!confirm(
      'Reset this instance\'s local git history to match the latest release?\n\n' +
      'This discards only local git commits — your Brain data lives outside the repo ' +
      'and is never touched. The daemon will then rebuild and restart as a normal update would.'
    )) return
    setRunning(true)
    try {
      await updateApi.resync()
      flash(true, 'Resync queued — the daemon will apply it within 60 seconds.')
      onQueued()
    } catch (e) {
      flash(false, e.message || 'Failed to queue resync')
      setRunning(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Fix Update Divergence</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>

        <div className="space-y-3 text-sm">
          <p className="text-charcoal-600 dark:text-charcoal-300">
            The last update refused to apply because this instance&apos;s local git history no
            longer shares commits with the latest release — most likely the project rewrote
            its published history upstream (rare; usually to remove something that should
            never have been committed, like a leaked internal detail) since this instance
            last updated.
          </p>
          <p className="text-charcoal-600 dark:text-charcoal-300">
            The fix resets <em>only this instance&apos;s copy of the app&apos;s own source code</em> to
            match the latest release. Your Brain data (tasks, notes, everything under{' '}
            <code className="text-xs bg-charcoal-100 dark:bg-charcoal-800 px-1 rounded">brain/</code>)
            lives outside the code repository and is never touched by this.
          </p>
          {compareUrl && (
            <a
              href={compareUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-orange-600 dark:text-orange-400 hover:underline"
            >
              See exactly what will change (v{currentVersion} → v{latestVersion}) on GitHub →
            </a>
          )}

          <div>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-1">
              To do it yourself instead, run this on the host:
            </p>
            <div className="flex items-start gap-2 bg-charcoal-900 dark:bg-black rounded-lg p-3">
              <code className="text-xs font-mono text-charcoal-100 flex-1 break-all">{fixCommand}</code>
              <button
                onClick={copyCommand}
                className="text-xs text-charcoal-400 hover:text-white shrink-0"
                title="Copy to clipboard"
              >
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <button
            onClick={runFix}
            disabled={running}
            className="btn-primary text-sm w-full disabled:opacity-50"
          >
            {running ? 'Queuing…' : 'Fix Automatically'}
          </button>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 text-center">
            Runs the same command above via the update daemon, then rebuilds and restarts
            like a normal update.
          </p>
        </div>
      </div>
    </div>
  )
}

export default function General() {
  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="General" backTo="/settings/admin" backLabel="Admin Settings" />
      <RegistrationSection />
      <WorkspaceVisibilitySection />
      <SessionLengthSection />
      <UpdateSection />

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
