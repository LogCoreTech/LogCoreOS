import { useEffect, useState } from 'react'
import { useSearchParams, useLocation, useNavigate } from 'react-router-dom'
import { brain as brainApi } from '../lib/api'

export default function Brain() {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)   // { path, content }
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [openFolders, setOpenFolders] = useState(new Set())
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    brainApi.list()
      .then(setFiles)
      .catch(() => setError('Could not load files.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const file = searchParams.get('file')
    if (file) openFile(file)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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

  function toggleFolder(name) {
    setOpenFolders(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  // ── Editor view ──
  if (selected) {
    const fromChat = location.state?.from === '/chat'
    return (
      <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-6rem)]">
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={() => fromChat ? navigate('/chat') : (setSelected(null), setError(''))}
            className="btn-ghost text-sm shrink-0"
          >
            {fromChat ? '← Chat' : '← Files'}
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

  // Build grouped structure
  const rootFiles = files.filter(f => !f.path.includes('/'))
  const folderMap = {}
  files.filter(f => f.path.includes('/')).forEach(f => {
    const folder = f.path.split('/')[0]
    if (!folderMap[folder]) folderMap[folder] = []
    folderMap[folder].push(f)
  })

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
        <div className="space-y-1">
          {rootFiles.map(f => (
            <FileRow key={f.path} f={f} onOpen={openFile} />
          ))}

          {Object.entries(folderMap).map(([folder, items]) => (
            <div key={folder}>
              <button
                onClick={() => toggleFolder(folder)}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left text-sm font-medium text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-800 transition-colors"
              >
                <span className="text-xs text-charcoal-400 w-3 shrink-0">
                  {openFolders.has(folder) ? '▼' : '▶'}
                </span>
                <span className="text-base leading-none">📁</span>
                <span className="flex-1">{folder}</span>
                <span className="text-xs text-charcoal-400">{items.length}</span>
              </button>
              {openFolders.has(folder) && (
                <div className="ml-4 space-y-1 mt-1">
                  {items.map(f => (
                    <FileRow key={f.path} f={f} onOpen={openFile} sub />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FileRow({ f, onOpen, sub }) {
  const label = f.name.replace('.md', '')
  const subpath = sub ? f.path.split('/').slice(1).join('/').replace(/\.md$/, '') : null
  return (
    <button
      onClick={() => onOpen(f.path)}
      className="card p-4 w-full text-left flex items-center gap-3 hover:border-orange-500/50 active:scale-[0.99] transition-all"
    >
      <span className="text-xl leading-none shrink-0">📄</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm">{label}</p>
        {subpath && subpath !== label && (
          <p className="text-xs text-charcoal-400 dark:text-charcoal-500 truncate">{subpath}</p>
        )}
      </div>
      <span className="text-charcoal-300 dark:text-charcoal-600 shrink-0">›</span>
    </button>
  )
}
