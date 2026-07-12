import { useState, useEffect } from 'react'
import { assets as assetsApi, tasks as tasksApi } from '../lib/api'
import TaskModal from './TaskModal'
import TagInput from './TagInput'
import AssetTreePicker from './AssetTreePicker'
import AssetView from './AssetView'
import { AttachmentThumb, formatChanges, FieldInput, CapsSelector } from './assetDisplay'

export default function AssetModal({ asset: initialAsset, templates, allAssets: allAssetsProp, defaultParentId, user, workspace, onClose, onSaved, onOpenAsset }) {
  const allAssets = Array.isArray(allAssetsProp) ? allAssetsProp : []
  // `asset` is state so a fresh create can flip the modal into edit mode in place
  // (files/tasks/sharing need a saved asset id before they can be used).
  const [asset, setAsset] = useState(initialAsset)
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
    // template holds the template ID (per-user templates are id-referenced)
    template: asset?.template_id || templates[0]?.id || '',
    name: asset?.name || '',
    parent_id: asset?.parent_id || defaultParentId || '',
    fields: { ...(asset?.fields || {}) },
    notes: asset?.notes || '',
    owner: 'me',
  })
  // Existing assets open read-first (clean view); creating starts in the editor.
  // The view's Edit button flips this to 'edit' in place.
  const [mode, setMode] = useState(initialAsset ? 'view' : 'edit')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [linkedTasks, setLinkedTasks] = useState([])
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [access, setAccess] = useState({
    shared_with: asset?.shared_with || [],
    hidden_from: asset?.hidden_from || [],
    contributors: asset?.contributors || [],
  })
  const [attachments, setAttachments] = useState(asset?.attachments || [])
  const [uploading, setUploading] = useState(false)
  const [members, setMembers] = useState([])
  const [roleNames, setRoleNames] = useState([])
  const [archivePrompt, setArchivePrompt] = useState(false)
  const [showParentPicker, setShowParentPicker] = useState(false)
  const [shareScope, setShareScope] = useState('all') // 'all' = cascade to children, 'one' = this node only

  const templatesById = Object.fromEntries((templates || []).map(t => [t.id, t]))
  const groupTarget = workspace === 'business' ? 'team' : 'household'

  // Active (non-archived) descendants of this asset — drives the 3-choice archive
  const activeDescendants = (() => {
    if (!editing) return 0
    const kids = {}
    for (const a of allAssets) (kids[a.parent_id] = kids[a.parent_id] || []).push(a)
    let count = 0
    const stack = [...(kids[asset.id] || [])]
    while (stack.length) {
      const n = stack.pop()
      if (!n.archived) count++
      stack.push(...(kids[n.id] || []))
    }
    return count
  })()

  useEffect(() => {
    assetsApi.members().then(m => setMembers((m || []).map(x => x.name))).catch(() => {})
    // Feature-role names feed the hide-from role chips (role:crew etc.)
    assetsApi.roles().then(r => setRoleNames(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])

  // For an existing asset the template comes embedded (_template) — handles shared
  // assets whose template the viewer doesn't own; on create, use the picked one.
  const template = editing
    ? (asset._template || templatesById[asset.template_id] || null)
    : templatesById[form.template]
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
    if (!asset?.id) return
    tasksApi.list()
      .then(all => setLinkedTasks((all || []).filter(t => t.asset_id === asset.id)))
      .catch(() => {})
  }, [asset?.id])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function setFieldValue(key, value) {
    setForm(f => ({ ...f, fields: { ...f.fields, [key]: value } }))
  }

  // Cancel out of the editor: an existing asset was opened in the read view, so
  // return there; a brand-new (or just-created) asset closes the modal.
  function handleCancel() {
    if (initialAsset) setMode('view')
    else onClose()
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
        // Save sharing/hiding in the same Save (owner/pool-manager only) so the
        // one Save button persists shares too — no separate "Save access" step.
        if (canManage) {
          const accessPayload = isPool
            ? { hidden_from: access.hidden_from, contributors: access.contributors, cascade: shareScope === 'all' }
            : { shared_with: access.shared_with, hidden_from: access.hidden_from, cascade: shareScope === 'all' }
          await assetsApi.updateAccess(asset.id, accessPayload)
        }
        onSaved()
        onClose()
      } else {
        const created = await assetsApi.create({
          template_id: form.template,
          name: form.name,
          parent_id: form.parent_id || null,
          fields,
          notes: form.notes || null,
          owner: form.owner,
        })
        // Flip to edit mode in place so files/tasks/sharing become available
        setAsset(created)
        setAttachments(created.attachments || [])
        onSaved()
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function doArchive(cascade) {
    setArchivePrompt(false)
    setLoading(true)
    try {
      if (asset.archived) await assetsApi.unarchive(asset.id, true)
      else await assetsApi.archive(asset.id, cascade)
      onSaved()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleArchive() {
    if (!asset.archived && activeDescendants > 0) {
      setArchivePrompt(true)   // ask cascade vs only-this
    } else {
      doArchive(false)
    }
  }

  async function handleLeave() {
    if (!confirm(`Remove yourself from "${asset.name}"? You can be re-added later.`)) return
    setLoading(true)
    try {
      await assetsApi.leave(asset.id)
      onSaved()
      onClose()
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
      onClose()
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
      onClose()
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

  // The view can change the asset (quick status, contribute fields, comments,
  // capped uploads) — sync modal state + the editor's form so a later Edit/Save
  // doesn't revert those changes, and refresh the page list behind the modal.
  function handleViewUpdate(updated) {
    setAsset(updated)
    setAttachments(updated.attachments || [])
    setForm(f => ({
      ...f,
      name: updated.name ?? f.name,
      fields: { ...(updated.fields || {}) },
      notes: updated.notes ?? f.notes,
    }))
    onSaved()
  }

  // Read-first: an existing asset opens in a clean, readable view. Edit (owner /
  // editor only) flips this same modal into the editor below. Contribute-level
  // viewers (employees) never see the editor — they work inline in the view.
  if (mode === 'view' && asset) {
    return (
      <AssetView
        asset={asset}
        template={template}
        linkedTasks={linkedTasks}
        childAssets={allAssets.filter(a => a.parent_id === asset.id)}
        canEdit={!readOnly}
        canManage={canManage}
        user={user}
        onEdit={() => setMode('edit')}
        onClose={onClose}
        onOpenAsset={onOpenAsset}
        onAssetUpdated={handleViewUpdate}
      />
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-md">
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
                      key={t.id}
                      type="button"
                      onClick={() => set('template', t.id)}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                        form.template === t.id
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

            {/* Parent — foldered tree-picker (own/pool assets) */}
            {!isForeign && parentOptions.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-1">
                  Inside <span className="text-charcoal-400 font-normal">(optional)</span>
                </label>
                <button
                  type="button"
                  onClick={() => setShowParentPicker(p => !p)}
                  className="input text-left flex items-center justify-between"
                >
                  <span className="truncate">
                    {form.parent_id
                      ? (allAssets.find(a => a.id === form.parent_id)?.name || 'Selected')
                      : 'Top level'}
                  </span>
                  <span className="text-xs text-charcoal-400">{showParentPicker ? '▲' : 'Change ▾'}</span>
                </button>
                {showParentPicker && (
                  <div className="mt-1 border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-1 max-h-48 overflow-y-auto">
                    <AssetTreePicker
                      candidates={parentOptions}
                      disabledId={form.parent_id || null}
                      onPick={id => { set('parent_id', id || ''); setShowParentPicker(false) }}
                    />
                  </div>
                )}
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

          {/* On create: show what unlocks after saving so nothing feels hidden */}
          {!editing && (
            <p className="text-xs text-charcoal-400 border-t border-charcoal-100 dark:border-charcoal-800 pt-3">
              📎 Files, ✓ linked tasks, and 🔗 sharing become available right after you create this asset.
            </p>
          )}

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
                    <div key={i} className="space-y-1">
                      <div className="flex items-center gap-2 text-sm">
                        <select
                          value={s.target}
                          onChange={e => setAccess(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, target: e.target.value } : x) }))}
                          className="input !py-1 flex-1"
                        >
                          <option value="">— pick —</option>
                          <option value={groupTarget}>{groupTarget === 'team' ? '🧑‍🤝‍🧑 Whole team' : '🏠 Whole household'}</option>
                          {members.filter(m => m !== user?.name).map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                        <select
                          value={s.access}
                          onChange={e => setAccess(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, access: e.target.value, ...(e.target.value === 'contribute' && !x.caps ? { caps: { fields: [], add: ['comments'] } } : {}) } : x) }))}
                          className="input !py-1 !w-28"
                        >
                          <option value="read">read</option>
                          <option value="contribute">contribute</option>
                          <option value="edit">edit</option>
                        </select>
                        <button type="button" onClick={() => setAccess(a => ({ ...a, shared_with: a.shared_with.filter((_, j) => j !== i) }))} className="text-red-400 hover:text-red-500">✕</button>
                      </div>
                      {s.access === 'contribute' && (
                        <CapsSelector
                          caps={s.caps}
                          onChange={caps => setAccess(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, caps } : x) }))}
                          templateFields={template?.fields || []}
                        />
                      )}
                    </div>
                  ))}
                  <button type="button" onClick={() => setAccess(a => ({ ...a, shared_with: [...a.shared_with, { target: '', access: 'read' }] }))} className="btn-ghost text-xs px-2 py-1">
                    ＋ Share with…
                  </button>
                  <p className="text-[10px] text-charcoal-400">People you add get a request to accept before it appears for them. Contribute = you pick exactly what they can change or add.</p>
                </div>
              )}
              {isPool && (
                <div className="space-y-1">
                  <label className="block text-xs text-charcoal-400">Contributors <span className="font-normal">(can update what you pick — without full pool rights)</span></label>
                  {(access.contributors || []).map((c, i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex items-center gap-2 text-sm">
                        <select
                          value={c.target}
                          onChange={e => setAccess(a => ({ ...a, contributors: a.contributors.map((x, j) => j === i ? { ...x, target: e.target.value } : x) }))}
                          className="input !py-1 flex-1"
                        >
                          <option value="">— pick —</option>
                          <option value={groupTarget}>{groupTarget === 'team' ? '🧑‍🤝‍🧑 Whole team' : '🏠 Whole household'}</option>
                          {members.filter(m => m !== user?.name).map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                        <button type="button" onClick={() => setAccess(a => ({ ...a, contributors: a.contributors.filter((_, j) => j !== i) }))} className="text-red-400 hover:text-red-500">✕</button>
                      </div>
                      <CapsSelector
                        caps={c.caps}
                        onChange={caps => setAccess(a => ({ ...a, contributors: a.contributors.map((x, j) => j === i ? { ...x, caps } : x) }))}
                        templateFields={template?.fields || []}
                      />
                    </div>
                  ))}
                  <button type="button" onClick={() => setAccess(a => ({ ...a, contributors: [...(a.contributors || []), { target: '', caps: { fields: [], add: ['comments'] } }] }))} className="btn-ghost text-xs px-2 py-1">
                    ＋ Contributor…
                  </button>
                </div>
              )}
              <div>
                <label className="block text-xs text-charcoal-400 mb-1">Hide from</label>
                <TagInput
                  value={access.hidden_from || []}
                  onChange={hidden_from => setAccess(a => ({ ...a, hidden_from }))}
                  suggestions={[
                    ...members.filter(m => m !== user?.name),
                    ...roleNames.map(r => `role:${r}`),
                  ]}
                  strict
                  placeholder="Pick people or role:… to hide this from…"
                />
              </div>
              {activeDescendants > 0 && (
                <div className="flex gap-1 text-xs">
                  {[
                    { id: 'all', label: 'Apply to everything inside' },
                    { id: 'one', label: 'This one only' },
                  ].map(o => (
                    <button
                      key={o.id}
                      type="button"
                      onClick={() => setShareScope(o.id)}
                      className={`flex-1 py-1.5 rounded-md font-medium transition-colors ${
                        shareScope === o.id
                          ? 'bg-orange-500 text-white'
                          : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                      }`}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-charcoal-400">Sharing is saved when you press Save below.</p>
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
                        <span className="opacity-75"> — {formatChanges(h.changes)}</span>
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
            {isForeign && !isPool && (
              <button type="button" onClick={handleLeave} disabled={loading}
                className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                Leave
              </button>
            )}
            {readOnly ? (
              <button type="button" onClick={onClose} className="btn-ghost flex-1">Close</button>
            ) : (
              <>
                {editing && (isAdmin || (!isForeign && !isPool)) && (
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
                <button type="button" onClick={handleCancel} className="btn-ghost flex-1">Cancel</button>
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

        {archivePrompt && (
          <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={() => setArchivePrompt(false)}>
            <div className="card p-5 w-full max-w-xs" onClick={e => e.stopPropagation()}>
              <p className="font-semibold mb-1">Archive “{asset.name}”?</p>
              <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
                It has {activeDescendants} active item{activeDescendants !== 1 ? 's' : ''} inside.
              </p>
              <div className="space-y-2">
                <button onClick={() => doArchive(true)} disabled={loading} className="btn-primary w-full text-sm">
                  Archive this and everything inside
                </button>
                <button onClick={() => doArchive(false)} disabled={loading} className="btn-ghost w-full text-sm">
                  Archive only this one
                </button>
                <button onClick={() => setArchivePrompt(false)} className="w-full text-sm text-charcoal-400 hover:text-charcoal-600 py-1">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
