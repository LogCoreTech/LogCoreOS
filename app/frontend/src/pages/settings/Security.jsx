import { useEffect, useState } from 'react'
import { totp as totpApi } from '../../lib/api'
import { useToast } from '../../lib/toast'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

// Combines the "shown once" temp-password box style (UserDetail.jsx's own
// password-reset card) with the real copy-button pattern (General.jsx's
// ResyncModal) — there are several codes to copy at once here, unlike a
// single short string, so a real copy-all button earns its place.
function RecoveryCodesBox({ codes, onDone }) {
  const [copied, setCopied] = useState(false)

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(codes.join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard permission denied — the text is still selectable */ }
  }

  return (
    <div className="text-sm bg-charcoal-50 dark:bg-charcoal-800 rounded-lg p-3">
      <p className="text-charcoal-500 dark:text-charcoal-400 mb-2">
        Recovery codes (shown once — save these somewhere safe). Each one works once, if you
        ever lose access to your authenticator app.
      </p>
      <div className="grid grid-cols-2 gap-1 font-mono select-all">
        {codes.map(c => <span key={c}>{c}</span>)}
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={copyAll} className="btn-ghost text-sm">
          {copied ? '✓ Copied' : 'Copy all'}
        </button>
        <button onClick={onDone} className="btn-primary text-sm">
          I&apos;ve saved these — Done
        </button>
      </div>
    </div>
  )
}

