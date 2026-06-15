import { useEffect, useState } from 'react'
import { priorities as prioritiesApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useNavigate } from 'react-router-dom'

const BASE_CATS = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']

export default function Settings() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [order, setOrder] = useState([])
  const [profileOrder, setProfileOrder] = useState([])
  const [customCat, setCustomCat] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [ntfyChannel, setNtfyChannel] = useState(
    () => localStorage.getItem('lc_ntfy_channel') || ''
  )

  useEffect(() => {
    prioritiesApi.get().then(p => {
      setOrder(p.order || [])
      setProfileOrder(p.profile_order || [])
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

  async function savePriorities() {
    await prioritiesApi.override(order)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  function saveNtfy() {
    localStorage.setItem('lc_ntfy_channel', ntfyChannel)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  function handleLogout() {
    logout()
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
          Install the <strong>ntfy</strong> app on your phone. Subscribe to your personal channel to receive morning digests and overdue alerts.
        </p>
        <label className="block text-sm font-medium mb-1">Your ntfy channel name</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={ntfyChannel}
            onChange={e => setNtfyChannel(e.target.value)}
            placeholder={`logcore-${(user?.name || '').toLowerCase().replace(' ','-')}`}
            className="input"
          />
          <button onClick={saveNtfy} className="btn-primary px-4">Save</button>
        </div>
      </div>

      {/* Sign out */}
      <div className="card p-5">
        <h2 className="font-semibold mb-3">Account</h2>
        <button onClick={handleLogout} className="text-red-500 hover:text-red-600 text-sm font-medium">
          Sign out
        </button>
      </div>
    </div>
  )
}
