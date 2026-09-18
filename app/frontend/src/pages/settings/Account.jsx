import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth as authApi, user as userApi } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useToast } from '../../lib/toast'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

function detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch { return '' }
}

export default function Account() {
  const { updateUserField } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [timezone, setTimezone] = useState('')
  const [tzSaved, setTzSaved] = useState(false)
  const [autoSyncTz, setAutoSyncTz] = useState(() => localStorage.getItem('lc_auto_tz') === 'true')
  const [exporting, setExporting] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

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
      toast.error(e.message || 'Invalid timezone')
    }
  }

  async function changePassword() {
    setChangingPassword(true)
    try {
      await authApi.changePassword(currentPassword, newPassword)
      updateUserField('mustChangePassword', false)
      setCurrentPassword('')
      setNewPassword('')
      toast.success('Password changed.')
    } catch (e) {
      toast.error(e.message || 'Failed to change password')
    } finally {
      setChangingPassword(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      await userApi.export()
    } catch (e) {
      toast.error(e.message || 'Export failed')
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

      {/* Password */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Password</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Change your password. You&apos;ll need your current one.
        </p>
        <div className="space-y-2 mb-3">
          <div>
            <label className="block text-sm font-medium mb-1">Current password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              className="input w-full"
              autoComplete="current-password"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">New password</label>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              className="input w-full"
              autoComplete="new-password"
              minLength={8}
            />
          </div>
        </div>
        <button
          onClick={changePassword}
          disabled={changingPassword || !currentPassword || newPassword.length < 8}
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {changingPassword ? 'Saving…' : 'Change Password'}
        </button>
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

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
