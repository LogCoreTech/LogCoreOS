import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { auth as authApi, push as pushApi, suggestions as sugApi } from '../../lib/api'
import HelpButton from '../../components/HelpButton'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return new Uint8Array([...raw].map(c => c.charCodeAt(0)))
}

export default function Notifications() {
  const [ntfyChannel, setNtfyChannel] = useState('')
  const [channelRotatedAt, setChannelRotatedAt] = useState(null)
  const [rotating, setRotating] = useState(false)
  const [rotateError, setRotateError] = useState('')
  const [rotateSaved, setRotateSaved] = useState(false)

  const [pushStatus, setPushStatus] = useState('unknown')
  const [pushLoading, setPushLoading] = useState(false)
  const [pushMsg, setPushMsg] = useState('')

  const [sugConfig, setSugConfig] = useState(null)
  const [sugRunning, setSugRunning] = useState({})
  const [sugFlash, setSugFlash] = useState({})

  useEffect(() => {
    authApi.me().then(me => {
      setNtfyChannel(me.notification_channel || '')
      setChannelRotatedAt(me.channel_rotated_at || null)
    })
    sugApi.list().then(setSugConfig).catch(() => {})
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPushStatus('unsupported')
    } else {
      navigator.serviceWorker.ready.then(reg =>
        reg.pushManager.getSubscription()
      ).then(sub => {
        setPushStatus(sub ? 'subscribed' : 'unsubscribed')
      }).catch(() => setPushStatus('unsubscribed'))
    }
  }, [])

  function flash(setter) {
    setter(true)
    setTimeout(() => setter(false), 2000)
  }

  async function rotateChannel() {
    setRotating(true)
    setRotateError('')
    try {
      const res = await authApi.rotateChannel()
      setNtfyChannel(res.notification_channel)
      setChannelRotatedAt(res.channel_rotated_at)
      flash(setRotateSaved)
    } catch (err) {
      setRotateError(err.message || 'Rotation failed')
    } finally {
      setRotating(false)
    }
  }

  async function subscribePush() {
    setPushLoading(true)
    setPushMsg('')
    try {
      const { publicKey } = await pushApi.vapidKey()
      const reg = await navigator.serviceWorker.ready
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') { setPushStatus('denied'); return }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _urlBase64ToUint8Array(publicKey),
      })
      await pushApi.subscribe(JSON.parse(JSON.stringify(sub)))
      setPushStatus('subscribed')
      setPushMsg('Push notifications enabled!')
    } catch (e) {
      setPushMsg(e.message || 'Failed to enable push notifications')
    } finally {
      setPushLoading(false)
    }
  }

  async function unsubscribePush() {
    setPushLoading(true)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) await sub.unsubscribe()
      await pushApi.unsubscribe()
      setPushStatus('unsubscribed')
      setPushMsg('Push notifications disabled.')
    } catch (e) {
      setPushMsg(e.message || 'Failed to disable notifications')
    } finally {
      setPushLoading(false)
    }
  }

  async function testPush() {
    setPushLoading(true)
    try {
      await pushApi.test()
      setPushMsg('Test notification sent!')
    } catch (e) {
      setPushMsg(e.message || 'Failed to send test')
    } finally {
      setPushLoading(false)
    }
  }

  async function updateSug(id, data) {
    try {
      const updated = await sugApi.update(id, data)
      setSugConfig(updated)
    } catch (e) {
      console.error('Failed to update suggestion:', e)
    }
  }

  async function runSug(id) {
    setSugRunning(p => ({ ...p, [id]: true }))
    try {
      await sugApi.run(id)
      setSugFlash(p => ({ ...p, [id]: true }))
      setTimeout(() => setSugFlash(p => ({ ...p, [id]: false })), 3000)
    } catch (e) {
      console.error('Failed to run suggestion:', e)
    } finally {
      setSugRunning(p => ({ ...p, [id]: false }))
    }
  }

  async function deleteCustomSug(id) {
    try {
      await sugApi.deleteCustom(id)
      setSugConfig(prev => prev ? { ...prev, custom: prev.custom.filter(c => c.id !== id) } : prev)
    } catch (e) {
      console.error('Failed to delete suggestion:', e)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Notifications" backTo="/settings" backLabel="Settings" />

      {/* ntfy */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">
          Notifications (ntfy)
          <HelpButton section="notifications" className="ml-1 align-middle" />
        </h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Install the <strong>ntfy</strong> app on your phone and subscribe to your personal channel to receive morning digests and alerts. By default ntfy runs self-hosted on your server's local network only — for notifications away from home, use Web Push below, or ask an admin to give ntfy a public address (see the <Link to="/help#notifications" className="text-orange-500 hover:underline">Notifications guide</Link> for setup steps). Your channel ID is the only thing protecting it, so treat it like a password: don't share it, and rotate it if you ever suspect it's leaked.
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
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-2">
              {channelRotatedAt
                ? `Last rotated ${new Date(channelRotatedAt).toLocaleDateString()}`
                : 'Never rotated since account creation'}
              {' — '}we'll remind you here once it's over 30 days old.
            </p>
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={rotateChannel}
                disabled={rotating}
                className="btn-ghost text-xs disabled:opacity-50"
              >
                {rotating ? 'Rotating…' : 'Rotate channel'}
              </button>
              {rotateSaved && <span className="text-green-500 text-xs">Rotated ✓ — update the topic in your ntfy app</span>}
              {rotateError && <span className="text-red-500 text-xs">{rotateError}</span>}
            </div>
          </div>
        ) : (
          <p className="text-sm text-charcoal-500">Channel loading…</p>
        )}
      </div>

      {/* Push Notifications */}
      <div className="card p-5">
        <h2 className="font-semibold mb-1">Push Notifications</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Receive morning digests and task reminders directly in your browser or on your device.
        </p>
        {pushStatus === 'unsupported' ? (
          <p className="text-sm text-charcoal-500">Push notifications are not supported in this browser.</p>
        ) : pushStatus === 'denied' ? (
          <p className="text-sm text-red-500">Notifications are blocked. Enable them in your browser settings.</p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full ${pushStatus === 'subscribed' ? 'bg-green-500' : 'bg-charcoal-300'}`} />
              <span className="text-sm">{pushStatus === 'subscribed' ? 'Subscribed' : 'Not subscribed'}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {pushStatus !== 'subscribed' ? (
                <button onClick={subscribePush} disabled={pushLoading} className="btn-primary text-sm disabled:opacity-50">
                  {pushLoading ? 'Enabling…' : 'Enable Push Notifications'}
                </button>
              ) : (
                <>
                  <button onClick={testPush} disabled={pushLoading} className="btn-ghost text-sm disabled:opacity-50">
                    {pushLoading ? '…' : 'Send Test'}
                  </button>
                  <button onClick={unsubscribePush} disabled={pushLoading} className="text-sm text-red-500 hover:text-red-600 font-medium disabled:opacity-50">
                    Disable
                  </button>
                </>
              )}
            </div>
            {pushMsg && <p className="text-xs text-charcoal-500">{pushMsg}</p>}
          </div>
        )}
      </div>

      {/* Proactive Suggestions */}
      {sugConfig && (
        <div className="card p-5 space-y-4">
          <h2 className="font-semibold">Proactive Suggestions</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 -mt-2">
            Recurring AI-powered reminders and check-ins. Delivery: <strong>Push</strong> = ntfy + web push, <strong>In-app</strong> = bell icon, <strong>Chat</strong> = appears in AI chat on next open.
          </p>

          {[
            { id: 'daily_digest',  label: 'Daily Digest',    desc: 'Your top 3 priorities every morning', showHour: true },
            { id: 'overdue_alert', label: 'Overdue Alert',   desc: 'Alert when you have overdue tasks',   showHour: true },
            { id: 'weekly_review', label: 'Weekly Review',   desc: 'Sunday summary of completed tasks',   showHour: false },
            { id: 'goal_drift',    label: 'Goal Drift',      desc: 'Nudge when goals have no recent progress', showHour: false, showDays: true },
          ].map(({ id, label, desc, showHour, showDays }) => {
            const cfg = sugConfig[id] || {}
            const delivery = cfg.delivery || []
            return (
              <div key={id} className="border border-charcoal-200 dark:border-charcoal-700 rounded-xl p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{label}</span>
                    <p className="text-xs text-charcoal-400 dark:text-charcoal-500">{desc}</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={cfg.enabled !== false}
                      onChange={e => updateSug(id, { enabled: e.target.checked })}
                    />
                    <div className="w-9 h-5 bg-charcoal-200 dark:bg-charcoal-600 peer-checked:bg-orange-500 rounded-full transition-colors" />
                    <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                  </label>
                </div>

                <div className="flex flex-wrap gap-2 items-center">
                  {['push', 'in_app', 'chat'].map(ch => (
                    <label key={ch} className="flex items-center gap-1.5 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        className="accent-orange-500"
                        checked={delivery.includes(ch)}
                        onChange={e => {
                          const next = e.target.checked ? [...delivery, ch] : delivery.filter(d => d !== ch)
                          updateSug(id, { delivery: next })
                        }}
                      />
                      {ch === 'in_app' ? 'In-app' : ch.charAt(0).toUpperCase() + ch.slice(1)}
                    </label>
                  ))}
                  {showHour && (
                    <label className="flex items-center gap-1 text-xs ml-auto">
                      <span className="text-charcoal-400">Hour:</span>
                      <input
                        type="number"
                        min={0} max={23}
                        value={cfg.hour ?? ''}
                        placeholder="default"
                        onChange={e => {
                          const v = e.target.value === '' ? null : Number(e.target.value)
                          updateSug(id, { hour: v })
                        }}
                        className="w-16 input text-xs py-1 px-2"
                      />
                    </label>
                  )}
                  {showDays && (
                    <label className="flex items-center gap-1 text-xs ml-auto">
                      <span className="text-charcoal-400">Days:</span>
                      <input
                        type="number"
                        min={1} max={365}
                        value={cfg.days_threshold ?? 14}
                        onChange={e => updateSug(id, { days_threshold: Number(e.target.value) })}
                        className="w-16 input text-xs py-1 px-2"
                      />
                    </label>
                  )}
                  <button
                    onClick={() => runSug(id)}
                    disabled={sugRunning[id]}
                    className="ml-auto text-xs px-2.5 py-1 rounded-lg border border-charcoal-200 dark:border-charcoal-600 text-charcoal-500 hover:text-orange-500 hover:border-orange-400 transition-colors disabled:opacity-50"
                  >
                    {sugRunning[id] ? '…' : sugFlash[id] ? 'Sent ✓' : 'Run now'}
                  </button>
                </div>
              </div>
            )
          })}

          {/* Custom suggestions */}
          {sugConfig.custom?.length > 0 && (
            <div className="space-y-2 pt-1">
              <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400">Custom (AI-created)</p>
              {sugConfig.custom.map(s => {
                const schedLabel = s.schedule === 'interval'
                  ? `Every ${s.interval_days} day${s.interval_days !== 1 ? 's' : ''} at ${s.hour}:00`
                  : s.schedule === 'weekly'
                  ? `Every ${s.day_of_week} at ${s.hour}:00`
                  : `Daily at ${s.hour}:00`
                return (
                  <div key={s.id} className="border border-charcoal-200 dark:border-charcoal-700 rounded-xl p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{s.name}</p>
                        <p className="text-xs text-charcoal-400 dark:text-charcoal-500">{schedLabel}</p>
                        <div className="flex gap-1 mt-1">
                          {(s.delivery || []).map(d => (
                            <span key={d} className="text-xs bg-charcoal-100 dark:bg-charcoal-700 px-1.5 py-0.5 rounded">
                              {d === 'in_app' ? 'in-app' : d}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            className="sr-only peer"
                            checked={s.enabled !== false}
                            onChange={e => updateSug(s.id, { enabled: e.target.checked })}
                          />
                          <div className="w-9 h-5 bg-charcoal-200 dark:bg-charcoal-600 peer-checked:bg-orange-500 rounded-full transition-colors" />
                          <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                        </label>
                        <button
                          onClick={() => runSug(s.id)}
                          disabled={sugRunning[s.id]}
                          className="text-xs px-2 py-1 rounded border border-charcoal-200 dark:border-charcoal-600 text-charcoal-500 hover:text-orange-500 hover:border-orange-400 transition-colors disabled:opacity-50"
                        >
                          {sugRunning[s.id] ? '…' : sugFlash[s.id] ? '✓' : 'Run'}
                        </button>
                        <button
                          onClick={() => deleteCustomSug(s.id)}
                          className="text-xs text-red-400 hover:text-red-500"
                        >✕</button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <p className="text-xs text-charcoal-400 dark:text-charcoal-500 pt-1">
            Ask the AI to create new recurring suggestions or modify existing ones.
          </p>
        </div>
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
