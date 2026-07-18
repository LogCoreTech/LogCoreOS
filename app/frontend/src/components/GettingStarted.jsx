import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { help as helpApi } from '../lib/api'

// First-run checklist shown on the Dashboard. Steps mark themselves done when
// clicked; the card hides once dismissed or all steps are complete.
const STEPS = [
  { id: 'priorities', icon: '⭐', label: 'Set your life priorities', to: '/profile' },
  { id: 'first-task', icon: '✅', label: 'Create your first task', to: '/tasks' },
  { id: 'try-chat', icon: '💬', label: 'Ask the AI to plan your day', to: '/chat' },
  { id: 'read-help', icon: '❔', label: 'Skim the Help guide', to: '/help' },
]

export default function GettingStarted() {
  const [state, setState] = useState(null) // { dismissed, done: [] }

  useEffect(() => {
    helpApi.getOnboarding().then(setState).catch(() => {})
  }, [])

  if (!state || state.dismissed) return null
  const done = new Set(state.done || [])
  if (STEPS.every(s => done.has(s.id))) return null

  function complete(id) {
    if (done.has(id)) return
    setState({ ...state, done: [...(state.done || []), id] })
    helpApi.setOnboarding({ done: [id] }).catch(() => {})
  }

  function dismiss() {
    setState({ ...state, dismissed: true })
    helpApi.setOnboarding({ dismissed: true }).catch(() => {})
  }

  const completed = STEPS.filter(s => done.has(s.id)).length

  return (
    <div className="card p-5 border border-orange-500/30">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">👋 Welcome to LogCore</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">
            A few steps to get you started ({completed}/{STEPS.length}).
          </p>
        </div>
        <button
          onClick={dismiss}
          aria-label="Dismiss"
          className="shrink-0 text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-sm"
        >
          ✕
        </button>
      </div>
      <div className="mt-3 space-y-1">
        {STEPS.map(s => {
          const isDone = done.has(s.id)
          return (
            <Link
              key={s.id}
              to={s.to}
              onClick={() => complete(s.id)}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isDone ? 'text-charcoal-400' : 'hover:bg-orange-500/10'
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 text-xs ${
                  isDone
                    ? 'border-orange-500 bg-orange-500 text-white'
                    : 'border-charcoal-300 dark:border-charcoal-600'
                }`}
              >
                {isDone ? '✓' : ''}
              </span>
              <span className={`flex-1 ${isDone ? 'line-through' : ''}`}>
                {s.icon} {s.label}
              </span>
              {!isDone && <span className="text-charcoal-300 dark:text-charcoal-600" aria-hidden>→</span>}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
