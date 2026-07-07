import { useState, useEffect } from 'react'
import { assets as assetsApi, tasks as tasksApi } from '../lib/api'
import TaskModal from './TaskModal'

// Field input for one template field definition — module-level per MEMORY.md rule.
function FieldInput({ def, value, onChange }) {
  if (def.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-sm py-2 cursor-pointer">
        <input
          type="checkbox"
          checked={value === true}
          onChange={e => onChange(e.target.checked)}
          className="accent-orange-500 w-4 h-4"
        />
        <span>{def.label}</span>
      </label>
    )
  }
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{def.label}</label>
      {def.type === 'select' ? (
        <select value={value ?? ''} onChange={e => onChange(e.target.value)} className="input">
          <option value="">—</option>
          {(def.options || []).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : def.type === 'number' ? (
        <input
          type="number"
          step="any"
          value={value ?? ''}
          onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          className="input"
        />
      ) : def.type === 'date' ? (
        <input type="date" value={value ?? ''} onChange={e => onChange(e.target.value)} className="input" />
      ) : (
        <input type="text" value={value ?? ''} onChange={e => onChange(e.target.value)} className="input" />
      )}
    </div>
  )
}

function AttachmentThumb({ assetId, file, canEdit, onDelete }) {
  const [url, setUrl] = useState(null)
  const isImage = file.mime.startsWith('image/')

  useEffect(() => {
    let objectUrl = null
    if (isImage) {
      assetsApi.fileBlob(assetId, file.id)
        .then(blob => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) })
        .catch(() => {})
    }
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [assetId, file.id])

  async function open() {
    try {
      const blob = await assetsApi.fileBlob(assetId, file.id)
      const u = URL.createObjectURL(blob)
      window.open(u, '_blank')
      setTimeout(() => URL.revokeObjectURL(u), 60000)
    } catch { /* ignore */ }
  }

  return (
    <div className="relative group border border-charcoal-200 dark:border-charcoal-700 rounded-lg overflow-hidden">
      <button type="button" onClick={open} className="block w-full" title={file.filename}>
        {isImage && url ? (
          <img src={url} alt={file.filename} className="w-full h-20 object-cover" />
        ) : (
          <div className="w-full h-20 flex flex-col items-center justify-center text-charcoal-500 dark:text-charcoal-400">
            <span className="text-xl">📄</span>
            <span className="text-[10px] px-1 truncate max-w-full">{file.filename}</span>
          </div>
        )}
      </button>
      {canEdit && (
        <button
          type="button"
          onClick={() => onDelete(file)}
          className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
          title="Delete file"
        >
          ✕
        </button>
      )}
    </div>
  )
}