function SetupFlow({ setupData, onEnabled, onCancel }) {
  const [code, setCode] = useState('')
  const [enabling, setEnabling] = useState(false)
  const [error, setError] = useState('')

  async function confirm(e) {
    e.preventDefault()
    setError('')
    setEnabling(true)
    try {
      const result = await totpApi.enable(code)
      onEnabled(result.recovery_codes)
    } catch (err) {
      setError(err.message || 'Invalid code')
    } finally {
      setEnabling(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-center">
        <img
          src={setupData.qr_code}
          alt="Scan with your authenticator app"
          className="w-48 h-48 rounded-lg border border-charcoal-200 dark:border-charcoal-700"
        />
      </div>
      <div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-1">
          Can&apos;t scan? Enter this code manually:
        </p>
        <p className="font-mono text-sm select-all break-all bg-charcoal-50 dark:bg-charcoal-800 rounded-lg p-2">
          {setupData.secret}
        </p>
      </div>
      <form onSubmit={confirm} className="space-y-2">
        <div>
          <label className="block text-sm font-medium mb-1">
            Enter the 6-digit code from your app
          </label>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={6}
            value={code}
            onChange={e => setCode(e.target.value)}
            className="input w-full"
            autoFocus
          />
        </div>
        {error && <p className="text-sm text-red-500">{error}</p>}
        <div className="flex gap-2">
          <button type="submit" disabled={enabling || code.length < 6} className="btn-primary text-sm disabled:opacity-50">
            {enabling ? 'Confirming…' : 'Confirm'}
          </button>
          <button type="button" onClick={onCancel} className="btn-ghost text-sm">Cancel</button>
        </div>
      </form>
    </div>
  )
}

export default function Security() {
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [stage, setStage] = useState('idle') // idle | setting_up | codes_shown
  const [setupData, setSetupData] = useState(null)
  const [shownCodes, setShownCodes] = useState([])
  const [startingSetup, setStartingSetup] = useState(false)

  const [showDisable, setShowDisable] = useState(false)
  const [disablePassword, setDisablePassword] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [disabling, setDisabling] = useState(false)
  const [disableError, setDisableError] = useState('')

  const [showRegen, setShowRegen] = useState(false)
  const [regenCode, setRegenCode] = useState('')
  const [regenerating, setRegenerating] = useState(false)
  const [regenError, setRegenError] = useState('')

  function load() {
    totpApi.status().then(setStatus).catch(() => setStatus({ enabled: false, recovery_codes_remaining: 0 }))
  }

  useEffect(() => { load() }, [])

  async function startSetup() {
    setStartingSetup(true)
    try {
      const data = await totpApi.setup()
      setSetupData(data)
      setStage('setting_up')
    } catch (err) {
      toast.error(err.message || 'Failed to start setup')
    } finally {
      setStartingSetup(false)
    }
  }

  function handleEnabled(codes) {
    setShownCodes(codes)
    setStage('codes_shown')
  }

  function finishEnrollment() {
    setStage('idle')
    setSetupData(null)
    load()
  }

  async function disable(e) {
    e.preventDefault()
    setDisableError('')
    setDisabling(true)
    try {
      await totpApi.disable(disablePassword, disableCode)
      setShowDisable(false)
      setDisablePassword('')
      setDisableCode('')
      toast.success('Two-factor authentication disabled.')
      load()
    } catch (err) {
      setDisableError(err.message || 'Failed to disable')
    } finally {
      setDisabling(false)
    }
  }

  async function regenerate(e) {
    e.preventDefault()
    setRegenError('')
    setRegenerating(true)
    try {
      const result = await totpApi.regenerateRecovery(regenCode)
      setShowRegen(false)
      setRegenCode('')
      setShownCodes(result.recovery_codes)
      setStage('codes_shown')
    } catch (err) {
      setRegenError(err.message || 'Invalid code')
    } finally {
      setRegenerating(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Security" backTo="/settings" backLabel="Settings" />

      <div className="card p-5">
        <h2 className="font-semibold mb-1">Two-Factor Authentication</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Adds a 6-digit code from an authenticator app (like Google Authenticator or Authy)
          on top of your password when signing in.
        </p>

        {!status ? (
          <p className="text-sm text-charcoal-400">Loading…</p>
        ) : stage === 'setting_up' ? (
          <SetupFlow
            setupData={setupData}
            onEnabled={handleEnabled}
            onCancel={() => { setStage('idle'); setSetupData(null) }}
          />
        ) : stage === 'codes_shown' ? (
          <RecoveryCodesBox codes={shownCodes} onDone={finishEnrollment} />
        ) : status.enabled ? (
          <div className="space-y-3">
            <p className="text-sm text-green-600 dark:text-green-400">
              ✓ Enabled — {status.recovery_codes_remaining} recovery code
              {status.recovery_codes_remaining === 1 ? '' : 's'} remaining.
            </p>

            {!showDisable && !showRegen && (
              <div className="flex gap-2 flex-wrap">
                <button onClick={() => setShowRegen(true)} className="btn-ghost text-sm">
                  Generate new recovery codes
                </button>
                <button onClick={() => setShowDisable(true)} className="text-sm text-red-500 hover:text-red-600 font-medium">
                  Disable 2FA
                </button>
              </div>
            )}

            {showRegen && (
              <form onSubmit={regenerate} className="space-y-2 border-t border-charcoal-100 dark:border-charcoal-800 pt-3">
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  This invalidates your existing recovery codes. Enter a code from your app to confirm.
                </p>
                <input
                  type="text" inputMode="numeric" placeholder="6-digit code"
                  value={regenCode} onChange={e => setRegenCode(e.target.value)}
                  className="input w-full" autoFocus
                />
                {regenError && <p className="text-sm text-red-500">{regenError}</p>}
                <div className="flex gap-2">
                  <button type="submit" disabled={regenerating} className="btn-primary text-sm disabled:opacity-50">
                    {regenerating ? 'Generating…' : 'Generate'}
                  </button>
                  <button type="button" onClick={() => { setShowRegen(false); setRegenCode(''); setRegenError('') }} className="btn-ghost text-sm">
                    Cancel
                  </button>
                </div>
              </form>
            )}

            {showDisable && (
              <form onSubmit={disable} className="space-y-2 border-t border-charcoal-100 dark:border-charcoal-800 pt-3">
                <div>
                  <label className="block text-sm font-medium mb-1">Current password</label>
                  <input
                    type="password" value={disablePassword} onChange={e => setDisablePassword(e.target.value)}
                    className="input w-full" autoComplete="current-password" autoFocus
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">6-digit code (or a recovery code)</label>
                  <input
                    type="text" value={disableCode} onChange={e => setDisableCode(e.target.value)}
                    className="input w-full"
                  />
                </div>
                {disableError && <p className="text-sm text-red-500">{disableError}</p>}
                <div className="flex gap-2">
                  <button type="submit" disabled={disabling} className="text-sm text-red-500 hover:text-red-600 font-medium disabled:opacity-50">
                    {disabling ? 'Disabling…' : 'Confirm disable'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowDisable(false); setDisablePassword(''); setDisableCode(''); setDisableError('') }}
                    className="btn-ghost text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        ) : (
          <button onClick={startSetup} disabled={startingSetup} className="btn-primary text-sm disabled:opacity-50">
            {startingSetup ? 'Starting…' : 'Set up 2FA'}
          </button>
        )}
      </div>
    </div>
  )
}
