import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { setup as setupApi } from '../lib/api'

const BASE_CATEGORIES = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']

export default function Setup() {
  const [step, setStep] = useState(1)
  const [profile, setProfile] = useState('personal')
  const [role, setRole] = useState('')
  const [timezone, setTimezone] = useState(() => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Chicago' } catch { return 'America/Chicago' }
  })
  const [categories, setCategories] = useState([...BASE_CATEGORIES])
  const [customCat, setCustomCat] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [showProfileType, setShowProfileType] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    setupApi.status().then(s => setShowProfileType(s.show_profile_type ?? false)).catch(() => {})
  }, [])

  function addCustom() {
    const v = customCat.trim()
    if (v && !categories.includes(v)) {
      setCategories([...categories, v])
      setCustomCat('')
    }
  }

  function removeCategory(cat) {
    if (BASE_CATEGORIES.includes(cat)) return // can't remove base
    setCategories(categories.filter(c => c !== cat))
  }

  // Drag-to-reorder
  function onDragStart(i) { setDragIdx(i) }
  function onDragOver(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) return
    const next = [...categories]
    const [moved] = next.splice(dragIdx, 1)
    next.splice(i, 0, moved)
    setCategories(next)
    setDragIdx(i)
  }
  function onDragEnd() { setDragIdx(null) }

  async function finish() {
    setLoading(true)
    setError('')
    try {
      await setupApi.create({
        priority_order: categories,
        custom_categories: categories.filter(c => !BASE_CATEGORIES.includes(c)),
        role,
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
          <span className="text-orange-500 font-bold text-2xl">LogCore</span>
          <p className="text-charcoal-500 dark:text-charcoal-400 text-sm mt-1">Let's set up your Brain</p>
        </div>

        {/* Step indicators */}
        <div className="flex gap-2 mb-6">
          {[1,2,3].map(s => (
            <div
              key={s}
              className={`flex-1 h-1.5 rounded-full transition-colors ${
                s <= step ? 'bg-orange-500' : 'bg-charcoal-200 dark:bg-charcoal-700'
              }`}
            />
          ))}
        </div>

        <div className="card p-6">
          {step === 1 && (
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
                  Your Role / Occupation
                </label>
                <input
                  type="text"
                  value={role}
                  onChange={e => setRole(e.target.value)}
                  placeholder="e.g. Electrician, Teacher, Business Owner"
                  className="input"
                />
              </div>
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
              <button onClick={() => setStep(2)} className="btn-primary w-full mt-2">
                Next →
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <h2 className="font-semibold text-lg">Your Life Priorities</h2>
              <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                Drag to reorder. The top item has the highest weight when scoring your tasks.
              </p>

              <ul className="space-y-2">
                {categories.map((cat, i) => (
                  <li
                    key={cat}
                    draggable
                    onDragStart={() => onDragStart(i)}
                    onDragOver={e => onDragOver(e, i)}
                    onDragEnd={onDragEnd}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab active:cursor-grabbing transition-colors ${
                      dragIdx === i
                        ? 'border-orange-500 bg-orange-500/10'
                        : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                    }`}
                  >
                    <span className="text-charcoal-400 dark:text-charcoal-500 text-xs font-mono w-4">
                      {i + 1}
                    </span>
                    <span className="flex-1 text-sm font-medium">{cat}</span>
                    {!BASE_CATEGORIES.includes(cat) && (
                      <button
                        onClick={() => removeCategory(cat)}
                        className="text-charcoal-400 hover:text-red-500 text-xs"
                      >✕</button>
                    )}
                    <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
                  </li>
                ))}
              </ul>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={customCat}
                  onChange={e => setCustomCat(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addCustom()}
                  placeholder="Add custom category…"
                  className="input"
                />
                <button onClick={addCustom} className="btn-primary px-3">+</button>
              </div>

              <div className="flex gap-2">
                <button onClick={() => setStep(1)} className="btn-ghost flex-1">← Back</button>
                <button onClick={() => setStep(3)} className="btn-primary flex-1">Next →</button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <h2 className="font-semibold text-lg">Ready to Go</h2>
              <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                We'll set up your personal Brain folder with your priorities.
              </p>

              <div className="bg-charcoal-100 dark:bg-charcoal-700 rounded-lg p-4 space-y-1">
                {showProfileType && (
                  <p className="text-sm"><span className="text-charcoal-500">Profile:</span> {profile === 'business' ? 'Business' : 'Personal'}</p>
                )}
                {role && <p className="text-sm"><span className="text-charcoal-500">Occupation:</span> {role}</p>}
                <p className="text-sm"><span className="text-charcoal-500">Timezone:</span> {timezone}</p>
                <p className="text-sm font-medium mt-2">Priority order:</p>
                {categories.map((cat, i) => (
                  <p key={cat} className="text-sm text-charcoal-600 dark:text-charcoal-300">
                    {i + 1}. {cat}
                  </p>
                ))}
              </div>

              {error && <p className="text-red-500 text-sm">{error}</p>}

              <div className="flex gap-2">
                <button onClick={() => setStep(2)} className="btn-ghost flex-1">← Back</button>
                <button onClick={finish} disabled={loading} className="btn-primary flex-1">
                  {loading ? 'Setting up…' : 'Launch LogCore'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