export default function AssetModal({ asset, templates, allAssets, defaultParentId, user, workspace, onClose, onSaved }) {
  const editing = !!asset
  const isAdmin = user?.role === 'admin'
  const isForeign = editing && !!asset._owner
  const isPool = editing && (asset._owner === 'team' || asset._owner === 'household')
  const readOnly = isForeign && asset._access !== 'edit'
  const canManage = editing ? (!isForeign || (isPool && asset._access === 'edit')) : true
  const poolLabel = asset?._owner === 'team' ? 'Team' : 'Household'

  const poolName = workspace === 'business' ? 'team' : 'household'
  const canCreateInPool = isAdmin || (user?.poolEdit || []).includes(poolName)

  const [form, setForm] = useState({
    template: asset?.template || templates[0]?.key || '',
    name: asset?.name || '',
    parent_id: asset?.parent_id || defaultParentId || '',
    fields: { ...(asset?.fields || {}) },
    notes: asset?.notes || '',
    owner: 'me',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [linkedTasks, setLinkedTasks] = useState([])
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [access, setAccess] = useState({
    shared_with: asset?.shared_with || [],
    hidden_from: asset?.hidden_from || [],
  })
  const [attachments, setAttachments] = useState(asset?.attachments || [])
  const [uploading, setUploading] = useState(false)

  const template = templates.find(t => t.key === form.template)
  const knownKeys = new Set((template?.fields || []).map(f => f.key))
  const orphanedKeys = Object.keys(form.fields).filter(k => !knownKeys.has(k))

  // Prefill defaults when the template changes on a NEW asset
  useEffect(() => {
    if (editing) return
    const defaults = {}
    for (const f of template?.fields || []) {
      if (f.default !== undefined) defaults[f.key] = f.default
    }
    setForm(f => ({ ...f, fields: defaults }))
  }, [form.template])

  useEffect(() => {
    if (!editing) return
    tasksApi.list()
      .then(all => setLinkedTasks((all || []).filter(t => t.asset_id === asset.id)))
      .catch(() => {})
  }, [])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function setFieldValue(key, value) {
    setForm(f => ({ ...f, fields: { ...f.fields, [key]: value } }))
  }

  // Parent options: same-store assets only, excluding self and own descendants
  const parentOptions = (() => {
    if (isForeign) return []
    const pool = allAssets.filter(a =>
      editing ? sameStore(a, asset) : form.owner === 'pool' ? a._owner === poolName : !a._owner
    )
    if (!editing) return pool
    const blocked = new Set([asset.id])
    let grew = true
    while (grew) {
      grew = false
      for (const a of pool) {
        if (a.parent_id && blocked.has(a.parent_id) && !blocked.has(a.id)) {
          blocked.add(a.id)
          grew = true
        }
      }
    }
    return pool.filter(a => !blocked.has(a.id))
  })()

  function sameStore(a, b) {
    return (a._owner || '') === (b._owner || '')
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required'); return }
    if (!editing && !form.template) { setError('Pick a template first'); return }
    setLoading(true)
    setError('')
    try {
      const fields = {}
      for (const [k, v] of Object.entries(form.fields)) {
        fields[k] = v === '' ? null : v
      }
      if (editing) {
        const payload = { name: form.name, fields, notes: form.notes || null }
        if (!isForeign) payload.parent_id = form.parent_id || null
        await assetsApi.update(asset.id, payload)
      } else {
        await assetsApi.create({
          template: form.template,
          name: form.name,
          parent_id: form.parent_id || null,
          fields,
          notes: form.notes || null,
          owner: form.owner,
        })
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function saveAccess() {
    setLoading(true)
    setError('')
    try {
      const payload = isPool
        ? { hidden_from: access.hidden_from }
        : { shared_with: access.shared_with, hidden_from: access.hidden_from }
      await assetsApi.updateAccess(asset.id, payload)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleArchive() {
    setLoading(true)
    try {
      if (asset.archived) await assetsApi.unarchive(asset.id)
      else await assetsApi.archive(asset.id)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete() {
    if (!confirm(`Permanently delete "${asset.name}"? This cannot be undone.`)) return
    setLoading(true)
    try {
      await assetsApi.remove(asset.id)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleConvert() {
    if (!confirm(`Make "${asset.name}" and everything inside it a shared ${workspace === 'business' ? 'Team' : 'Household'} object? It will no longer belong to your personal store.`)) return
    setLoading(true)
    try {
      await assetsApi.convertToPool(asset.id)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const att = await assetsApi.uploadFile(asset.id, file)
      setAttachments(prev => [...prev, att])
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleFileDelete(file) {
    try {
      await assetsApi.removeFile(asset.id, file.id)
      setAttachments(prev => prev.filter(f => f.id !== file.id))
    } catch (err) {
      setError(err.message)
    }
  }

  const shareTargets = access.shared_with

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-end md:items-center justify-center p-4">
      <div className="card p-5 w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">
            {readOnly ? 'View Asset' : editing ? 'Edit Asset' : 'New Asset'}
            {isForeign && (
              <span className="ml-2 text-xs font-normal text-charcoal-400">
                {isPool ? poolLabel : `shared by ${asset._owner}`}
              </span>
            )}
          </h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <fieldset disabled={readOnly} className="space-y-4 border-0 p-0 m-0 min-w-0 disabled:opacity-70">

            {/* Template picker — create only; immutable afterwards */}
            {!editing ? (
              <div>
                <label className="block text-sm font-medium mb-1">Template</label>
                <div className="flex gap-1 flex-wrap">
                  {templates.map(t => (
                    <button
                      key={t.key}
                      type="button"
                      onClick={() => set('template', t.key)}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                        form.template === t.key
                          ? 'bg-orange-500 text-white'
                          : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                      }`}
                    >
                      {t.icon ? `${t.icon} ` : ''}{t.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-charcoal-400">
                Template: {template ? `${template.icon ? `${template.icon} ` : ''}${template.label}` : asset.template}
              </p>
            )}

            {/* Owner — create only, for admins / pool managers */}
            {!editing && canCreateInPool && (
              <div>
                <label className="block text-sm font-medium mb-1">Owner</label>
                <div className="flex gap-1">
                  {[
                    { id: 'me', label: 'Me' },
                    { id: 'pool', label: workspace === 'business' ? '🧑‍🤝‍🧑 Team' : '🏠 Household' },
                  ].map(o => (
                    <button
                      key={o.id}
                      type="button"
                      onClick={() => { set('owner', o.id); set('parent_id', '') }}
                      className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors ${
                        form.owner === o.id
                          ? 'bg-orange-500 text-white'
                          : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                      }`}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Name */}
            <div>
              <label className="block text-sm font-medium mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={e => set('name', e.target.value)}
                placeholder="e.g. Parcel 3"
                autoFocus={!editing}
                className="input"
              />
            </div>

            {/* Parent — own assets only */}
            {!isForeign && parentOptions.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-1">
                  Inside <span className="text-charcoal-400 font-normal">(optional)</span>
                </label>
                <select value={form.parent_id} onChange={e => set('parent_id', e.target.value)} className="input">
                  <option value="">— top level —</option>
                  {parentOptions.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
            )}

            {/* Template fields, in template order */}
            {(template?.fields || []).map(def => (
              <FieldInput
                key={def.key}
                def={def}
                value={form.fields[def.key]}
                onChange={v => setFieldValue(def.key, v)}
              />
            ))}

            {/* Orphaned values from removed template fields */}
            {editing && orphanedKeys.length > 0 && (
              <div className="text-xs text-charcoal-400 space-y-1">
                {orphanedKeys.map(k => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="truncate">{k}: {String(form.fields[k])}</span>
                    <button type="button" onClick={() => setFieldValue(k, null)} className="text-red-400 hover:text-red-500" title="Remove leftover value">✕</button>
                  </div>
                ))}
              </div>
            )}

            {/* Notes */}
            <div>
              <label className="block text-sm font-medium mb-1">
                Notes <span className="text-charcoal-400 font-normal">(optional)</span>
              </label>
              <textarea
                value={form.notes || ''}
                onChange={e => set('notes', e.target.value)}
                rows={2}
                className="input resize-none"
              />
            </div>
          </fieldset>

          {/* Attachments — edit mode only (needs an asset id) */}
          {editing && (
            <div>
              <label className="block text-sm font-medium mb-1">Files</label>
              {attachments.length > 0 && (
                <div className="grid grid-cols-3 gap-2 mb-2">
                  {attachments.map(f => (
                    <AttachmentThumb
                      key={f.id}
                      assetId={asset.id}
                      file={f}
                      canEdit={!readOnly}
                      onDelete={handleFileDelete}
                    />
                  ))}
                </div>
              )}
              {!readOnly && (
                <label className="btn-ghost text-xs px-3 py-1.5 inline-block cursor-pointer">
                  {uploading ? 'Uploading…' : '＋ Add photo / PDF'}
                  <input type="file" accept="image/jpeg,image/png,image/webp,image/avif,application/pdf" onChange={handleUpload} className="hidden" disabled={uploading} />
                </label>
              )}
            </div>
          )}

          {/* Linked tasks */}
          {editing && (
            <div>
              <label className="block text-sm font-medium mb-1">Linked tasks</label>
              {linkedTasks.length > 0 ? (
                <ul className="text-sm space-y-1 mb-2">
                  {linkedTasks.map(t => (
                    <li key={t.id} className="flex items-center gap-2">
                      <span className={t.status === 'done' ? 'line-through text-charcoal-400' : ''}>{t.title}</span>
                      {t.due_date && <span className="text-xs text-charcoal-400">{t.due_date}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-charcoal-400 mb-2">No tasks linked yet.</p>
              )}
              <button type="button" onClick={() => setShowTaskModal(true)} className="btn-ghost text-xs px-3 py-1.5">
                ＋ Task for this asset
              </button>
            </div>
          )}

          {/* Access — owner (shares + hide) or pool manager (hide only) */}
          {editing && canManage && !readOnly && (
            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-2">
              <label className="block text-sm font-medium">Access</label>
              {!isPool && (
                <div className="space-y-1">
                  {shareTargets.map((s, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <input
                        type="text"
                        value={s.target}
                        onChange={e => setAccess(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, target: e.target.value } : x) }))}
                        placeholder={workspace === 'business' ? 'team or user name' : 'household or user name'}
                        className="input !py-1 flex-1"
                      />
                      <select
                        value={s.access}
                        onChange={e => setAccess(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, access: e.target.value } : x) }))}
                        className="input !py-1 !w-20"
                      >
                        <option value="read">read</option>
                        <option value="edit">edit</option>
                      </select>
                      <button type="button" onClick={() => setAccess(a => ({ ...a, shared_with: a.shared_with.filter((_, j) => j !== i) }))} className="text-red-400 hover:text-red-500">✕</button>
                    </div>
                  ))}
                  <button type="button" onClick={() => setAccess(a => ({ ...a, shared_with: [...a.shared_with, { target: '', access: 'read' }] }))} className="btn-ghost text-xs px-2 py-1">
                    ＋ Share with…
                  </button>
                </div>
              )}
              <div>
                <input
                  type="text"
                  value={(access.hidden_from || []).join(', ')}
                  onChange={e => setAccess(a => ({ ...a, hidden_from: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
                  placeholder="Hide from (user names, comma-separated)"
                  className="input !py-1"
                />
              </div>
              <button type="button" onClick={saveAccess} disabled={loading} className="btn-ghost text-xs px-3 py-1.5">
                Save access
              </button>
            </div>
          )}

          {/* History */}
          {editing && (asset.history || []).length > 0 && (
            <div className="text-xs">
              <button type="button" onClick={() => setShowHistory(h => !h)} className="text-charcoal-400 hover:text-orange-500 transition-colors">
                {showHistory ? '▾' : '▸'} History ({asset.history.length})
              </button>
              {showHistory && (
                <div className="mt-1 pl-3 border-l-2 border-charcoal-200 dark:border-charcoal-700 space-y-1 max-h-40 overflow-y-auto">
                  {[...asset.history].reverse().map((h, i) => (
                    <div key={i} className="text-charcoal-500 dark:text-charcoal-400">
                      <span className="font-medium">{h.by || 'system'}</span> {h.action}
                      {Object.keys(h.changes || {}).length > 0 && (
                        <span className="opacity-75"> — {Object.entries(h.changes).map(([k, [o, n]]) => `${k.replace('fields.', '')}: ${o ?? '∅'}→${n ?? '∅'}`).join(', ')}</span>
                      )}
                      <span className="opacity-50 ml-1">{(h.at || '').slice(0, 10)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <div className="flex flex-wrap gap-2 pt-1">
            {readOnly ? (
              <button type="button" onClick={onClose} className="btn-ghost flex-1">Close</button>
            ) : (
              <>
                {editing && isAdmin && (
                  <button type="button" onClick={handleDelete} disabled={loading}
                    className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                    Delete
                  </button>
                )}
                {editing && canManage && (
                  <button type="button" onClick={handleArchive} disabled={loading} className="btn-ghost px-3">
                    {asset.archived ? 'Unarchive' : 'Archive'}
                  </button>
                )}
                {editing && isAdmin && !isPool && (
                  <button type="button" onClick={handleConvert} disabled={loading} className="btn-ghost px-3" title="Move into the shared pool so it survives account changes">
                    → {workspace === 'business' ? 'Team' : 'Household'}
                  </button>
                )}
                <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={loading} className="btn-primary flex-1">
                  {loading ? 'Saving…' : editing ? 'Save' : 'Create'}
                </button>
              </>
            )}
          </div>
        </form>

        {showTaskModal && (
          <TaskModal
            defaultAssetId={asset.id}
            assets={[asset]}
            onClose={() => setShowTaskModal(false)}
            onSave={() => {
              setShowTaskModal(false)
              tasksApi.list().then(all => setLinkedTasks((all || []).filter(t => t.asset_id === asset.id))).catch(() => {})
            }}
          />
        )}
      </div>
    </div>
  )
}
