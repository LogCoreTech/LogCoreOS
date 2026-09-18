import { useState } from 'react'
import { auth as authApi } from '../lib/api'
import { useAuth } from '../lib/auth'

// Gate rendered by App.jsx's <Protected> in place of the whole app when
// user.mustChangePassword is set — an admin reset this account's password
// (services/audit_log.py's "user.password_reset") and the temp password
// they were given must be replaced before anything else is usable. Same
// POST /auth/me/password endpoint Settings → Account's own "Change
// Password" section uses — the temp password IS current_password here.
export default function ForcePasswordChange() {
  const { updateUserField } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await authApi.changePassword(currentPassword, newPassword)
      updateUserField('mustChangePassword', false)
    } catch (err) {
      setError(err.message || 'Failed to change password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="card p-6 w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-bold">Set a new password</h1>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-1">
            An admin reset your password. Enter the temporary password you were given, then
            choose a new one to continue.
          </p>
        </div>
        {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}
        <div>
          <label className="block text-sm font-medium mb-1">Temporary password</label>
          <input
            type="password"
            value={currentPassword}
            onChange={e => setCurrentPassword(e.target.value)}
            className="input w-full"
            autoComplete="current-password"
            autoFocus
            required
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
            required
          />
        </div>
        <button
          type="submit"
          disabled={saving || !currentPassword || newPassword.length < 8}
          className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : 'Set Password'}
        </button>
      </form>
    </div>
  )
}
