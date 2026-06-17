import { useEffect, useState } from 'react'
import { brain as brainApi } from '../lib/api'

export default function Brain() {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)   // { path, content }
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    brainApi.list()
      .then(setFiles)
      .catch(() => setError('Could not load files.'))
      .finally(() => setLoading(false))
  }, [])

  async function openFile(path) {
    setError('')
    try {
      const data = await brainApi.getFile(path)
      setSelected(data)
      setEditContent(data.content)
    } catch {
      setError('Could not load file.')
    }
  }

  async function save() {
    setSaving(true)
    setError('')
    try {
      await brainApi.saveFile(selected.path, editContent)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e.message || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  // ── Editor view ──
  if (selected) {
    return (
      <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-6rem)]">
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={() => { setSelected(null); setError('') }}
            className="btn-ghost text-sm shrink-0"
          >
            ← Files
          </button>
          <span className="text-sm font-medium text-charcoal-600 dark:text-charcoal-300 truncate flex-1">
            {selected.path.split('/').pop().replace('.md', '')}
          </span>
          <button
            onClick={save}
            disabled={saving}
            className={`btn-primary text-sm px-4 shrink-0 ${saved ? 'bg-green-500' : ''}`}
          >
            {saving ? '…' : saved ? 'Saved ✓' : 'Save'}
          </button>
        </div>
        {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
        <textarea
          value={editContent}
          onChange={e => setEditContent(e.target.value)}
          spellCheck={false}
          className="flex-1 font-mono text-sm p-4 rounded-xl border border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800 resize-none focus:outline-none focus:ring-2 focus:ring-orange-500 leading-relaxed"
        />
      </div>
    )
  }

  // ── File list view ──
  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Brain</h1>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-0.5">
          Your personal AI context files. Changes here are read by the AI.
        </p>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-14 card animate-pulse" />)}
        </div>
      ) : files.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-3xl mb-2">🧠</p>
          <p>No brain files found. Complete the setup wizard first.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {files.map(f => {
            const label = f.name.replace('.md', '')
            const subpath = f.path.includes('/') ? f.path : null
            return (
              <button
                key={f.path}
                onClick={() => openFile(f.path)}
                className="card p-4 w-full text-left flex items-center gap-3 hover:border-orange-500/50 active:scale-[0.99] transition-all"
              >
                <span className="text-xl leading-none shrink-0">📄</span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm">{label}</p>
                  {subpath && (
                    <p className="text-xs text-charcoal-400 dark:text-charcoal-500 truncate">{f.path}</p>
                  )}
                </div>
                <span className="text-charcoal-300 dark:text-charcoal-600 shrink-0">›</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
