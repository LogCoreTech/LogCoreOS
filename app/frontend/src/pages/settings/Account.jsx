import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth as authApi, user as userApi } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useToast } from '../../lib/toast'
import useEscapeToClose from '../../lib/useEscapeToClose'
import useFocusTrap from '../../lib/useFocusTrap'
import useScrollLock from '../../lib/useScrollLock'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'
import SimpleFormModal from '../../components/SimpleFormModal'
import TwoFactorSection from '../../components/settings/TwoFactorSection'

function detectTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch { return '' }
}

export default function Account() {
  const { user, updateUserField } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [timezone, setTimezone] = useState('')
  const [tzSaved, setTzSaved] = useState(false)
  const [autoSyncTz, setAutoSyncTz] = useState(() => localStorage.getItem('lc_auto_tz') === 'true')
  const [exporting, setExporting] = useState(false)
  const [email, setEmail] = useState(user?.email || '')

  // Reset Password / Update Email are popups, not default-open fields — the
  // whole point of this page is that email/password read as fixed account
  // facts you glance at, not a form you're mid-editing (owner feedback,
  // 2026-09-20).
  const [modal, setModal] = useState(null) // 'password' | 'email' | null
  const modalCardRef = useRef(null)
  useEscapeToClose(() => setModal(null))
  useFocusTrap(modalCardRef, !!modal)
  useScrollLock(!!modal)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordError, setPasswordError] = useState('')

  const [emailPassword, setEmailPassword] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [changingEmail, setChangingEmail] = useState(false)
  const [emailError, setEmailError] = useState('')

  useEffect(() => {
    authApi.me().then(me => {
      setTimezone(me.timezone || '')
      setEmail(me.email || '')
    })
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

  function closeModal() {
    setModal(null)
    setCurrentPassword('')
    setNewPassword('')
    setPasswordError('')
    setEmailPassword('')
    setNewEmail('')
    setEmailError('')
  }

  async function changePassword() {
    setPasswordError('')
    setChangingPassword(true)
    try {
      await authApi.changePassword(currentPassword, newPassword)
      updateUserField('mustChangePassword', false)
      toast.success('Password changed.')
      closeModal()
    } catch (e) {
      setPasswordError(e.message || 'Failed to change password')
    } finally {
      setChangingPassword(false)
    }
  }

  async function changeEmail() {
    setEmailError('')
    setChangingEmail(true)
    try {
      const result = await authApi.changeEmail(emailPassword, newEmail)
      setEmail(result.email)
      updateUserField('email', result.email)
      toast.success('Email updated.')
      closeModal()
    } catch (e) {
      setEmailError(e.message || 'Failed to update email')
    } finally {
      setChangingEmail(false)
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

      {/* Email + Password */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Sign-in</h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Email</p>
              <p className="text-sm font-medium truncate">{email}</p>
            </div>
            <button onClick={() => setModal('email')} className="btn-ghost text-sm shrink-0">
              Update Email
            </button>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-charcoal-100 dark:border-charcoal-800 pt-3">
            <div className="min-w-0">
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Password</p>
              <p className="text-sm font-medium tracking-widest">••••••••</p>
            </div>
            <button onClick={() => setModal('password')} className="btn-ghost text-sm shrink-0">
              Reset Password
            </button>
          </div>
        </div>
      </div>

      {/* Two-Factor Authentication (moved here from its own Security page, 2026-09-20) */}
      <TwoFactorSection />

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

      {modal === 'password' && (
        <SimpleFormModal
          cardRef={modalCardRef}
          title="Reset Password"
          onClose={closeModal}
          onCancel={closeModal}
          onSubmit={changePassword}
          submitLabel="Change Password"
          submitBusyLabel="Saving…"
          busy={changingPassword}
          submitDisabled={changingPassword || !currentPassword || newPassword.length < 8}
          error={passwordError}
        >
          <div className="space-y-2 mb-3">
            <div>
              <label className="block text-sm font-medium mb-1">Current password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={e => setCurrentPassword(e.target.value)}
                className="input w-full"
                autoComplete="current-password"
                autoFocus
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
        </SimpleFormModal>
      )}

      {modal === 'email' && (
        <SimpleFormModal
          cardRef={modalCardRef}
          title="Update Email"
          onClose={closeModal}
          onCancel={closeModal}
          onSubmit={changeEmail}
          submitLabel="Update Email"
          submitBusyLabel="Saving…"
          busy={changingEmail}
          submitDisabled={changingEmail || !emailPassword || !newEmail}
          error={emailError}
        >
          <div className="space-y-2 mb-3">
            <div>
              <label className="block text-sm font-medium mb-1">New email</label>
              <input
                type="email"
                value={newEmail}
                onChange={e => setNewEmail(e.target.value)}
                className="input w-full"
                autoComplete="email"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Current password</label>
              <input
                type="password"
                value={emailPassword}
                onChange={e => setEmailPassword(e.target.value)}
                className="input w-full"
                autoComplete="current-password"
              />
            </div>
          </div>
        </SimpleFormModal>
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
