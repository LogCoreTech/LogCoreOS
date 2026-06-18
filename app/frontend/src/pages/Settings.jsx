import { useEffect, useState } from 'react'
import { priorities as prioritiesApi, auth as authApi, user as userApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useNavigate } from 'react-router-dom'
import { getShortcuts, saveShortcuts, ALL_MODULES } from '../lib/constants'

function detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch { return '' }
}

const BASE_CATS = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']

const SESSION_OPTIONS = [
  { label: '1 day',   value: 1440   },
  { label: '7 days',  value: 10080  },
  { label: '30 days', value: 43200  },
  { label: '90 days', value: 129600 },
]

export default function Settings() {
  const { user, logout, updateUserField } = useAuth()
  const navigate = useNavigate()
  const [order, setOrder] = useState([])
  const [profileOrder, setProfileOrder] = useState([])
  const [customCat, setCustomCat] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [ntfyChannel, setNtfyChannel] = useState('')
  const [sessionMinutes, setSessionMinutes] = useState(10080)
  const [timezone, setTimezone] = useState('')
  const [tzSaved, setTzSaved] = useState(false)
  const [autoSyncTz, setAutoSyncTz] = useState(() => localStorage.getItem('lc_auto_tz') === 'true')
  const [shortcutIds, setShortcutIds] = useState(getShortcuts)
  const [shortcutDragIdx, setShortcutDragIdx] = useState(null)
  const [shortcutSaved, setShortcutSaved] = useState(false)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    const fetches = [prioritiesApi.get(), authApi.me()]
    Promise.all(fetches).then(([p, me]) => {
      setOrder(p.order || [])
      setProfileOrder(p.profile_order || [])
      setNtfyChannel(me.notification_channel || '')
      setSessionMinutes(me.session_minutes || 10080)
      setTimezone(me.timezone || '')
    }).finally(() => setLoading(false))
  }, [])


  function addCustom() {
    const v = customCat.trim()
    if (v && !order.includes(v)) { setOrder([...order, v]); setCustomCat('') }
  }

  function removeCustom(cat) {
    if (BASE_CATS.includes(cat)) return
    setOrder(order.filter(c => c !== cat))
  }

  function onDragStart(i) { setDragIdx(i) }
  function onDragOver(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) return
    const next = [...order]
    const [m] = next.splice(dragIdx, 1)
    next.splice(i, 0, m)
    setOrder(next)
    setDragIdx(i)
  }
  function onDragEnd() { setDragIdx(null) }

  function flash(setter) {
    setter(true)
    setTimeout(() => setter(false), 2000)
  }

  async function saveTimezone() {
    try {
      await authApi.updateMe({ timezone })
      updateUserField('timezone', timezone)
      flash(setTzSaved)
    } catch (e) {
      alert(e.message || 'Invalid timezone')
    }
  }

  async function savePriorities() {
    await prioritiesApi.override(order)
    flash(setSaved)
  }

  async function saveSession() {
    try {
      await authApi.updateSession(sessionMinutes)
      flash(setSaved)
    } catch (e) {
      console.error('Failed to save session length:', e)
    }
  }

  function toggleShortcut(id) {
    if (shortcutIds.includes(id)) {
      setShortcutIds(shortcutIds.filter(s => s !== id))
    } else if (shortcutIds.length < 4) {
      setShortcutIds([...shortcutIds, id])
    }
  }

  function onShortcutDragStart(i) { setShortcutDragIdx(i) }
  function onShortcutDragOver(e, i) {
    e.preventDefault()
    if (shortcutDragIdx === null || shortcutDragIdx === i) return
    const next = [...shortcutIds]
    const [m] = next.splice(shortcutDragIdx, 1)
    next.splice(i, 0, m)
    setShortcutIds(next)
    setShortcutDragIdx(i)
  }
  function onShortcutDragEnd() { setShortcutDragIdx(null) }

  function saveShortcutsHandler() {
    saveShortcuts(shortcutIds)
    setShortcutSaved(true)
    setTimeout(() => setShortcutSaved(false), 2000)
  }

  async function handleExport() {
    setExporting(true)
    try {
      await userApi.export()
    } catch (e) {
      alert(e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Profile */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Profile</h2>
        <div className="text-sm space-y-1 text-charcoal-700 dark:text-charcoal-300">
          <p><span className="text-charcoal-500">Name:</span> {user?.name}</p>
          <p><span className="text-charcoal-500">Role:</span> {user?.role}</p>
        </div>
      </div>

      {/* Priority order */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Life Priority Order</h2>
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          This sets today's priority override. Your profile default is: {profileOrder.join(' → ')}
        </p>

        {loading ? (
          <div className="space-y-2">{[1,2,3].map(i=><div key={i} className="h-10 bg-charcoal-100 dark:bg-charcoal-700 rounded animate-pulse"/>)}</div>
        ) : (
          <>
            <ul className="space-y-2 mb-4">
              {order.map((cat, i) => (
                <li
                  key={cat}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={e => onDragOver(e, i)}
                  onDragEnd={onDragEnd}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                    dragIdx === i
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                  }`}
                >
                  <span className="text-charcoal-400 text-xs w-4">{i+1}</span>
                  <span className="flex-1 text-sm">{cat}</span>
                  {!BASE_CATS.includes(cat) && (
                    <button onClick={() => removeCustom(cat)} className="text-charcoal-400 hover:text-red-500 text-xs">✕</button>
                  )}
                  <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
                </li>
              ))}
            </ul>

            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={customCat}
                onChange={e => setCustomCat(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCustom()}
                placeholder="Add category…"
                className="input"
              />
              <button onClick={addCustom} className="btn-primary px-3">+</button>
            </div>

            <button onClick={savePriorities} className="btn-primary w-full">
              Apply Today's Order
            </button>
          </>
        )}
      </div>

      {/* Notifications */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Notifications (ntfy)</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Install the <strong>ntfy</strong> app on your phone and subscribe to your personal channel to receive morning digests and alerts.
        </p>
        {ntfyChannel ? (
          <div>
            <label className="block text-sm font-medium mb-1">Your ntfy channel</label>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-charcoal-100 dark:bg-charcoal-700 text-sm px-3 py-2 rounded-lg font-mono break-all">
                {ntfyChannel}
              </code>
              <button
                onClick={() => navigator.clipboard?.writeText(ntfyChannel)}
                className="text-xs text-charcoal-500 hover:text-orange-500 whitespace-nowrap"
              >
                Copy
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-charcoal-500">Channel loading…</p>
        )}
      </div>

      {/* Session length */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Session Length</h2>
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          How long you stay signed in before needing to log in again.
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
          <button onClick={saveSession} className="btn-primary px-4">Save</button>
        </div>
        <p className="text-xs text-charcoal-400 mt-2">
          Takes effect on your next sign-in.
        </p>
      </div>

      {/* Timezone */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Timezone</h2>
          {tzSaved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Used for due dates, task scoring, and morning digests. Set to your local zone.
        </p>
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={timezone}
            onChange={e => setTimezone(e.target.value)}
            placeholder="e.g. America/Chicago"
            className="input flex-1"
          />
          <button
            onClick={() => { const tz = detectTz(); if (tz) setTimezone(tz) }}
            className="btn-ghost text-xs px-3 whitespace-nowrap"
          >
            Detect
          </button>
          <button onClick={saveTimezone} className="btn-primary px-4">Save</button>
        </div>
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={autoSyncTz}
            onChange={e => {
              setAutoSyncTz(e.target.checked)
              localStorage.setItem('lc_auto_tz', String(e.target.checked))
            }}
            className="accent-orange-500 w-4 h-4 mt-0.5 shrink-0"
          />
          <div>
            <span className="text-sm font-medium">Auto-sync to device location</span>
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5">
              Automatically updates your timezone when you open the app from a different location.
              Useful for travellers or shared devices.
            </p>
          </div>
        </label>
      </div>

      {/* Bottom Bar Shortcuts */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Bottom Bar Shortcuts</h2>
          {shortcutSaved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Pin up to 4 modules to the bottom bar. Drag to reorder.
        </p>

        {/* Pinned shortcuts — draggable */}
        <ul className="space-y-2 mb-3">
          {shortcutIds.map((id, i) => {
            const mod = ALL_MODULES.find(m => m.id === id)
            if (!mod) return null
            return (
              <li
                key={id}
                draggable
                onDragStart={() => onShortcutDragStart(i)}
                onDragOver={e => onShortcutDragOver(e, i)}
                onDragEnd={onShortcutDragEnd}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                  shortcutDragIdx === i
                    ? 'border-orange-500 bg-orange-500/10'
                    : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                }`}
              >
                <span className="text-base leading-none">{mod.icon}</span>
                <span className="flex-1 text-sm">{mod.label}</span>
                <button
                  onClick={() => toggleShortcut(id)}
                  className="text-charcoal-400 hover:text-red-500 text-xs"
                >✕</button>
                <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
              </li>
            )
          })}
        </ul>

        {/* Available modules to add */}
        {shortcutIds.length < 4 && (
          <div className="mb-4">
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mb-2">
              Add ({4 - shortcutIds.length} slot{4 - shortcutIds.length !== 1 ? 's' : ''} left):
            </p>
            <div className="flex flex-wrap gap-2">
              {ALL_MODULES.filter(m => !shortcutIds.includes(m.id)).map(mod => (
                <button
                  key={mod.id}
                  onClick={() => toggleShortcut(mod.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-charcoal-300 dark:border-charcoal-600 text-xs text-charcoal-500 dark:text-charcoal-400 hover:border-orange-500 hover:text-orange-500 transition-colors"
                >
                  <span>{mod.icon}</span>
                  {mod.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <button onClick={saveShortcutsHandler} className="btn-primary w-full">
          Save Shortcuts
        </button>
      </div>

      {/* Account */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Account</h2>
        <div className="space-y-3">
          <button
            onClick={handleExport}
            disabled={exporting}
            className="btn-ghost w-full text-left text-sm"
          >
            {exporting ? 'Preparing download…' : '⬇ Export Brain (zip)'}
          </button>
          <button onClick={handleLogout} className="text-red-500 hover:text-red-600 text-sm font-medium block">
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}
