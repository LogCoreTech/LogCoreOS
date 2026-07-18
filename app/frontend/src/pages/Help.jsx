import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { help as helpApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import { ALL_MODULES } from '../lib/constants'

// A section is "mine" if it isn't tied to any module, or if at least one of its
// modules is enabled for me in the active workspace.
function useMyModuleIds() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  return useMemo(() => {
    const disabled = new Set(user?.disabledModules || [])
    const ids = new Set()
    for (const m of ALL_MODULES) {
      if (disabled.has(m.id)) continue
      if (m.workspace && m.workspace !== workspace) continue
      ids.add(m.id)
    }
    return ids
  }, [user?.disabledModules, workspace])
}

function matches(section, q) {
  if (!q) return true
  const hay = [
    section.title,
    section.blurb,
    ...(section.howto || []),
    ...(section.tips || []),
  ].join(' ').toLowerCase()
  return hay.includes(q)
}

export default function Help() {
  const { user } = useAuth()
  const location = useLocation()
  const myModules = useMyModuleIds()
  const isAdmin = user?.role === 'admin'

  const [content, setContent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [onlyMine, setOnlyMine] = useState(false)
  const [openFaq, setOpenFaq] = useState(null)

  useEffect(() => {
    helpApi.content()
      .then(setContent)
      .catch(() => setError('Could not load help content.'))
      .finally(() => setLoading(false))
  }, [])

  const query = q.trim().toLowerCase()

  const sectionIsMine = (s) => !s.modules?.length || s.modules.some(m => myModules.has(m))

  const sections = useMemo(() => {
    const all = content?.sections || []
    return all.filter(s => {
      if (s.admin_only && !isAdmin) return false
      if (onlyMine && !sectionIsMine(s)) return false
      return matches(s, query)
    })
  }, [content, isAdmin, onlyMine, query, myModules])

  const faq = useMemo(() => {
    const items = content?.faq || []
    if (!query) return items
    return items.filter(f =>
      (f.q + ' ' + f.a).toLowerCase().includes(query)
    )
  }, [content, query])

  const whatsNew = content?.whats_new || []
  const support = content?.support || {}

  // Scroll to the section named in the URL hash (from an ⓘ deep-link) once loaded.
  useEffect(() => {
    if (loading) return
    const id = location.hash.replace('#', '')
    if (!id) return
    const el = document.getElementById(id)
    if (el) requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [loading, location.hash, sections.length])

  function jump(id) {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    history.replaceState(null, '', `#${id}`)
  }

  function mailto(subject) {
    const addr = support.email || 'support@logcoretech.com'
    return `mailto:${addr}?subject=${encodeURIComponent(subject)}`
  }

  if (loading) {
    return <div className="max-w-3xl mx-auto p-8 text-center text-charcoal-400">Loading help…</div>
  }
  if (error) {
    return <div className="max-w-3xl mx-auto p-8 text-center text-red-500">{error}</div>
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Help &amp; Guide</h1>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-1">
          How every part of LogCore works. Stuck? Ask the AI in Chat — it reads this guide too.
        </p>
      </div>

      {/* Search + filter */}
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <input
          className="input flex-1"
          placeholder="Search help…"
          value={q}
          onChange={e => setQ(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm text-charcoal-600 dark:text-charcoal-300 shrink-0 cursor-pointer">
          <input type="checkbox" checked={onlyMine} onChange={e => setOnlyMine(e.target.checked)} />
          Only my modules
        </label>
      </div>

      {/* Jump nav */}
      {sections.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {sections.map(s => (
            <button
              key={s.id}
              onClick={() => jump(s.id)}
              className="badge hover:bg-orange-500/10 hover:text-orange-600 dark:hover:text-orange-400 transition-colors"
            >
              {s.icon} {s.title}
            </button>
          ))}
        </div>
      )}

      {sections.length === 0 && faq.length === 0 && (
        <p className="text-sm text-charcoal-400 text-center py-6">No help topics match “{q}”.</p>
      )}

      {/* Sections */}
      {sections.map(s => (
        <div key={s.id} id={s.id} className="card p-5 scroll-mt-20">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <span>{s.icon}</span> {s.title}
          </h2>
          {s.blurb && (
            <p className="text-sm text-charcoal-600 dark:text-charcoal-300 mt-1">{s.blurb}</p>
          )}
          {s.howto?.length > 0 && (
            <ol className="list-decimal list-inside space-y-1 text-sm mt-3 marker:text-orange-500">
              {s.howto.map((step, i) => <li key={i}>{step}</li>)}
            </ol>
          )}
          {s.tips?.length > 0 && (
            <div className="mt-3 space-y-1">
              {s.tips.map((tip, i) => (
                <p key={i} className="text-xs text-charcoal-500 dark:text-charcoal-400 flex gap-1.5">
                  <span aria-hidden>💡</span><span>{tip}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* What's New */}
      {!query && whatsNew.length > 0 && (
        <div id="whats-new" className="card p-5 scroll-mt-20">
          <h2 className="font-semibold text-lg">✨ What's New</h2>
          <div className="mt-3 space-y-4">
            {whatsNew.map(entry => (
              <div key={entry.version}>
                <div className="flex items-baseline gap-2">
                  <span className="font-medium">v{entry.version}</span>
                  {entry.date && (
                    <span className="text-xs text-charcoal-400">{entry.date}</span>
                  )}
                </div>
                <ul className="list-disc list-inside text-sm mt-1 space-y-0.5 marker:text-orange-500">
                  {(entry.highlights || []).map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* FAQ */}
      {faq.length > 0 && (
        <div id="faq" className="card p-5 scroll-mt-20">
          <h2 className="font-semibold text-lg mb-2">❓ Frequently Asked Questions</h2>
          <div className="divide-y divide-charcoal-200 dark:divide-charcoal-800">
            {faq.map((f, i) => (
              <div key={i} className="py-2">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full text-left flex items-center justify-between gap-2 text-sm font-medium"
                >
                  <span>{f.q}</span>
                  <span className="text-charcoal-400 shrink-0">{openFaq === i ? '−' : '+'}</span>
                </button>
                {openFaq === i && (
                  <p className="text-sm text-charcoal-600 dark:text-charcoal-300 mt-2">{f.a}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Contact & Support */}
      {!query && (
        <div id="support" className="card p-5 scroll-mt-20">
          <h2 className="font-semibold text-lg">✉️ Contact &amp; Support</h2>
          <p className="text-sm text-charcoal-600 dark:text-charcoal-300 mt-1">
            {support.note}
          </p>
          <p className="text-sm mt-2">
            Email{' '}
            <a className="text-orange-600 dark:text-orange-400 font-medium" href={mailto('LogCore Support')}>
              {support.email}
            </a>
          </p>
          <div className="flex flex-wrap gap-2 mt-3">
            <a className="btn-ghost text-sm" href={mailto('Bug Report')}>🐞 Report a bug</a>
            <a className="btn-ghost text-sm" href={mailto('Feature Request')}>💡 Request a feature</a>
            <a className="btn-ghost text-sm" href={mailto('Feedback')}>💬 Send feedback</a>
          </div>
        </div>
      )}
    </div>
  )
}
