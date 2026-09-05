import { useEffect, useRef, useState } from 'react'
import { welcomeBack as welcomeBackApi } from '../lib/api'
import useEscapeToClose from '../lib/useEscapeToClose'
import useFocusTrap from '../lib/useFocusTrap'

// Middle-screen "welcome back" popup (item #25, 2026-09-04 UX Polish Batch) —
// checked once per app load, shown only if the backend says the user has
// been away past their configured threshold (default 7 days). If the user
// has an AI key configured AND opted into the AI summary setting, the
// backend also returns a short natural-language summary of what changed
// while they were gone — see services/welcome_back_service.py.
export default function WelcomeBackPopup() {
  const [state, setState] = useState(null) // { show, summary } | null while loading | false once dismissed

  useEffect(() => {
    welcomeBackApi
      .check()
      .then(setState)
      .catch(() => {})
  }, [])

  const dismiss = () => setState(false)
  const cardRef = useRef(null)
  useEscapeToClose(dismiss)
  // Layout.jsx mounts this component unconditionally and it decides its own
  // visibility internally (the `if (!state || !state.show) return null`
  // below) rather than being conditionally mounted/unmounted by a parent —
  // so `active` must be tied to that same visibility, or the trap's effect
  // (which only re-runs when its dependencies actually change) would stay
  // attached to nothing from the very first render, when there was no card
  // to find yet.
  useFocusTrap(cardRef, !!(state && state.show))

  if (!state || !state.show) return null

  return (
    <div className="modal-overlay" onClick={dismiss}>
      <div
        ref={cardRef}
        className="modal-card max-w-sm text-center"
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-back-title"
        onClick={e => e.stopPropagation()}
      >
        <p className="text-3xl mb-2" aria-hidden>
          👋
        </p>
        <h2 id="welcome-back-title" className="font-semibold mb-2">
          Welcome back!
        </h2>
        {state.summary ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4 whitespace-pre-line text-left">
            {state.summary}
          </p>
        ) : (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
            Good to see you again.
          </p>
        )}
        <button
          onClick={dismiss}
          className="min-h-[44px] px-6 py-2 rounded-lg text-sm font-medium text-white bg-orange-500 hover:bg-orange-400"
        >
          Let&apos;s go
        </button>
      </div>
    </div>
  )
}
