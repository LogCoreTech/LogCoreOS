import { useEffect, useState, useCallback, useRef } from 'react'
import { notes as notesApi } from '../lib/api'

// ── Tree builder ─────────────────────────────────────────────────────────────

function buildTree(items) {
  const byPath = {}
  items.forEach(item => { byPath[item.path] = { ...item, children: [] } })
  const root = []
  items.forEach(item => {
    const slash = item.path.lastIndexOf('/')
    if (slash === -1) {
      root.push(byPath[item.path])
    } else {
      const parentPath = item.path.slice(0, slash)
      byPath[parentPath]?.children.push(byPath[item.path])
    }
  })
  return root
}

function parentOf(path) {
  const slash = path.lastIndexOf('/')
  return slash === -1 ? '' : path.slice(0, slash)
}

function allFolderPaths(items) {
  return items.filter(i => i.type === 'folder').map(i => i.path)
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TreeNode({ node, depth, selectedPath, openFolders, onSelectNote, onToggleFolder, onAction }) {
  const isOpen = openFolders.has(node.path)
  const isSelected = selectedPath === node.path
  const indent = depth * 16

  if (node.type === 'folder') {
    return (
      <div>
        <div
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer group transition-colors ${
            isSelected
              ? 'bg-orange-500/10 text-orange-600 dark:text-orange-400'
              : 'hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
          }`}
          style={{ paddingLeft: `${8 + indent}px` }}
          onClick={() => onToggleFolder(node.path)}
        >
          <span className="text-charcoal-400 dark:text-charcoal-500 text-xs w-3 shrink-0">
            {isOpen ? '▼' : '▶'}
          </span>
          <span className="text-base leading-none shrink-0">{isOpen ? '📂' : '📁'}</span>
          <span className="flex-1 text-sm font-medium truncate">{node.name}</span>
          <button
            onClick={e => { e.stopPropagation(); onAction('folderMenu', node) }}
            className="opacity-0 group-hover:opacity-100 text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 px-1 text-xs shrink-0 transition-opacity"
            title="Folder options"
          >
            ···
          </button>
        </div>
        {isOpen && node.children?.map(child => (
          <TreeNode
            key={child.path}
            node={child}
            depth={depth + 1}
            selectedPath={selectedPath}
            openFolders={openFolders}
            onSelectNote={onSelectNote}
            onToggleFolder={onToggleFolder}
            onAction={onAction}
          />
        ))}
      </div>
    )
  }

  return (
    <div
      className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer group transition-colors ${
        isSelected
          ? 'bg-orange-500/15 border border-orange-500/30 text-orange-700 dark:text-orange-300'
          : 'hover:bg-charcoal-100 dark:hover:bg-charcoal-800'
      }`}
      style={{ paddingLeft: `${8 + indent}px` }}
      onClick={() => onSelectNote(node.path)}
    >
      <span className="text-base leading-none shrink-0">📝</span>
      <span className="flex-1 text-sm truncate">{node.name}</span>
      <button
        onClick={e => { e.stopPropagation(); onAction('noteMenu', node) }}
        className="opacity-0 group-hover:opacity-100 text-charcoal-400 hover:text-charcoal-600 dark:hover:text-charcoal-200 px-1 text-xs shrink-0 transition-opacity"
        title="Note options"
      >
        ···
      </button>
    </div>
  )
}

// ── Context menu ──────────────────────────────────────────────────────────────

function ContextMenu({ node, folders, onClose, onRename, onMove, onDelete }) {
  if (node.type === 'folder') {
    return (
      <div className="card p-1 w-44 shadow-lg z-50">
        <button onClick={() => { onClose(); onRename(node) }} className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-700">
          Rename folder
        </button>
        <button onClick={() => { onClose(); onDelete(node) }} className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400">
          Delete folder…
        </button>
      </div>
    )
  }
  return (
    <div className="card p-1 w-44 shadow-lg z-50">
      <button onClick={() => { onClose(); onRename(node) }} className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-700">
        Rename note
      </button>
      <button onClick={() => { onClose(); onMove(node) }} className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-charcoal-100 dark:hover:bg-charcoal-700">
        Move to folder
      </button>
      <button onClick={() => { onClose(); onDelete(node) }} className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400">
        Delete note…
      </button>
    </div>
  )
}

// ── Modal shell ───────────────────────────────────────────────────────────────

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <h2 className="font-semibold mb-3">{title}</h2>
        {children}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Notes() {
  const [items, setItems]           = useState([])
  const [tree, setTree]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [openFolders, setOpenFolders] = useState(new Set())
  const [selectedPath, setSelectedPath] = useState(null)
  const [note, setNote]             = useState(null)   // {path, name, content, modified_at}
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving]         = useState(false)
  const [saved, setSaved]           = useState(false)
  const [error, setError]           = useState('')
  const [contextMenu, setContextMenu] = useState(null)  // {node, x, y}
  const [modal, setModal]           = useState(null)    // {type, item?}
  const [modalInput, setModalInput] = useState('')
  const [modalTarget, setModalTarget] = useState('')
  const [modalBusy, setModalBusy]   = useState(false)
  const [showSidebar, setShowSidebar] = useState(true)
  const autoSaveTimer = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await notesApi.list()
      setItems(data)
      setTree(buildTree(data))
    } catch {
      setError('Could not load notes.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-save 1.5 s after the user stops typing
  useEffect(() => {
    if (!note) return
    clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => { save() }, 1500)
    return () => clearTimeout(autoSaveTimer.current)
  }, [editContent]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return
    const close = () => setContextMenu(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [contextMenu])

  async function openNote(path) {
    setError('')
    try {
      const data = await notesApi.get(path)
      setNote(data)
      setEditContent(data.content)
      setSelectedPath(path)
      setShowSidebar(false)
    } catch {
      setError('Could not load note.')
    }
  }

  async function save() {
    if (!note) return
    setSaving(true)
    setError('')
    try {
      await notesApi.update(note.path, editContent)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e.message || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  function toggleFolder(path) {
    setOpenFolders(prev => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
    setSelectedPath(prev => prev === path ? null : path)
  }

  function handleAction(type, node) {
    if (type === 'folderMenu') openContextMenu(node)
    if (type === 'noteMenu') openContextMenu(node)
  }

  function openContextMenu(node) {
    setContextMenu({ node })
  }

  // ── New note ────────────────────────────────────────────────────────────────

  async function handleCreateNote() {
    const name = modalInput.trim()
    if (!name) return
    const parent = selectedPath && items.find(i => i.path === selectedPath && i.type === 'folder')
      ? selectedPath
      : (selectedPath ? parentOf(selectedPath) : '')
    const path = parent ? `${parent}/${name}` : name
    setModalBusy(true)
    setError('')
    try {
      await notesApi.create(path, '')
      await load()
      setModal(null)
      if (parent) {
        setOpenFolders(prev => new Set([...prev, parent]))
      }
      openNote(path)
    } catch (e) {
      setError(e.message || 'Could not create note.')
      setModalBusy(false)
    }
  }

  // ── New folder ──────────────────────────────────────────────────────────────

  async function handleCreateFolder() {
    const name = modalInput.trim()
    if (!name) return
    const parent = selectedPath && items.find(i => i.path === selectedPath && i.type === 'folder')
      ? selectedPath
      : (selectedPath ? parentOf(selectedPath) : '')
    const path = parent ? `${parent}/${name}` : name
    setModalBusy(true)
    setError('')
    try {
      await notesApi.createFolder(path)
      await load()
      setModal(null)
      setOpenFolders(prev => new Set([...prev, path]))
      if (parent) setOpenFolders(prev => new Set([...prev, parent]))
    } catch (e) {
      setError(e.message || 'Could not create folder.')
      setModalBusy(false)
    }
  }

  // ── Rename ──────────────────────────────────────────────────────────────────

  async function handleRename() {
    const newName = modalInput.trim()
    if (!newName || !modal?.item) return
    const item = modal.item
    const parent = parentOf(item.path)
    const toPath = parent ? `${parent}/${newName}` : newName
    setModalBusy(true)
    setError('')
    try {
      await notesApi.move(item.path, toPath, item.type)
      if (note?.path === item.path) {
        setNote(prev => ({ ...prev, path: toPath, name: newName }))
        setSelectedPath(toPath)
      }
      await load()
      setModal(null)
    } catch (e) {
      setError(e.message || 'Could not rename.')
      setModalBusy(false)
    }
  }

  // ── Move note ───────────────────────────────────────────────────────────────

  async function handleMove() {
    if (!modal?.item) return
    const item = modal.item
    const targetFolder = modalTarget
    const toPath = targetFolder ? `${targetFolder}/${item.name}` : item.name
    setModalBusy(true)
    setError('')
    try {
      await notesApi.move(item.path, toPath, 'note')
      if (note?.path === item.path) {
        setNote(prev => ({ ...prev, path: toPath }))
        setSelectedPath(toPath)
      }
      await load()
      setModal(null)
    } catch (e) {
      setError(e.message || 'Could not move note.')
      setModalBusy(false)
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────

  async function handleDelete() {
    if (!modal?.item) return
    const item = modal.item
    setModalBusy(true)
    setError('')
    try {
      if (item.type === 'note') {
        await notesApi.remove(item.path)
        if (note?.path === item.path) { setNote(null); setSelectedPath(null) }
      } else {
        await notesApi.removeFolder(item.path)
        if (note?.path.startsWith(item.path + '/') || note?.path === item.path) {
          setNote(null); setSelectedPath(null)
        }
      }
      await load()
      setModal(null)
    } catch (e) {
      setError(e.message || 'Could not delete.')
      setModalBusy(false)
    }
  }

  function openModal(type, item = null) {
    setModalInput(type === 'rename' ? item?.name || '' : '')
    setModalTarget('')
    setModalBusy(false)
    setModal({ type, item })
  }

  const folders = allFolderPaths(items)

  // ── Sidebar ──────────────────────────────────────────────────────────────────

  const sidebar = (
    <div className="flex flex-col h-full">
      {/* Sidebar header */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
        <span className="font-semibold text-sm flex-1">Notes</span>
        <button
          onClick={() => { setModalInput(''); openModal('newNote') }}
          className="text-xs px-2 py-1 rounded-md bg-orange-500 hover:bg-orange-600 text-white font-medium transition-colors"
          title="New note"
        >
          + Note
        </button>
        <button
          onClick={() => { setModalInput(''); openModal('newFolder') }}
          className="text-xs px-2 py-1 rounded-md border border-charcoal-300 dark:border-charcoal-600 hover:bg-charcoal-100 dark:hover:bg-charcoal-700 transition-colors"
          title="New folder"
        >
          + Folder
        </button>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {loading ? (
          <div className="space-y-1 px-2">
            {[1,2,3].map(i => <div key={i} className="h-8 rounded-lg bg-charcoal-100 dark:bg-charcoal-800 animate-pulse" />)}
          </div>
        ) : tree.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-charcoal-400 dark:text-charcoal-500">
            <p className="text-2xl mb-2">📝</p>
            <p>No notes yet.</p>
            <p className="text-xs mt-1">Click + Note to create one.</p>
          </div>
        ) : (
          tree.map(node => (
            <TreeNode
              key={node.path}
              node={node}
              depth={0}
              selectedPath={selectedPath}
              openFolders={openFolders}
              onSelectNote={path => { openNote(path); setShowSidebar(false) }}
              onToggleFolder={toggleFolder}
              onAction={(type, n) => {
                setContextMenu({ node: n })
              }}
            />
          ))
        )}
      </div>

      {/* Context menu (inline below sidebar, not absolute positioned) */}
      {contextMenu && (
        <div className="border-t border-charcoal-200 dark:border-charcoal-700 p-2">
          <ContextMenu
            node={contextMenu.node}
            folders={folders}
            onClose={() => setContextMenu(null)}
            onRename={node => openModal('rename', node)}
            onMove={node => openModal('move', node)}
            onDelete={node => openModal(node.type === 'folder' ? 'deleteFolder' : 'deleteNote', node)}
          />
        </div>
      )}
    </div>
  )

  // ── Editor ────────────────────────────────────────────────────────────────

  const editor = note ? (
    <div className="flex flex-col h-full min-w-0">
      {/* Editor toolbar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-charcoal-200 dark:border-charcoal-700 shrink-0">
        <button
          onClick={() => { setShowSidebar(true); if (window.innerWidth < 768) setNote(null) }}
          className="text-sm text-charcoal-500 hover:text-charcoal-800 dark:hover:text-charcoal-200 shrink-0 md:hidden"
        >
          ← Back
        </button>
        <p className="flex-1 text-xs text-charcoal-400 dark:text-charcoal-500 truncate font-mono min-w-0">
          {note.path}
        </p>
        <span className="text-xs text-charcoal-400 dark:text-charcoal-500 shrink-0">
          {saving ? 'Saving…' : saved ? 'Saved ✓' : ''}
        </span>
      </div>

      {error && <p className="text-red-500 text-sm px-4 py-2">{error}</p>}

      <textarea
        value={editContent}
        onChange={e => setEditContent(e.target.value)}
        spellCheck={false}
        placeholder="Start writing…"
        className="flex-1 w-full font-mono text-sm p-4 bg-white dark:bg-charcoal-900 resize-none focus:outline-none leading-relaxed overflow-x-hidden"
      />
    </div>
  ) : (
    <div className="flex-1 flex items-center justify-center text-charcoal-400 dark:text-charcoal-500">
      <div className="text-center">
        <p className="text-4xl mb-3">📝</p>
        <p className="font-medium">Select a note to edit</p>
        <p className="text-sm mt-1">or create a new one in the sidebar.</p>
      </div>
    </div>
  )

  return (
    <div className="h-[calc(100vh-8rem)] md:h-[calc(100vh-3rem)] flex overflow-hidden -mx-4 -mt-4 md:-mx-6 md:-mt-6">
      {/* Sidebar */}
      <div className={`
        ${showSidebar ? 'flex' : 'hidden'} md:flex
        flex-col w-full md:w-64 lg:w-72 shrink-0
        border-r border-charcoal-200 dark:border-charcoal-700
        bg-charcoal-50 dark:bg-charcoal-900
      `}>
        {sidebar}
      </div>

      {/* Editor panel */}
      <div className={`
        ${showSidebar ? 'hidden' : 'flex'} md:flex
        flex-col flex-1 min-w-0
        bg-white dark:bg-charcoal-900
      `}>
        {editor}
      </div>

      {/* Modals */}
      {modal?.type === 'newNote' && (
        <Modal title="New Note" onClose={() => setModal(null)}>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-2">
            {selectedPath && items.find(i => i.path === selectedPath && i.type === 'folder')
              ? `Will be created inside: ${selectedPath}`
              : 'Will be created at the top level.'}
          </p>
          <input
            autoFocus
            className="input w-full mb-3"
            placeholder="Note name"
            value={modalInput}
            onChange={e => setModalInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreateNote()}
          />
          {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => { setModal(null); setError('') }} className="btn-ghost flex-1">Cancel</button>
            <button onClick={handleCreateNote} disabled={modalBusy || !modalInput.trim()} className="btn-primary flex-1">
              {modalBusy ? 'Creating…' : 'Create'}
            </button>
          </div>
        </Modal>
      )}

      {modal?.type === 'newFolder' && (
        <Modal title="New Folder" onClose={() => setModal(null)}>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-2">
            {selectedPath && items.find(i => i.path === selectedPath && i.type === 'folder')
              ? `Will be created inside: ${selectedPath}`
              : 'Will be created at the top level.'}
          </p>
          <input
            autoFocus
            className="input w-full mb-3"
            placeholder="Folder name"
            value={modalInput}
            onChange={e => setModalInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreateFolder()}
          />
          {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => { setModal(null); setError('') }} className="btn-ghost flex-1">Cancel</button>
            <button onClick={handleCreateFolder} disabled={modalBusy || !modalInput.trim()} className="btn-primary flex-1">
              {modalBusy ? 'Creating…' : 'Create'}
            </button>
          </div>
        </Modal>
      )}

      {modal?.type === 'rename' && (
        <Modal title={`Rename ${modal.item?.type === 'folder' ? 'Folder' : 'Note'}`} onClose={() => setModal(null)}>
          <input
            autoFocus
            className="input w-full mb-3"
            value={modalInput}
            onChange={e => setModalInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleRename()}
          />
          {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => { setModal(null); setError('') }} className="btn-ghost flex-1">Cancel</button>
            <button onClick={handleRename} disabled={modalBusy || !modalInput.trim()} className="btn-primary flex-1">
              {modalBusy ? 'Renaming…' : 'Rename'}
            </button>
          </div>
        </Modal>
      )}

      {modal?.type === 'move' && (
        <Modal title="Move Note" onClose={() => setModal(null)}>
          <p className="text-sm text-charcoal-600 dark:text-charcoal-300 mb-2">
            Move <strong>{modal.item?.name}</strong> to:
          </p>
          <select
            className="input w-full mb-3"
            value={modalTarget}
            onChange={e => setModalTarget(e.target.value)}
          >
            <option value="">(Root — no folder)</option>
            {folders
              .filter(f => f !== parentOf(modal.item?.path || ''))
              .map(f => <option key={f} value={f}>{f}</option>)
            }
          </select>
          {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => { setModal(null); setError('') }} className="btn-ghost flex-1">Cancel</button>
            <button onClick={handleMove} disabled={modalBusy} className="btn-primary flex-1">
              {modalBusy ? 'Moving…' : 'Move'}
            </button>
          </div>
        </Modal>
      )}

      {modal?.type === 'deleteNote' && (
        <Modal title="Delete Note?" onClose={() => setModal(null)}>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
            <strong>{modal.item?.path}</strong> will be permanently deleted.
          </p>
          {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => { setModal(null); setError('') }} className="btn-ghost flex-1">Cancel</button>
            <button onClick={handleDelete} disabled={modalBusy} className="flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors">
              {modalBusy ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </Modal>
      )}

      {modal?.type === 'deleteFolder' && (
        <Modal title="Delete Folder?" onClose={() => setModal(null)}>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
            <strong>{modal.item?.path}</strong> and all its contents will be permanently deleted.
          </p>
          {error && <p className="text-red-500 text-sm mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => { setModal(null); setError('') }} className="btn-ghost flex-1">Cancel</button>
            <button onClick={handleDelete} disabled={modalBusy} className="flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors">
              {modalBusy ? 'Deleting…' : 'Delete Folder'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
