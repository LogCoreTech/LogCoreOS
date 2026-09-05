import { useEffect, useState } from 'react'

// Item #16, 2026-09-04 UX Polish Batch — a persistent banner when the
// device loses connectivity, instead of scattered per-request error
// messages. navigator.onLine alone is unreliable (stays `true` even when
// DNS or a proxy is actually broken, only reliably reports the OS-level
// "no network interface at all" case), so this combines it with a
// lightweight periodic reachability check against the app's own /api/v1/health
// endpoint — the same one Docker's own healthcheck already hits.
export default function OfflineBanner() {
  const [offline, setOffline] = useState(!navigator.onLine)

  useEffect(() => {
    function goOffline() { setOffline(true) }
    function goOnline() { checkReachable() }
    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)

    async function checkReachable() {
      if (!navigator.onLine) {
        setOffline(true)
        return
      }
      try {
        const res = await fetch('/api/v1/health', { cache: 'no-store' })
        setOffline(!res.ok)
      } catch {
        setOffline(true)
      }
    }

    checkReachable()
    const interval = setInterval(checkReachable, 15000)
    return () => {
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
      clearInterval(interval)
    }
  }, [])

  if (!offline) return null

  return (
    <div
      role="status"
      className="shrink-0 bg-red-500/10 border-b border-red-500/20 px-4 py-2 flex items-center justify-center gap-2 text-sm text-red-600 dark:text-red-400"
    >
      <span aria-hidden>📡</span>
      <span>You&apos;re offline — some things may not work until your connection comes back.</span>
    </div>
  )
}
