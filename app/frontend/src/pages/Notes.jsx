import { useEffect, useState } from 'react'
import { notes as notesApi } from '../lib/api'

export default function Notes() {
  const [notesList, setNotesList] = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)   // { name, content }
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)
  const [error, setError]         = useState('')
  const [showNew, setShowNew]     = useState(false)
  const [newName, setNewName]     = useState('')
  const [creating, setCreating]   = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(null)

  async function load() {
    setLoading(true)
    try {
      setNotesList(await notesApi.list())
    } catch {
      setError('Could not load notes.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function openNote(name) {
    setError('')
    try {
      const data = await notesApi.get(name)
      setSelected(data)
      setEditContent(data.content)
    } catch {
      setError('Could not load note.')
    }
  }

  async function save() {
    setSaving(true)
    setError('')
    try {
      await notesApi.update(selected.name, editContent)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e.message || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  async function createNote() {
    if (!newName.trim()) return
    setCreating(true)
    setError('')
    try {
      const note = await notesApi.create(newName.trim(), '')
      setShowNew(false)
      setNewName('')
      await load()
      setSelected(note)
      setEditContent('')
    } catch (e) {
      setError(e.message || 'Could not create note.')
    } finally {
      setCreating(false)
    }
  }

  async function deleteNote(name) {
    try {
      await notesApi.remove(name)
      setConfirmDelete(null)
      if (selected?.name === name) setSelected(null)
      load()
    } catch (e) {
      setError(e.message || 'Could not delete note.')
    }
  }

  // ── Editor view ──
  if (selected) {
    return (
      <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-6rem)]">
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={() => { setSelected(null); setError(''); load() }}
            className="btn-ghost text-sm shrink-0"
          >
            ← Notes
          </button>
          <span className="text-sm font-medium text-charcoal-600 dark:text-charcoal-300 truncate flex-1">
            {selected.name}
          </span>
          <button
            onClick={() => setConfirmDelete(selected.name)}
            className="text-charcoal-400 hover:text-red-500 p-1 text-sm shrink-0"
            title="Delete note"
          >
            ✕
          </button>
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
          placeholder="Start writing…"
          className="flex-1 font-mono text-sm p-4 rounded-xl border border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800 resize-none focus:outline-none focus:ring-2 focus:ring-orange-500 leading-relaxed"
        />

        {confirmDelete && (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
            <div className="card p-5 w-full max-w-xs">
              <h2 className="font-semibold mb-1">Delete Note?</h2>
              <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
                <strong>{confirmDelete}</strong> will be permanently deleted.
              </p>
              <div className="flex gap-2">
                <button onClick={() => setConfirmDelete(null)} className="btn-ghost flex-1">Cancel</button>
                <button
                  onClick={() => deleteNote(confirmDelete)}
                  className="flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Note list view ──
  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Notes</h1>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-0.5">
            Markdown notes stored in your Brain.
          </p>
        </div>
        <button onClick={() => { setShowNew(true); setError('') }} className="btn-primary">
          + New Note
        </button>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {showNew && (
        <div className="card p-4 space-y-3">
          <h2 className="font-medium text-sm">New Note</h2>
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && createNote()}
            placeholder="Note name"
            className="input w-full"
            autoFocus
          />
          <p className="text-xs text-charcoal-400 dark:text-charcoal-500">
            Letters, digits, spaces, hyphens, dots, underscores — max 100 characters.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => { setShowNew(false); setNewName(''); setError('') }}
              className="btn-ghost flex-1"
            >
              Cancel
            </button>
            <button
              onClick={createNote}
              disabled={creating || !newName.trim()}
              className="btn-primary flex-1"
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-14 card animate-pulse" />)}
        </div>
      ) : notesList.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-3xl mb-2">📝</p>
          <p className="font-medium mb-1">No notes yet</p>
          <p className="text-sm">Create your first note to get started.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {notesList.map(note => (
            <button
              key={note.name}
              onClick={() => openNote(note.name)}
              className="card p-4 w-full text-left flex items-center gap-3 hover:border-orange-500/50 active:scale-[0.99] transition-all"
            >
              <span className="text-xl leading-none shrink-0">📝</span>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm">{note.name}</p>
                <p className="text-xs text-charcoal-400 dark:text-charcoal-500">
                  {new Date(note.modified_at).toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric', year: 'numeric',
                  })}
                </p>
              </div>
              <span className="text-charcoal-300 dark:text-charcoal-600 shrink-0">›</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
