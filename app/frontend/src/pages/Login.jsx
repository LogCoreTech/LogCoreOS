import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth as authApi, setup as setupApi } from '../lib/api'
import { useAuth } from '../lib/auth'

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [registrationOpen, setRegistrationOpen] = useState(null) // null = loading
  const { login } = useAuth()
  const navigate = useNavigate()

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
        const me = await authApi.login(email, password)
        const status = await setupApi.status()
        login(me.id, me.name, me.role, me.disabled_modules || [], me.timezone || 'UTC', me.accent_color || null, me.dark_mode || 'system', me.background || null, me.density || 'comfortable', me.corner_style || 'rounded', me.workspaces || ['personal'])
        navigate(status.setup_complete ? '/' : '/setup')
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

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4 bg-cover bg-center bg-no-repeat"
      style={{ backgroundImage: 'url(/login-banner.PNG)' }}
    >
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <img src="/icon-192.png" alt="LogCore" className="h-20 w-20 mx-auto" />
          <p className="text-white/70 text-sm mt-3">
            Your life, organized by what matters most.
          </p>
        </div>

        <div className="card p-6">
          {/* Tab toggle — skeleton while status loads, tabs when open, sign-in only when closed */}
          {registrationOpen === null ? (
            <div className="h-9 bg-charcoal-100 dark:bg-charcoal-700 rounded-lg animate-pulse mb-6" />
          ) : registrationOpen ? (
            <div className="flex bg-charcoal-100 dark:bg-charcoal-700 rounded-lg p-1 mb-6">
              {['login', 'register'].map(m => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${
                    mode === m
                      ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                      : 'text-charcoal-500 dark:text-charcoal-400'
                  }`}
                >
                  {m === 'login' ? 'Sign In' : 'Create Account'}
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
                required
                className="input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1 text-charcoal-700 dark:text-charcoal-300">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={8}
                className="input"
              />
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
          </form>
        </div>
      </div>
    </div>
  )
}
