import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth as authApi, user as userApi } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

function detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch { return '' }
}

export default function Account() {
  const { updateUserField } = useAuth()
  const navigate = useNavigate()
  const [timezone, setTimezone] = useState('')
  const [tzSaved, setTzSaved] = useState(false)
  const [autoSyncTz, setAutoSyncTz] = useState(() => localStorage.getItem('lc_auto_tz') === 'true')
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    authApi.me().then(me => setTimezone(me.timezone || ''))
  }, [])

  async function saveTimezone() {
    try {
      await authApi.updateMe({ timezone })
      updateUserField('timezone', timezone)
      setTzSaved(true)
      setTimeout(() => setTzSaved(false), 2000)
    } catch (e) {
      alert(e.message || 'Invalid timezone')
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

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Account" backTo="/settings" backLabel="Settings" />

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

      {/* Your Brain */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Your Brain</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          View and edit your Brain files directly — memory, profile, notes, and more.
        </p>
        <button onClick={() => navigate('/brain')} className="btn-primary">
          Open Brain Editor
        </button>
      </div>

      {/* Export */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Export</h2>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="btn-ghost w-full text-left text-sm"
        >
          {exporting ? 'Preparing download…' : '⬇ Export Brain (zip)'}
        </button>
      </div>
    </div>
  )
}
