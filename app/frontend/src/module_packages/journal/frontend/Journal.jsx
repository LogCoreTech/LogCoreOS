import { useEffect, useState } from 'react'
import HelpButton from '../../../components/HelpButton'
import { journal as journalApi } from './api'

function _todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Journal() {
  const today = _todayStr()
  const [date, setDate]         = useState(today)
  const [content, setContent]   = useState('')
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [saved, setSaved]       = useState(false)
  const [error, setError]       = useState('')
  const [entries, setEntries]   = useState([])
  const [showHistory, setShowHistory] = useState(false)

  async function loadEntry(d) {
    setLoading(true)
    setError('')
    try {
      const data = await journalApi.get(d)
      setContent(data.content || '')
    } catch {
      setError('Could not load entry.')
      setContent('')
    } finally {
      setLoading(false)
    }
  }

  async function loadHistory() {
    try {
      setEntries(await journalApi.list())
    } catch { /* history is a nice-to-have — a failed fetch just leaves the drawer empty */ }
  }

  useEffect(() => {
    loadEntry(date)
    loadHistory()
  }, [date])

  async function save() {
    setSaving(true)
    setError('')
    try {
      await journalApi.upsert(date, content)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      loadHistory()
    } catch (e) {
      setError(e.message || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  function goDate(delta) {
    const d = new Date(date + 'T12:00:00')
    d.setDate(d.getDate() + delta)
    setDate(d.toISOString().split('T')[0])
  }

  function jumpTo(d) {
    setDate(d)
    setShowHistory(false)
  }

  const displayDate = new Date(date + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })

  return (
    <div className="max-w-2xl mx-auto w-full flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <span className="flex items-center gap-2"><h1 className="text-2xl font-bold">Journal</h1><HelpButton section="journal" /></span>
        <button
          onClick={() => setShowHistory(true)}
          className="btn-ghost text-xs px-3 py-1.5"
          title="Browse past entries"
        >
          🗂 History
        </button>
      </div>

      {/* One seamless panel: date nav, editor, and save all share one border
          instead of stacking as separate cards with gaps between them. */}
      <div className="card flex-1 min-h-0 flex flex-col overflow-hidden p-0">
        {/* Date navigator */}
        <div className="flex items-center gap-2 p-3 border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
          <button onClick={() => goDate(-1)} className="btn-ghost px-3 py-1 text-sm shrink-0">‹</button>
          <div className="flex-1 text-center min-w-0">
            <p className="font-medium text-sm truncate">{displayDate}</p>
            {date !== today && (
              <button
                onClick={() => setDate(today)}
                className="text-xs text-orange-500 hover:underline"
              >
                Back to Today
              </button>
            )}
          </div>
          <button
            onClick={() => goDate(1)}
            disabled={date >= today}
            className="btn-ghost px-3 py-1 text-sm shrink-0 disabled:opacity-30"
          >
            ›
          </button>
          <input
            type="date"
            value={date}
            max={today}
            onChange={e => e.target.value && setDate(e.target.value)}
            className="text-xs text-charcoal-400 bg-transparent cursor-pointer shrink-0"
          />
        </div>

        {error && <p className="text-red-500 text-sm px-3 pt-2 shrink-0">{error}</p>}

        {/* Editor — this is the only thing that scrolls; the page itself doesn't.
            A <textarea> set directly as the flex-1 item doesn't reliably honor
            min-h-0 shrinking the way a plain div does (a well-known flexbox +
            form-control quirk), which let it force this panel — and the whole
            page — taller than the viewport. Wrapping it in a bounded div and
            having the textarea just fill that box at 100% sidesteps it. */}
        {loading ? (
          <div className="flex-1 min-h-0 animate-pulse bg-charcoal-50 dark:bg-charcoal-800" />
        ) : (
          <div className="flex-1 min-h-0 overflow-hidden">
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder={`Write your entry for ${displayDate}…`}
              // text-base (16px), not text-sm — see Notes.jsx's own textarea
              // for why (iOS Safari's auto-zoom-under-16px behavior).
              className="w-full h-full font-mono text-base p-4 bg-transparent resize-none focus:outline-none leading-relaxed overscroll-contain"
            />
          </div>
        )}

        {/* Save */}
        <div className="p-3 border-t border-charcoal-200 dark:border-charcoal-700 shrink-0">
          <button
            onClick={save}
            disabled={saving || loading}
            className={`btn-primary w-full ${saved ? 'bg-green-500' : ''}`}
          >
            {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save Entry'}
          </button>
        </div>
      </div>

      {/* Clears the fixed mobile footer nav so the panel bottom is never hidden behind it */}
      <div className="h-20 md:hidden shrink-0" aria-hidden="true" />

      {/* History drawer */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/40" onClick={() => setShowHistory(false)} />
          <div className="w-80 md:w-96 h-full bg-white dark:bg-charcoal-900 border-l border-charcoal-200 dark:border-charcoal-700 flex flex-col shadow-xl">
            <div className="flex items-center justify-between px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
              <h3 className="text-sm font-semibold">Journal History</h3>
              <button
                onClick={() => setShowHistory(false)}
                className="text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 text-lg leading-none"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto">
              {entries.length === 0 ? (
                <p className="text-sm text-charcoal-400 dark:text-charcoal-500 text-center py-10">No entries yet.</p>
              ) : (
                <div className="divide-y divide-charcoal-100 dark:divide-charcoal-800">
                  {entries.map(e => (
                    <button
                      key={e.date}
                      onClick={() => jumpTo(e.date)}
                      className={`w-full text-left px-4 py-3 transition-colors ${
                        e.date === date
                          ? 'bg-orange-500 text-white'
                          : 'hover:bg-charcoal-50 dark:hover:bg-charcoal-800'
                      }`}
                    >
                      <p className="text-sm font-medium">{e.date}</p>
                      {e.preview && (
                        <p className={`text-xs mt-0.5 truncate ${e.date === date ? 'opacity-80' : 'opacity-60'}`}>{e.preview}</p>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
