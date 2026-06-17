import { useEffect, useState } from 'react'
import { priorities as prioritiesApi, auth as authApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useNavigate } from 'react-router-dom'

const BASE_CATS = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']

const SESSION_OPTIONS = [
  { label: '1 day',   value: 1440   },
  { label: '7 days',  value: 10080  },
  { label: '30 days', value: 43200  },
  { label: '90 days', value: 129600 },
]

export default function Settings() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [order, setOrder] = useState([])
  const [profileOrder, setProfileOrder] = useState([])
  const [customCat, setCustomCat] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [ntfyChannel, setNtfyChannel] = useState('')
  const [sessionMinutes, setSessionMinutes] = useState(10080)

  useEffect(() => {
    Promise.all([
      prioritiesApi.get(),
      authApi.me(),
    ]).then(([p, me]) => {
      setOrder(p.order || [])
      setProfileOrder(p.profile_order || [])
      setNtfyChannel(me.notification_channel || '')
      setSessionMinutes(me.session_minutes || 10080)
    }).finally(() => setLoading(false))
  }, [])

  function addCustom() {
    const v = customCat.trim()
    if (v && !order.includes(v)) { setOrder([...order, v]); setCustomCat('') }
  }

  function removeCustom(cat) {
    if (BASE_CATS.includes(cat)) return
    setOrder(order.filter(c => c !== cat))
  }

  function onDragStart(i) { setDragIdx(i) }
  function onDragOver(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) return
    const next = [...order]
    const [m] = next.splice(dragIdx, 1)
    next.splice(i, 0, m)
    setOrder(next)
    setDragIdx(i)
  }
  function onDragEnd() { setDragIdx(null) }

  function flash() {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function savePriorities() {
    await prioritiesApi.override(order)
    flash()
  }

  async function saveSession() {
    await authApi.updateSession(sessionMinutes)
    flash()
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
        <h2 className="font-semibold mb-3">Profile</h2>
        <div className="text-sm space-y-1 text-charcoal-700 dark:text-charcoal-300">
          <p><span className="text-charcoal-500">Name:</span> {user?.name}</p>
          <p><span className="text-charcoal-500">Role:</span> {user?.role}</p>
        </div>
      </div>

      {/* Priority order */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Life Priority Order</h2>
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          This sets today's priority override. Your profile default is: {profileOrder.join(' → ')}
        </p>

        {loading ? (
          <div className="space-y-2">{[1,2,3].map(i=><div key={i} className="h-10 bg-charcoal-100 dark:bg-charcoal-700 rounded animate-pulse"/>)}</div>
        ) : (
          <>
            <ul className="space-y-2 mb-4">
              {order.map((cat, i) => (
                <li
                  key={cat}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={e => onDragOver(e, i)}
                  onDragEnd={onDragEnd}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                    dragIdx === i
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                  }`}
                >
                  <span className="text-charcoal-400 text-xs w-4">{i+1}</span>
                  <span className="flex-1 text-sm">{cat}</span>
                  {!BASE_CATS.includes(cat) && (
                    <button onClick={() => removeCustom(cat)} className="text-charcoal-400 hover:text-red-500 text-xs">✕</button>
                  )}
                  <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
                </li>
              ))}
            </ul>

            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={customCat}
                onChange={e => setCustomCat(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCustom()}
                placeholder="Add category…"
                className="input"
              />
              <button onClick={addCustom} className="btn-primary px-3">+</button>
            </div>

            <button onClick={savePriorities} className="btn-primary w-full">
              Apply Today's Order
            </button>
          </>
        )}
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

      {/* Account */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Account</h2>
        <button onClick={handleLogout} className="text-red-500 hover:text-red-600 text-sm font-medium">
          Sign out
        </button>
      </div>
    </div>
  )
}
