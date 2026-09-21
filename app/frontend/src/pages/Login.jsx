import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth as authApi, setup as setupApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import DemoBanner from '../components/DemoBanner'
import { handleTabListKeyDown } from '../lib/tabListKeyboard'

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [registrationOpen, setRegistrationOpen] = useState(null) // null = loading
  const [bgLoaded, setBgLoaded] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [pendingToken, setPendingToken] = useState(null)
  const [totpCode, setTotpCode] = useState('')
  const [useRecoveryCode, setUseRecoveryCode] = useState(false)
  const { login, refreshUser, demoMode } = useAuth()
  const navigate = useNavigate()
  const tabRefs = useRef([])

  async function finishLogin(me) {
    const status = await setupApi.status()
    login(me.id, me.name, me.role, me.disabled_modules || [], me.timezone || 'UTC', me.accent_color || null, me.dark_mode || 'system', me.background || null, me.density || 'comfortable', me.corner_style || 'rounded', me.workspaces || ['personal'])
    // login()'s own response above is a narrower shape than /me (no
    // must_change_password, among others) — refresh from /me itself so
    // a password-reset admin flagged doesn't slip through to a normal
    // session until the next 30s poll.
    await refreshUser()
    navigate(status.setup_complete ? '/' : '/setup')
  }

  useEffect(() => {
    authApi.status()
      .then(s => setRegistrationOpen(s.registration_open))
      .catch(() => setRegistrationOpen(false))
  }, [])

  async function submit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        // Login sets the auth cookie; status check must come after so it has auth
        const result = await authApi.login(email, password)
        if (result.totp_required) {
          setPendingToken(result.pending_token)
          setMode('totp')
          return
        }
        await finishLogin(result)
      } else {
        const me = await authApi.register(email, password, name)
        login(me.id, me.name, me.role, me.disabled_modules || [], me.timezone || 'UTC', me.accent_color || null, me.dark_mode || 'system', me.background || null, me.density || 'comfortable', me.corner_style || 'rounded', me.workspaces || ['personal'])
        navigate('/setup')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitTotp(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const me = await authApi.verifyTotp(pendingToken, totpCode)
      await finishLogin(me)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDemoLogin() {
    setError('')
    setDemoLoading(true)
    try {
      let tz = 'UTC'
      try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { /* keep UTC */ }
      const me = await authApi.demoLogin(tz)
      login(me.id, me.name, me.role, me.disabled_modules || [], me.timezone || 'UTC', me.accent_color || null, me.dark_mode || 'system', me.background || null, me.density || 'comfortable', me.corner_style || 'rounded', me.workspaces || ['personal'])
      // Setup already ran server-side (demo-login provisions the Brain folder
      // directly) — straight into the app, no /setup detour.
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <>
      {demoMode && <DemoBanner />}
      <div className="relative min-h-screen flex items-center justify-center p-4 bg-charcoal-900 overflow-hidden">
      {/* Fade the banner in once fully loaded so the large PNG never paints
          top-to-bottom — the solid bg shows until the image is ready. */}
      <img
        src="/login-banner.PNG"
        alt=""
        aria-hidden="true"
        onLoad={() => setBgLoaded(true)}
        className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-700 ${bgLoaded ? 'opacity-100' : 'opacity-0'}`}
      />
      <div className="relative z-10 w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <img src="/icon-192.png" alt="LogCore" className="h-20 w-20 mx-auto" />
          <p className="text-white/70 text-sm mt-3">
            Your life, organized by what matters most.
          </p>
        </div>

        <div className="card p-6">
          {mode === 'totp' ? (
            <form onSubmit={submitTotp} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-center mb-1">Two-Factor Authentication</h2>
                <p className="text-sm text-center text-charcoal-500 dark:text-charcoal-400">
                  {useRecoveryCode
                    ? 'Enter one of your recovery codes.'
                    : 'Enter the 6-digit code from your authenticator app.'}
                </p>
              </div>
              <div>
                <input
                  type="text"
                  inputMode={useRecoveryCode ? 'text' : 'numeric'}
                  pattern={useRecoveryCode ? undefined : '[0-9]*'}
                  maxLength={useRecoveryCode ? undefined : 6}
                  value={totpCode}
                  onChange={e => setTotpCode(e.target.value)}
                  placeholder={useRecoveryCode ? 'XXXX-XXXX' : '000000'}
                  autoFocus
                  required
                  className="input text-center tracking-widest"
                />
              </div>
              {error && <p className="text-red-500 text-sm">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2 rounded-lg font-medium text-white bg-[#f97316] hover:bg-[#ea580c] transition-colors disabled:opacity-60"
              >
                {loading ? 'Verifying…' : 'Verify'}
              </button>
              <div className="flex items-center justify-between text-xs">
                <button
                  type="button"
                  onClick={() => { setUseRecoveryCode(v => !v); setTotpCode(''); setError('') }}
                  className="text-charcoal-500 dark:text-charcoal-400 underline hover:text-charcoal-700 dark:hover:text-charcoal-200"
                >
                  {useRecoveryCode ? 'Use an authenticator code instead' : 'Use a recovery code instead'}
                </button>
                <button
                  type="button"
                  onClick={() => { setMode('login'); setPendingToken(null); setTotpCode(''); setUseRecoveryCode(false); setError('') }}
                  className="text-charcoal-500 dark:text-charcoal-400 underline hover:text-charcoal-700 dark:hover:text-charcoal-200"
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
          <>
          {/* Tab toggle — skeleton while status loads, tabs when open, sign-in only when closed */}
          {registrationOpen === null ? (
            <div className="h-9 bg-charcoal-100 dark:bg-charcoal-700 rounded-lg animate-pulse mb-6" />
          ) : registrationOpen ? (
            <div role="tablist" aria-label="Sign in or create account" className="flex bg-charcoal-100 dark:bg-charcoal-700 rounded-lg p-1 mb-6">
              {['login', 'register'].map((m, i, arr) => (
                <button
                  key={m}
                  ref={el => { tabRefs.current[i] = el }}
                  role="tab"
                  aria-selected={mode === m}
                  tabIndex={mode === m ? 0 : -1}
                  onClick={() => setMode(m)}
                  onKeyDown={e => handleTabListKeyDown(e, {
                    tabs: arr,
                    activeIndex: i,
                    onActivate: setMode,
                    refs: tabRefs,
                  })}
                  className={`flex-1 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${
                    mode === m
                      ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                      : 'text-charcoal-500 dark:text-charcoal-400'
                  }`}
                >
                  {m === 'login' ? 'Sign In' : demoMode ? 'Try the Demo' : 'Create Account'}
                </button>
              ))}
            </div>
          ) : (
            // Registration closed — show sign-in only with a note
            <div className="mb-6">
              <div className="bg-charcoal-100 dark:bg-charcoal-700 rounded-lg p-1 mb-3">
                <div className="py-1.5 rounded-md text-sm font-medium text-center text-charcoal-900 dark:text-gray-100 bg-white dark:bg-charcoal-600 shadow-sm">
                  Sign In
                </div>
              </div>
              <p className="text-xs text-center text-charcoal-500 dark:text-charcoal-400">
                Need an account? Ask an admin to add you.
              </p>
            </div>
          )}

          {mode === 'register' && demoMode ? (
            <div className="space-y-4">
              <p className="text-sm text-center text-charcoal-600 dark:text-charcoal-300">
                Generates a random guest account — no email or password needed. Everything resets nightly.
              </p>
              {error && <p className="text-red-500 text-sm">{error}</p>}
              <button
                type="button"
                onClick={handleDemoLogin}
                disabled={demoLoading}
                className="w-full py-2 rounded-lg font-medium text-white bg-[#f97316] hover:bg-[#ea580c] transition-colors disabled:opacity-60"
              >
                {demoLoading ? 'Creating your demo account…' : 'Generate my demo account →'}
              </button>
              <p className="text-xs text-center text-charcoal-500 dark:text-charcoal-400">
                By continuing you agree to our{' '}
                <a href="https://logcoretech.com/privacy/" target="_blank" rel="noopener noreferrer" className="underline hover:text-charcoal-700 dark:hover:text-charcoal-200">
                  Privacy Policy
                </a>{' '}
                and{' '}
                <a href="https://logcoretech.com/terms/" target="_blank" rel="noopener noreferrer" className="underline hover:text-charcoal-700 dark:hover:text-charcoal-200">
                  Terms of Service
                </a>.
              </p>
            </div>
          ) : (
          <form onSubmit={submit} className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium mb-1 text-charcoal-700 dark:text-charcoal-300">
                  Full Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="First and Last Name"
                  autoComplete="name"
                  required
                  className="input"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-1 text-charcoal-700 dark:text-charcoal-300">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
                className="input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1 text-charcoal-700 dark:text-charcoal-300">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  minLength={8}
                  className="input pr-16"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  className="absolute inset-y-0 right-0 px-3 min-w-[44px] text-xs font-medium text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200"
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}

            {/* Literal brand orange — independent of any user's accent so the login
                page always looks the same regardless of who was last signed in. */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 rounded-lg font-medium text-white bg-[#f97316] hover:bg-[#ea580c] transition-colors disabled:opacity-60"
            >
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>

            {mode === 'register' && (
              <p className="text-xs text-center text-charcoal-500 dark:text-charcoal-400">
                By creating an account you agree to our{' '}
                <a href="https://logcoretech.com/privacy/" target="_blank" rel="noopener noreferrer" className="underline hover:text-charcoal-700 dark:hover:text-charcoal-200">
                  Privacy Policy
                </a>{' '}
                and{' '}
                <a href="https://logcoretech.com/terms/" target="_blank" rel="noopener noreferrer" className="underline hover:text-charcoal-700 dark:hover:text-charcoal-200">
                  Terms of Service
                </a>.
              </p>
            )}
          </form>
          )}
          </>
          )}
        </div>
      </div>
      </div>
    </>
  )
}
