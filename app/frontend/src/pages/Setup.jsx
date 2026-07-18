import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { setup as setupApi } from '../lib/api'

const BASE_CATEGORIES = ['Religion', 'Family', 'Job', 'Personal Growth', 'Hobbies']
const BASE_CATEGORIES_BUSINESS = ['Revenue', 'Team', 'Clients', 'Operations', 'Growth']

export default function Setup() {
  const [profile, setProfile] = useState('personal')
  const [timezone, setTimezone] = useState(() => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Chicago' } catch { return 'America/Chicago' }
  })
  const [showProfileType, setShowProfileType] = useState(false)
  const [enabledWorkspaces, setEnabledWorkspaces] = useState(['personal', 'business'])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const isBusinessOnly = enabledWorkspaces.length === 1 && enabledWorkspaces[0] === 'business'

  useEffect(() => {
    setupApi.status().then(s => {
      setShowProfileType(s.show_profile_type ?? false)
      setEnabledWorkspaces(s.enabled_workspaces || ['personal', 'business'])
    }).catch(() => {})
  }, [])

  async function finish() {
    setLoading(true)
    setError('')
    try {
      await setupApi.create({
        priority_order: isBusinessOnly ? BASE_CATEGORIES_BUSINESS : BASE_CATEGORIES,
        custom_categories: [],
        timezone,
        profile,
      })
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-charcoal-50 dark:bg-charcoal-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <img src="/icon-192.png" alt="LogCore" className="h-16 w-16 mx-auto" />
          <p className="text-charcoal-500 dark:text-charcoal-400 text-sm mt-2">Let's set up your Brain</p>
        </div>

        <div className="card p-6">
          <div className="space-y-4">
            <h2 className="font-semibold text-lg">About You</h2>

            {/* Profile type — only shown for the first user (before features.json is created) */}
            {showProfileType && (
              <div>
                <p className="block text-sm font-medium mb-2 text-charcoal-700 dark:text-charcoal-300">
                  How will you use LogCore?
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { value: 'personal', label: '🏠 Personal', desc: 'For yourself and household' },
                    { value: 'business', label: '💼 Business', desc: 'For teams and employees' },
                  ].map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setProfile(opt.value)}
                      className={`rounded-lg border-2 p-3 text-left transition-colors ${
                        profile === opt.value
                          ? 'border-orange-500 bg-orange-50 dark:bg-orange-900/20'
                          : 'border-charcoal-200 dark:border-charcoal-700 hover:border-charcoal-300 dark:hover:border-charcoal-600'
                      }`}
                    >
                      <p className="text-sm font-medium">{opt.label}</p>
                      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">{opt.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-1 text-charcoal-700 dark:text-charcoal-300">
                Timezone
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={timezone}
                  onChange={e => setTimezone(e.target.value)}
                  placeholder="e.g. America/Chicago"
                  className="input flex-1"
                />
                <button
                  type="button"
                  onClick={() => {
                    try { setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone) } catch {}
                  }}
                  className="btn-ghost text-xs px-3 whitespace-nowrap"
                >
                  Detect
                </button>
              </div>
              <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-1">
                Auto-detected from your device. Use any{' '}
                <a
                  href="https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-orange-500 hover:underline"
                >IANA timezone name</a>.
              </p>
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}

            <button onClick={finish} disabled={loading} className="btn-primary w-full mt-2">
              {loading ? 'Setting up…' : 'Launch LogCore'}
            </button>
            {!isBusinessOnly && (
              <p className="text-xs text-charcoal-400 dark:text-charcoal-500 text-center">
                Your Life Priorities start with a sensible default — fine-tune them anytime on the Profile page.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
