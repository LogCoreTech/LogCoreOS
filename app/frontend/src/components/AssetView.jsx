import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { assets as assetsApi, contacts as contactsApi } from '../lib/api'
import { AttachmentThumb, formatChanges, fieldDisplay, FieldInput } from './assetDisplay'
import { fmtMoney } from './finance/money'

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
  asset, template, linkedTasks, financeActivity, childAssets,
  canEdit, canManage, user, onEdit, onClose, onOpenAsset, onAssetUpdated,
}) {
  const [showHistory, setShowHistory] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [commentText, setCommentText] = useState('')
  const [draft, setDraft] = useState({})
  const [uploading, setUploading] = useState(false)
  const [mutePopup, setMutePopup] = useState(false)
  const [muteInfo, setMuteInfo] = useState(null) // {muted, self, via, via_name}
  // Per-user, per-open collapse — plain component state, so the section
  // reappears the next time the asset is opened.
  const [commentsCollapsed, setCommentsCollapsed] = useState(false)

  const isForeign = !!asset._owner
  const isPool = asset._owner === 'team' || asset._owner === 'household'
  const isContribute = asset._access === 'contribute'
  const caps = asset._caps || {}
  const capFields = caps.fields || []
  const capAdds = caps.add || []
  const status = asset.fields?.status
  const fieldDefs = (template?.fields || []).filter(f => f.key !== 'status')
  const statusDef = (template?.fields || []).find(f => f.key === 'status')
  const navigate = useNavigate()

  // Contact-type fields render the contact's name as a jump link — resolve
  // names once, only when the template actually has a contact field.
  const hasContactField = (template?.fields || []).some(f => f.type === 'contact')
  const [contactNames, setContactNames] = useState({})
  useEffect(() => {
    if (!hasContactField) return
    contactsApi.list()
      .then(r => setContactNames(Object.fromEntries((Array.isArray(r) ? r : []).map(c => [c.id, c.name]))))
      .catch(() => {})
  }, [hasContactField])
  const notes = (asset.notes || '').trim()
  const attachments = asset.attachments || []
  const shares = (asset.shared_with || []).filter(s => s.target)
  const hidden = asset.hidden_from || []
  const contributors = (asset.contributors || []).filter(c => c.target)
  const history = asset.history || []
  const comments = asset.comments || []
  const kids = Array.isArray(childAssets) ? childAssets : []

  // What this viewer can do from the view itself
  const isAdmin = user?.role === 'admin'
  const commentsHidden = !!asset.comments_hidden
  const canQuickStatus = !!statusDef && (canEdit || (isContribute && capFields.includes('status')))
  const inlineDefs = isContribute ? fieldDefs.filter(f => capFields.includes(f.key)) : []
  const canComment = !commentsHidden && (canEdit || canManage || (isContribute && capAdds.includes('comments')))
  const canUploadHere = isContribute && capAdds.includes('files')
  // Only edit-level users receive comment notifications, so only they get the bell
  const showBell = canEdit || canManage
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

  async function openMutePopup() {
    setMutePopup(true)
    setMuteInfo(null)
    try { setMuteInfo(await assetsApi.muteState(asset.id)) } catch { setMuteInfo({ muted: false, self: false }) }
  }

  async function toggleMute() {
    if (!muteInfo) return
    setBusy(true)
    try {
      setMuteInfo(await assetsApi.setMute(asset.id, !muteInfo.self))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
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
          <div className="flex items-center gap-1 shrink-0">
            {showBell && (
              <button
                onClick={openMutePopup}
                className="text-charcoal-400 hover:text-orange-500 transition-colors p-0.5"
                title="Comment notifications for this asset"
              >
                🔔
              </button>
            )}
            <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
          </div>
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
                const raw = asset.fields?.[def.key]
                const val = fieldDisplay(def, raw)
                return (
                  <div key={def.key} className="min-w-0">
                    <dt className="text-[11px] uppercase tracking-wide text-charcoal-400">{def.label}</dt>
                    <dd className={`text-sm break-words ${val == null ? 'text-charcoal-300 dark:text-charcoal-600' : ''}`}>
                      {val == null ? '—' : def.type === 'contact' ? (
                        <button
                          type="button"
                          onClick={() => navigate(`/contacts?contact=${raw}`)}
                          className="text-orange-500 hover:underline"
                        >🧑 {contactNames[raw] || '(contact)'}</button>
                      ) : val}
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

          {/* Finance activity — transactions tagged with this asset, across
              every book the viewer can see (server-side access-scoped) */}
          {(financeActivity || []).length > 0 && (() => {
            const income = financeActivity.reduce((s, t) => s + Math.max(t.amount_cents || 0, 0), 0)
            const expenses = financeActivity.reduce((s, t) => s + Math.min(t.amount_cents || 0, 0), 0)
            const net = income + expenses
            return (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">
                  Finance activity ({financeActivity.length})
                </div>
                <div className="flex gap-4 text-sm mb-1.5">
                  <span>Income <b className="text-green-600">{fmtMoney(income)}</b></span>
                  <span>Expenses <b className="text-red-500">{fmtMoney(expenses)}</b></span>
                  <span>Net <b className={net < 0 ? 'text-red-500' : 'text-green-600'}>{fmtMoney(net)}</b></span>
                </div>
                <ul className="text-sm space-y-1">
                  {financeActivity.map(t => (
                    <li key={t.id} className="flex items-center gap-2">
                      <span className="truncate">{t.payee || t.category || '(uncategorized)'}</span>
                      <span className={`shrink-0 ${t.amount_cents < 0 ? 'text-red-500' : 'text-green-600'}`}>
                        {fmtMoney(t.amount_cents)}
                      </span>
                      <span className="text-xs text-charcoal-400 ml-auto shrink-0">{t.book_name} · {t.date}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })()}

          {/* Comments — attributed job log; edit-level users get notified.
              Any user can collapse the section for themselves (resets on
              reopen); turning comments OFF for everyone lives in the edit
              page; only an admin can delete individual comments. */}
          {commentsHidden && canEdit && (
            <p className="text-xs text-charcoal-400">
              Comments are turned off on this asset — manage it in ✎ Edit.
            </p>
          )}
          {!commentsHidden && (comments.length > 0 || canComment) && (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[11px] uppercase tracking-wide text-charcoal-400">
                  Comments{comments.length > 0 ? ` (${comments.length})` : ''}
                </span>
                <button
                  type="button"
                  onClick={() => setCommentsCollapsed(c => !c)}
                  className="text-[10px] text-charcoal-400 hover:text-orange-500 transition-colors ml-auto"
                  title="Hide the comments section for yourself until you reopen this asset"
                >
                  {commentsCollapsed ? 'Show' : 'Hide'}
                </button>
              </div>
              {!commentsCollapsed && comments.length > 0 && (
                <div className="space-y-2 max-h-48 overflow-y-auto mb-2">
                  {comments.map(c => (
                    <div key={c.id} className="group text-sm bg-charcoal-50 dark:bg-charcoal-800 rounded-lg px-2.5 py-1.5">
                      <div className="flex items-center gap-2 text-[11px] text-charcoal-400">
                        <span className="font-medium text-charcoal-600 dark:text-charcoal-300">{c.by || 'system'}</span>
                        <span>{fmtWhen(c.at)}</span>
                        {isAdmin && (
                          <button
                            type="button"
                            onClick={() => removeComment(c)}
                            className="ml-auto text-red-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Delete comment (admin)"
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
              {!commentsCollapsed && canComment && (
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

        {/* Comment-notification mute popup (per-user; covers the whole subtree) */}
        {mutePopup && (
          <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={() => setMutePopup(false)}>
            <div className="card p-5 w-full max-w-xs" onClick={e => e.stopPropagation()}>
              <p className="font-semibold mb-1">Comment notifications</p>
              <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">
                Applies to “{asset.name}” and everything inside it. Only affects you.
              </p>
              {muteInfo == null ? (
                <div className="flex justify-center py-2">
                  <div className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : muteInfo.muted && !muteInfo.self ? (
                <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-3">
                  🔕 Muted through “{muteInfo.via_name || 'a parent asset'}” — open that asset to unmute.
                </p>
              ) : (
                <button onClick={toggleMute} disabled={busy} className="btn-primary w-full text-sm mb-2">
                  {muteInfo.self ? '🔔 Turn notifications on' : '🔕 Mute notifications'}
                </button>
              )}
              <button onClick={() => setMutePopup(false)} className="w-full text-sm text-charcoal-400 hover:text-charcoal-600 py-1">
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
