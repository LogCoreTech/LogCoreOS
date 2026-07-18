import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { help as helpApi } from '../lib/api'

// Dismissible bar shown for a few days after an app update (window driven by the
// backend). Per-version dismissal is remembered locally so it doesn't nag.
export default function WhatsNewBanner() {
  const [info, setInfo] = useState(null)
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    helpApi.whatsNew().then(setInfo).catch(() => {})
  }, [])

  if (!info?.version || hidden) return null
  if (localStorage.getItem('lc_whatsnew_dismissed') === info.version) return null

  function dismiss() {
    localStorage.setItem('lc_whatsnew_dismissed', info.version)
    setHidden(true)
  }

  return (
    <div className="shrink-0 bg-orange-500/10 border-b border-orange-500/20 px-4 py-2 flex items-center gap-3 text-sm">
      <span className="shrink-0" aria-hidden>🎉</span>
      <Link
        to="/help#whats-new"
        className="flex-1 min-w-0 truncate text-orange-700 dark:text-orange-300 hover:underline"
      >
        LogCore updated to v{info.version} — see what's new
      </Link>
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        className="shrink-0 text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200"
      >
        ✕
      </button>
    </div>
  )
}
