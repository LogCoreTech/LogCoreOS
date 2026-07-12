import { useState } from 'react'
import { assets as assetsApi } from '../lib/api'
import { AttachmentThumb, formatChanges, fieldDisplay, FieldInput } from './assetDisplay'

const OWNER_CHIP = { team: '🧑‍🤝‍🧑 Team', household: '🏠 Household' }

function fmtWhen(iso) {
  try {
    const d = new Date(iso)
    const diff = Math.floor((new Date() - d) / 60000)
    if (diff < 1) return 'just now'
    if (diff < 60) return `${diff}m ago`
    if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
    return d.toLocaleDateString()
  } catch { return '' }
}

// Clean, read-first view of a single asset — everything laid out to read at a
// glance (no input rows). AssetModal renders this first for an existing asset;
// the Edit button flips the same modal into the editor (owner/editor only).
// Contribute-level viewers (employees) work entirely from here: quick status,
// inline controls for their granted fields, comments, capped file upload.
export default function AssetView({
  asset, template, linkedTasks, childAssets,
  canEdit, canManage, user, onEdit, onClose, onOpenAsset, onAssetUpdated,
}) {
  const [showHistory, setShowHistory] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [commentText, setCommentText] = useState('')
  const [draft, setDraft] = useState({})
  const [uploading, setUploading] = useState(false)

  const isForeign = !!asset._owner
  const isPool = asset._owner === 'team' || asset._owner === 'household'
  const isContribute = asset._access === 'contribute'
  const caps = asset._caps || {}
  const capFields = caps.fields || []
  const capAdds = caps.add || []
  const status = asset.fields?.status
  const fieldDefs = (template?.fields || []).filter(f => f.key !== 'status')
  const statusDef = (template?.fields || []).find(f => f.key === 'status')
  const notes = (asset.notes || '').trim()
  const attachments = asset.attachments || []
  const shares = (asset.shared_with || []).filter(s => s.target)
  const hidden = asset.hidden_from || []
  const contributors = (asset.contributors || []).filter(c => c.target)
  const history = asset.history || []
  const comments = asset.comments || []
  const kids = Array.isArray(childAssets) ? childAssets : []

  // What this viewer can do from the view itself
  const canQuickStatus = !!statusDef && (canEdit || (isContribute && capFields.includes('status')))
  const inlineDefs = isContribute ? fieldDefs.filter(f => capFields.includes(f.key)) : []
  const canComment = canEdit || canManage || (isContribute && capAdds.includes('comments'))
  const canUploadHere = isContribute && capAdds.includes('files')
  const dirty = Object.keys(draft).length > 0

  function shareLabel(target) {
    if (target === 'team') return 'Team'
    if (target === 'household') return 'Household'
    return target
  }

  async function patchFields(fields) {
    setBusy(true)
    setError('')
    try {
      const res = await assetsApi.update(asset.id, { fields })
      onAssetUpdated && onAssetUpdated({ ...asset, ...res })
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  async function quickStatus(value) {
    await patchFields({ status: value === '' ? null : value })
  }

  async function saveDraft() {
    const clean = {}
    for (const [k, v] of Object.entries(draft)) clean[k] = v === '' ? null : v
    if (await patchFields(clean)) setDraft({})
  }

  async function postComment() {
    const text = commentText.trim()
    if (!text) return
    setBusy(true)
    setError('')
    try {
      const c = await assetsApi.addComment(asset.id, text)
      onAssetUpdated && onAssetUpdated({ ...asset, comments: [...comments, c] })
      setCommentText('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeComment(c) {
    try {
      await assetsApi.removeComment(asset.id, c.id)
      onAssetUpdated && onAssetUpdated({ ...asset, comments: comments.filter(x => x.id !== c.id) })
    } catch (err) {
      setError(err.message)
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
      onAssetUpdated && onAssetUpdated({ ...asset, attachments: [...attachments, att] })
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-md">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xl shrink-0">{template?.icon || '▫️'}</span>
              <h2 className="font-semibold text-lg truncate">{asset.name}</h2>
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs text-charcoal-400 flex-wrap">
              <span>{template?.label || asset.template}</span>
              {canQuickStatus ? (
                <select
                  value={status ?? ''}
                  onChange={e => quickStatus(e.target.value)}
                  disabled={busy}
                  className="input !py-0.5 !px-1.5 !w-auto text-xs"
                  title="Change status"
                >
                  <option value="">—</option>
                  {(statusDef.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                status && <span className="badge text-[10px]">{status}</span>
              )}
              {isPool && <span className="text-blue-500">{OWNER_CHIP[asset._owner]}</span>}
              {isForeign && !isPool && <span className="text-blue-500">shared by {asset._owner}</span>}
              {isContribute && <span className="badge text-[10px]">contributor</span>}
              {asset.archived && <span>archived</span>}
            </div>
          </div>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200 shrink-0">✕</button>
        </div>

        <div className="space-y-4">
          {/* Attachments */}
          {(attachments.length > 0 || canUploadHere) && (
            <div>
              {attachments.length > 0 && (
                <div className="grid grid-cols-3 gap-2">
                  {attachments.map(f => (
                    <AttachmentThumb key={f.id} assetId={asset.id} file={f} canEdit={false} onDelete={() => {}} />
                  ))}
                </div>
              )}
              {canUploadHere && (
                <label className="btn-ghost text-xs px-3 py-1.5 inline-block cursor-pointer mt-2">
                  {uploading ? 'Uploading…' : '＋ Add photo / PDF'}
                  <input type="file" accept="image/jpeg,image/png,image/webp,image/avif,application/pdf" onChange={handleUpload} className="hidden" disabled={uploading} />
                </label>
              )}
            </div>
          )}

          {/* Contribute: inline controls for granted fields only */}
          {inlineDefs.length > 0 && (
            <div className="border border-orange-500/30 rounded-lg p-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">You can update</p>
              {inlineDefs.map(def => (
                <FieldInput
                  key={def.key}
                  def={def}
                  value={draft[def.key] !== undefined ? draft[def.key] : asset.fields?.[def.key]}
                  onChange={v => setDraft(d => ({ ...d, [def.key]: v }))}
                />
              ))}
              {dirty && (
                <button type="button" onClick={saveDraft} disabled={busy} className="btn-primary text-xs px-3 py-1.5 w-full">
                  {busy ? 'Saving…' : 'Save updates'}
                </button>
              )}
            </div>
          )}

          {/* Fields — readable label/value pairs, template order */}
          {fieldDefs.length > 0 && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              {fieldDefs.map(def => {
                const val = fieldDisplay(def, asset.fields?.[def.key])
                return (
                  <div key={def.key} className="min-w-0">
                    <dt className="text-[11px] uppercase tracking-wide text-charcoal-400">{def.label}</dt>
                    <dd className={`text-sm break-words ${val == null ? 'text-charcoal-300 dark:text-charcoal-600' : ''}`}>
                      {val == null ? '—' : val}
                    </dd>
                  </div>
                )
              })}
            </dl>
          )}

          {/* Notes */}
          {notes && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">Notes</div>
              <p className="text-sm whitespace-pre-wrap break-words">{notes}</p>
            </div>
          )}

          {/* Children — drill into an item inside this one */}
          {kids.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">Inside this ({kids.length})</div>
              <div className="space-y-1">
                {kids.map(c => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => onOpenAsset && onOpenAsset(c)}
                    className="flex items-center gap-2 w-full text-left text-sm py-1 px-2 rounded-md hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors"
                  >
                    <span className="shrink-0">{c._template?.icon || '▫️'}</span>
                    <span className={`truncate ${c.archived ? 'line-through text-charcoal-400' : ''}`}>{c.name}</span>
                    {c.fields?.status && <span className="badge text-[10px] shrink-0">{c.fields.status}</span>}
                    <span className="text-charcoal-300 dark:text-charcoal-600 ml-auto shrink-0">›</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Linked tasks */}
          {(linkedTasks || []).length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">Linked tasks ({linkedTasks.length})</div>
              <ul className="text-sm space-y-1">
                {linkedTasks.map(t => (
                  <li key={t.id} className="flex items-center gap-2">
                    <span className={t.status === 'done' ? 'line-through text-charcoal-400' : ''}>{t.title}</span>
                    {t.status === 'done' && <span className="text-green-500 text-xs shrink-0">✓</span>}
                    {t.due_date && <span className="text-xs text-charcoal-400 ml-auto shrink-0">{t.due_date}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Comments — attributed job log; edit-level users get notified */}
          {(comments.length > 0 || canComment) && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">
                Comments{comments.length > 0 ? ` (${comments.length})` : ''}
              </div>
              {comments.length > 0 && (
                <div className="space-y-2 max-h-48 overflow-y-auto mb-2">
                  {comments.map(c => (
                    <div key={c.id} className="group text-sm bg-charcoal-50 dark:bg-charcoal-800 rounded-lg px-2.5 py-1.5">
                      <div className="flex items-center gap-2 text-[11px] text-charcoal-400">
                        <span className="font-medium text-charcoal-600 dark:text-charcoal-300">{c.by || 'system'}</span>
                        <span>{fmtWhen(c.at)}</span>
                        {(c.by === user?.name || canManage) && (
                          <button
                            type="button"
                            onClick={() => removeComment(c)}
                            className="ml-auto text-red-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Delete comment"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                      <p className="whitespace-pre-wrap break-words">{c.text}</p>
                    </div>
                  ))}
                </div>
              )}
              {canComment && (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={commentText}
                    onChange={e => setCommentText(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); postComment() } }}
                    placeholder="Leave a note…"
                    maxLength={2000}
                    className="input !py-1.5 text-sm flex-1"
                  />
                  <button type="button" onClick={postComment} disabled={busy || !commentText.trim()} className="btn-primary text-xs px-3">
                    Post
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Sharing summary — only the owner/manager needs to see this */}
          {canManage && (shares.length > 0 || hidden.length > 0 || contributors.length > 0) && (
            <div className="text-xs space-y-0.5">
              {shares.length > 0 && (
                <div>
                  <span className="text-charcoal-400">Shared with: </span>
                  <span className="text-charcoal-600 dark:text-charcoal-300">
                    {shares.map(s => `${shareLabel(s.target)} (${s.access})`).join(', ')}
                  </span>
                </div>
              )}
              {contributors.length > 0 && (
                <div>
                  <span className="text-charcoal-400">Contributors: </span>
                  <span className="text-charcoal-600 dark:text-charcoal-300">
                    {contributors.map(c => shareLabel(c.target)).join(', ')}
                  </span>
                </div>
              )}
              {hidden.length > 0 && (
                <div>
                  <span className="text-charcoal-400">Hidden from: </span>
                  <span className="text-charcoal-600 dark:text-charcoal-300">{hidden.join(', ')}</span>
                </div>
              )}
            </div>
          )}

          {/* History */}
          {history.length > 0 && (
            <div className="text-xs">
              <button type="button" onClick={() => setShowHistory(h => !h)} className="text-charcoal-400 hover:text-orange-500 transition-colors">
                {showHistory ? '▾' : '▸'} History ({history.length})
              </button>
              {showHistory && (
                <div className="mt-1 pl-3 border-l-2 border-charcoal-200 dark:border-charcoal-700 space-y-1 max-h-40 overflow-y-auto">
                  {[...history].reverse().map((h, i) => (
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
        </div>

        {/* Footer */}
        <div className="flex gap-2 pt-4 mt-4 border-t border-charcoal-100 dark:border-charcoal-800">
          <button type="button" onClick={onClose} className="btn-ghost flex-1">Close</button>
          {canEdit && (
            <button type="button" onClick={onEdit} className="btn-primary flex-1">✎ Edit</button>
          )}
        </div>
      </div>
    </div>
  )
}
