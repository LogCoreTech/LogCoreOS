import { useEffect, useRef, useState } from 'react'
import { auth as authApi, user as userApi, push as pushApi, suggestions as sugApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useNavigate } from 'react-router-dom'
import { getShortcuts, saveShortcuts, ALL_MODULES } from '../lib/constants'
import { applyAccentColor, applyDarkMode, applyBackground, applyDensity, applyCornerStyle, getSystemDarkPreference, BACKGROUND_PRESETS } from '../lib/theme'

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return new Uint8Array([...raw].map(c => c.charCodeAt(0)))
}

function detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch { return '' }
}

const SESSION_OPTIONS = [
  { label: '1 day',   value: 1440   },
  { label: '7 days',  value: 10080  },
  { label: '30 days', value: 43200  },
  { label: '90 days', value: 129600 },
]

const DEFAULT_ACCENT = '#f97316'
const PRESET_COLORS = ['#f97316', '#3b82f6', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#f59e0b', '#06b6d4']
const HEX_RE = /^#[0-9a-fA-F]{6}$/

export default function Settings() {
  const { user, logout, updateUserField } = useAuth()
  const navigate = useNavigate()
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [ntfyChannel, setNtfyChannel] = useState('')
  const [sessionMinutes, setSessionMinutes] = useState(10080)
  const [timezone, setTimezone] = useState('')
  const [tzSaved, setTzSaved] = useState(false)
  const [autoSyncTz, setAutoSyncTz] = useState(() => localStorage.getItem('lc_auto_tz') === 'true')

  // Appearance state
  const [accentColor, setAccentColor]       = useState(() => user?.accentColor  || DEFAULT_ACCENT)
  const [hexInput, setHexInput]             = useState(() => user?.accentColor  || DEFAULT_ACCENT)
  const [darkMode, setDarkMode]             = useState(() => user?.darkMode     || 'system')
  const [background, setBackground]         = useState(() => user?.background   || null)
  const [density, setDensity]               = useState(() => user?.density      || 'comfortable')
  const [cornerStyle, setCornerStyle]       = useState(() => user?.cornerStyle  || 'rounded')
  const [appearanceSaved, setAppearanceSaved] = useState(false)
  const [bgUploading, setBgUploading]       = useState(false)
  const [bgError, setBgError]               = useState('')
  const bgInputRef = useRef(null)
  const [shortcutIds, setShortcutIds] = useState(getShortcuts)
  const [shortcutDragIdx, setShortcutDragIdx] = useState(null)
  const [shortcutSaved, setShortcutSaved] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [pushStatus, setPushStatus] = useState('unknown')
  const [pushLoading, setPushLoading] = useState(false)
  const [pushMsg, setPushMsg] = useState('')
  const [sugConfig, setSugConfig] = useState(null)
  const [sugRunning, setSugRunning] = useState({})
  const [sugFlash, setSugFlash] = useState({})

  useEffect(() => {
    authApi.me().then(me => {
      setNtfyChannel(me.notification_channel || '')
      setSessionMinutes(me.session_minutes || 10080)
      setTimezone(me.timezone || '')
    }).finally(() => setLoading(false))
    sugApi.list().then(setSugConfig).catch(() => {})
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPushStatus('unsupported')
    } else {
      navigator.serviceWorker.ready.then(reg =>
        reg.pushManager.getSubscription()
      ).then(sub => {
        setPushStatus(sub ? 'subscribed' : 'unsubscribed')
      }).catch(() => setPushStatus('unsubscribed'))
    }
  }, [])

  function flash(setter) {
    setter(true)
    setTimeout(() => setter(false), 2000)
  }

  function previewAccent(hex) {
    setAccentColor(hex)
    setHexInput(hex)
    applyAccentColor(hex)
  }

  function handleHexInput(raw) {
    setHexInput(raw)
    const normalized = raw.length === 4
      ? '#' + raw.slice(1).split('').map(c => c + c).join('')
      : raw
    if (HEX_RE.test(normalized)) previewAccent(normalized)
  }

  function previewDarkMode(mode) {
    setDarkMode(mode)
    applyDarkMode(mode, getSystemDarkPreference())
  }

  function previewBackground(value) {
    setBackground(value)
    applyBackground(value)
  }

  async function saveAppearance() {
    const updates = { accent_color: accentColor, dark_mode: darkMode, density, corner_style: cornerStyle }
    if (background !== 'uploaded') updates.background = background || 'none'
    try {
      await authApi.updateMe(updates)
      updateUserField('accentColor', accentColor)
      updateUserField('darkMode', darkMode)
      updateUserField('density', density)
      updateUserField('cornerStyle', cornerStyle)
      if (background !== 'uploaded') updateUserField('background', background || null)
      flash(setAppearanceSaved)
    } catch (e) {
      alert(e.message || 'Failed to save appearance')
    }
  }

  async function handleBgUpload(file) {
    setBgUploading(true)
    setBgError('')
    try {
      await authApi.uploadBackground(file)
      setBackground('uploaded')
      applyBackground('uploaded')
      updateUserField('background', 'uploaded')
    } catch (e) {
      setBgError(e.message || 'Upload failed')
    } finally {
      setBgUploading(false)
    }
  }

  async function handleRemoveBackground() {
    try {
      await authApi.deleteBackground()
    } catch { /* ignore if no file exists */ }
    setBackground(null)
    applyBackground(null)
    updateUserField('background', null)
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

  async function subscribePush() {
    setPushLoading(true)
    setPushMsg('')
    try {
      const { publicKey } = await pushApi.vapidKey()
      const reg = await navigator.serviceWorker.ready
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') { setPushStatus('denied'); return }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _urlBase64ToUint8Array(publicKey),
      })
      await pushApi.subscribe(JSON.parse(JSON.stringify(sub)))
      setPushStatus('subscribed')
      setPushMsg('Push notifications enabled!')
    } catch (e) {
      setPushMsg(e.message || 'Failed to enable push notifications')
    } finally {
      setPushLoading(false)
    }
  }

  async function unsubscribePush() {
    setPushLoading(true)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) await sub.unsubscribe()
      await pushApi.unsubscribe()
      setPushStatus('unsubscribed')
      setPushMsg('Push notifications disabled.')
    } catch (e) {
      setPushMsg(e.message || 'Failed to disable notifications')
    } finally {
      setPushLoading(false)
    }
  }

  async function testPush() {
    setPushLoading(true)
    try {
      await pushApi.test()
      setPushMsg('Test notification sent!')
    } catch (e) {
      setPushMsg(e.message || 'Failed to send test')
    } finally {
      setPushLoading(false)
    }
  }

  async function updateSug(id, data) {
    try {
      const updated = await sugApi.update(id, data)
      setSugConfig(updated)
    } catch (e) {
      console.error('Failed to update suggestion:', e)
    }
  }

  async function runSug(id) {
    setSugRunning(p => ({ ...p, [id]: true }))
    try {
      await sugApi.run(id)
      setSugFlash(p => ({ ...p, [id]: true }))
      setTimeout(() => setSugFlash(p => ({ ...p, [id]: false })), 3000)
    } catch (e) {
      console.error('Failed to run suggestion:', e)
    } finally {
      setSugRunning(p => ({ ...p, [id]: false }))
    }
  }

  async function deleteCustomSug(id) {
    try {
      await sugApi.deleteCustom(id)
      setSugConfig(prev => prev ? { ...prev, custom: prev.custom.filter(c => c.id !== id) } : prev)
    } catch (e) {
      console.error('Failed to delete suggestion:', e)
    }
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
        <h2 className="font-semibold mb-1">Profile</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          {user?.name} · {user?.role}
        </p>
        <button onClick={() => navigate('/profile')} className="btn-primary text-sm">
          Edit Full Profile →
        </button>
      </div>

      {/* Brain Editor */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Brain Editor</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          View and edit your Brain files directly — memory, profile, notes, and more.
        </p>
        <button onClick={() => navigate('/brain')} className="btn-primary">
          Open Brain Editor
        </button>
      </div>

      {/* Appearance */}
      <div className="card p-5 space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Appearance</h2>
          {appearanceSaved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>

        {/* Dark mode */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Dark Mode</p>
          <div className="flex rounded-lg border border-charcoal-200 dark:border-charcoal-700 overflow-hidden">
            {['system', 'light', 'dark'].map(mode => (
              <button
                key={mode}
                onClick={() => previewDarkMode(mode)}
                className={`flex-1 py-1.5 text-sm font-medium capitalize transition-colors ${
                  darkMode === mode
                    ? 'bg-orange-500 text-white'
                    : 'text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-700'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        {/* Accent color */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Accent Color</p>
          <div className="flex flex-wrap gap-2 mb-3">
            {PRESET_COLORS.map(color => (
              <button
                key={color}
                onClick={() => previewAccent(color)}
                title={color}
                className="w-8 h-8 rounded-full transition-transform hover:scale-110 focus:outline-none"
                style={{
                  backgroundColor: color,
                  boxShadow: accentColor === color ? `0 0 0 2px white, 0 0 0 4px ${color}` : 'none',
                }}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={accentColor}
              onChange={e => previewAccent(e.target.value)}
              className="w-9 h-9 rounded cursor-pointer border border-charcoal-300 dark:border-charcoal-600 bg-transparent p-0.5"
              title="Pick custom color"
            />
            <input
              type="text"
              value={hexInput}
              onChange={e => handleHexInput(e.target.value)}
              placeholder="#f97316"
              maxLength={7}
              className="input w-28 font-mono text-sm"
            />
          </div>
        </div>

        {/* Background */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Background</p>
          <div className="grid grid-cols-4 gap-2 mb-3">
            {BACKGROUND_PRESETS.map(preset => {
              const isNone = preset.id === 'none'
              const isSelected = isNone
                ? (!background || background === 'none')
                : background === `gradient:${preset.id}`
              return (
                <button
                  key={preset.id}
                  onClick={() => previewBackground(isNone ? null : `gradient:${preset.id}`)}
                  title={preset.label}
                  className={`h-12 rounded-lg border-2 transition-all text-xs font-medium overflow-hidden ${
                    isSelected
                      ? 'border-orange-500 ring-1 ring-orange-500'
                      : 'border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400'
                  }`}
                  style={isNone ? {} : { background: preset.css }}
                >
                  {isNone && (
                    <span className="text-charcoal-400 dark:text-charcoal-500 text-xs">None</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Custom upload */}
          <div className="flex items-center gap-2">
            <input
              ref={bgInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/avif"
              className="hidden"
              onChange={e => { if (e.target.files?.[0]) handleBgUpload(e.target.files[0]); e.target.value = '' }}
            />
            <button
              onClick={() => bgInputRef.current?.click()}
              disabled={bgUploading}
              className="btn-ghost text-xs px-3 py-1.5 disabled:opacity-50"
            >
              {bgUploading ? 'Uploading…' : background === 'uploaded' ? 'Replace image' : 'Upload image'}
            </button>
            {(background && background !== 'none') && (
              <button
                onClick={handleRemoveBackground}
                className="text-xs text-red-500 hover:text-red-600 font-medium"
              >
                Remove
              </button>
            )}
            {background === 'uploaded' && !bgUploading && (
              <span className="text-xs text-green-500">Custom image active</span>
            )}
          </div>
          {bgError && <p className="text-xs text-red-500 mt-1">{bgError}</p>}
        </div>

        {/* Density */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Density</p>
          <div className="flex rounded-lg border border-charcoal-200 dark:border-charcoal-700 overflow-hidden">
            {['comfortable', 'compact'].map(opt => (
              <button
                key={opt}
                onClick={() => { setDensity(opt); applyDensity(opt) }}
                className={`flex-1 py-1.5 text-sm font-medium capitalize transition-colors ${
                  density === opt
                    ? 'bg-orange-500 text-white'
                    : 'text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-700'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Corners */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Corners</p>
          <div className="flex gap-3">
            {[
              { id: 'rounded', label: 'Rounded', cls: 'rounded-xl' },
              { id: 'sharp',   label: 'Sharp',   cls: 'rounded-md'  },
            ].map(({ id, label, cls }) => (
              <button
                key={id}
                onClick={() => { setCornerStyle(id); applyCornerStyle(id) }}
                className={`flex-1 flex flex-col items-center gap-2 py-3 border-2 transition-colors ${
                  cornerStyle === id
                    ? 'border-orange-500'
                    : 'border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400'
                } ${cls}`}
              >
                <div className={`w-8 h-5 bg-charcoal-300 dark:bg-charcoal-600 ${cls}`} />
                <span className="text-xs font-medium text-charcoal-600 dark:text-charcoal-300">{label}</span>
              </button>
            ))}
          </div>
        </div>

        <button onClick={saveAppearance} className="btn-primary w-full">
          Save Appearance
        </button>
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

      {/* Bottom Bar Shortcuts — mobile only */}
      <div className="card p-5 md:hidden">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Bottom Bar Shortcuts</h2>
          {shortcutSaved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Pin up to 4 modules to the bottom bar. Drag to reorder.
        </p>

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

      {/* Push Notifications */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Push Notifications</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Receive morning digests and task reminders directly in your browser or on your device.
        </p>
        {pushStatus === 'unsupported' ? (
          <p className="text-sm text-charcoal-500">Push notifications are not supported in this browser.</p>
        ) : pushStatus === 'denied' ? (
          <p className="text-sm text-red-500">Notifications are blocked. Enable them in your browser settings.</p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full ${pushStatus === 'subscribed' ? 'bg-green-500' : 'bg-charcoal-300'}`} />
              <span className="text-sm">{pushStatus === 'subscribed' ? 'Subscribed' : 'Not subscribed'}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {pushStatus !== 'subscribed' ? (
                <button onClick={subscribePush} disabled={pushLoading} className="btn-primary text-sm disabled:opacity-50">
                  {pushLoading ? 'Enabling…' : 'Enable Push Notifications'}
                </button>
              ) : (
                <>
                  <button onClick={testPush} disabled={pushLoading} className="btn-ghost text-sm disabled:opacity-50">
                    {pushLoading ? '…' : 'Send Test'}
                  </button>
                  <button onClick={unsubscribePush} disabled={pushLoading} className="text-sm text-red-500 hover:text-red-600 font-medium disabled:opacity-50">
                    Disable
                  </button>
                </>
              )}
            </div>
            {pushMsg && <p className="text-xs text-charcoal-500">{pushMsg}</p>}
          </div>
        )}
      </div>

      {/* Proactive Suggestions */}
      {sugConfig && (
        <div className="card p-5 space-y-4">
          <h2 className="font-semibold">Proactive Suggestions</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 -mt-2">
            Recurring AI-powered reminders and check-ins. Delivery: <strong>Push</strong> = ntfy + web push, <strong>In-app</strong> = bell icon, <strong>Chat</strong> = appears in AI chat on next open.
          </p>

          {[
            { id: 'daily_digest',  label: 'Daily Digest',    desc: 'Your top 3 priorities every morning', showHour: true },
            { id: 'overdue_alert', label: 'Overdue Alert',   desc: 'Alert when you have overdue tasks',   showHour: true },
            { id: 'weekly_review', label: 'Weekly Review',   desc: 'Sunday summary of completed tasks',   showHour: false },
            { id: 'goal_drift',    label: 'Goal Drift',      desc: 'Nudge when goals have no recent progress', showHour: false, showDays: true },
          ].map(({ id, label, desc, showHour, showDays }) => {
            const cfg = sugConfig[id] || {}
            const delivery = cfg.delivery || []
            return (
              <div key={id} className="border border-charcoal-200 dark:border-charcoal-700 rounded-xl p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{label}</span>
                    <p className="text-xs text-charcoal-400 dark:text-charcoal-500">{desc}</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={cfg.enabled !== false}
                      onChange={e => updateSug(id, { enabled: e.target.checked })}
                    />
                    <div className="w-9 h-5 bg-charcoal-200 dark:bg-charcoal-600 peer-checked:bg-orange-500 rounded-full transition-colors" />
                    <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                  </label>
                </div>

                <div className="flex flex-wrap gap-2 items-center">
                  {['push', 'in_app', 'chat'].map(ch => (
                    <label key={ch} className="flex items-center gap-1.5 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        className="accent-orange-500"
                        checked={delivery.includes(ch)}
                        onChange={e => {
                          const next = e.target.checked ? [...delivery, ch] : delivery.filter(d => d !== ch)
                          updateSug(id, { delivery: next })
                        }}
                      />
                      {ch === 'in_app' ? 'In-app' : ch.charAt(0).toUpperCase() + ch.slice(1)}
                    </label>
                  ))}
                  {showHour && (
                    <label className="flex items-center gap-1 text-xs ml-auto">
                      <span className="text-charcoal-400">Hour:</span>
                      <input
                        type="number"
                        min={0} max={23}
                        value={cfg.hour ?? ''}
                        placeholder="default"
                        onChange={e => {
                          const v = e.target.value === '' ? null : Number(e.target.value)
                          updateSug(id, { hour: v })
                        }}
                        className="w-16 input text-xs py-1 px-2"
                      />
                    </label>
                  )}
                  {showDays && (
                    <label className="flex items-center gap-1 text-xs ml-auto">
                      <span className="text-charcoal-400">Days:</span>
                      <input
                        type="number"
                        min={1} max={365}
                        value={cfg.days_threshold ?? 14}
                        onChange={e => updateSug(id, { days_threshold: Number(e.target.value) })}
                        className="w-16 input text-xs py-1 px-2"
                      />
                    </label>
                  )}
                  <button
                    onClick={() => runSug(id)}
                    disabled={sugRunning[id]}
                    className="ml-auto text-xs px-2.5 py-1 rounded-lg border border-charcoal-200 dark:border-charcoal-600 text-charcoal-500 hover:text-orange-500 hover:border-orange-400 transition-colors disabled:opacity-50"
                  >
                    {sugRunning[id] ? '…' : sugFlash[id] ? 'Sent ✓' : 'Run now'}
                  </button>
                </div>
              </div>
            )
          })}

          {/* Custom suggestions */}
          {sugConfig.custom?.length > 0 && (
            <div className="space-y-2 pt-1">
              <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400">Custom (AI-created)</p>
              {sugConfig.custom.map(s => {
                const schedLabel = s.schedule === 'interval'
                  ? `Every ${s.interval_days} day${s.interval_days !== 1 ? 's' : ''} at ${s.hour}:00`
                  : s.schedule === 'weekly'
                  ? `Every ${s.day_of_week} at ${s.hour}:00`
                  : `Daily at ${s.hour}:00`
                return (
                  <div key={s.id} className="border border-charcoal-200 dark:border-charcoal-700 rounded-xl p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{s.name}</p>
                        <p className="text-xs text-charcoal-400 dark:text-charcoal-500">{schedLabel}</p>
                        <div className="flex gap-1 mt-1">
                          {(s.delivery || []).map(d => (
                            <span key={d} className="text-xs bg-charcoal-100 dark:bg-charcoal-700 px-1.5 py-0.5 rounded">
                              {d === 'in_app' ? 'in-app' : d}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            className="sr-only peer"
                            checked={s.enabled !== false}
                            onChange={e => updateSug(s.id, { enabled: e.target.checked })}
                          />
                          <div className="w-9 h-5 bg-charcoal-200 dark:bg-charcoal-600 peer-checked:bg-orange-500 rounded-full transition-colors" />
                          <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                        </label>
                        <button
                          onClick={() => runSug(s.id)}
                          disabled={sugRunning[s.id]}
                          className="text-xs px-2 py-1 rounded border border-charcoal-200 dark:border-charcoal-600 text-charcoal-500 hover:text-orange-500 hover:border-orange-400 transition-colors disabled:opacity-50"
                        >
                          {sugRunning[s.id] ? '…' : sugFlash[s.id] ? '✓' : 'Run'}
                        </button>
                        <button
                          onClick={() => deleteCustomSug(s.id)}
                          className="text-xs text-red-400 hover:text-red-500"
                        >✕</button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <p className="text-xs text-charcoal-400 dark:text-charcoal-500 pt-1">
            Ask the AI to create new recurring suggestions or modify existing ones.
          </p>
        </div>
      )}

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
