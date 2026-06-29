import { useEffect, useState } from 'react'
import { journal as journalApi } from '../lib/api'

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
    } catch {}
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

  const displayDate = new Date(date + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Journal</h1>
        <button
          onClick={() => setShowHistory(h => !h)}
          className="btn-ghost text-sm"
        >
          {showHistory ? 'Hide History' : 'History'}
        </button>
      </div>

      {/* Entry history */}
      {showHistory && (
        <div className="card p-3 max-h-48 overflow-y-auto">
          {entries.length === 0 ? (
            <p className="text-sm text-charcoal-400 dark:text-charcoal-500 text-center py-2">No entries yet.</p>
          ) : (
            <div className="space-y-0.5">
              {entries.map(e => (
                <button
                  key={e.date}
                  onClick={() => { setDate(e.date); setShowHistory(false) }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-baseline gap-2 ${
                    e.date === date
                      ? 'bg-orange-500 text-white'
                      : 'hover:bg-charcoal-100 dark:hover:bg-charcoal-700'
                  }`}
                >
                  <span className="font-medium shrink-0">{e.date}</span>
                  {e.preview && (
                    <span className="text-xs opacity-60 truncate">{e.preview}</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Date navigator */}
      <div className="card p-3 flex items-center gap-2">
        <button onClick={() => goDate(-1)} className="btn-ghost px-3 py-1 text-sm shrink-0">‹</button>
        <div className="flex-1 text-center">
          <p className="font-medium text-sm">{displayDate}</p>
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

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {/* Editor */}
      <div className="flex flex-col" style={{ height: 'calc(100vh - 22rem)' }}>
        {loading ? (
          <div className="flex-1 card animate-pulse" />
        ) : (
          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder={`Write your entry for ${displayDate}…`}
            className="flex-1 font-mono text-sm p-4 rounded-xl border border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800 resize-none focus:outline-none focus:ring-2 focus:ring-orange-500 leading-relaxed"
          />
        )}
      </div>

      {/* Save */}
      <button
        onClick={save}
        disabled={saving || loading}
        className={`btn-primary w-full ${saved ? 'bg-green-500' : ''}`}
      >
        {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save Entry'}
      </button>
    </div>
  )
}
