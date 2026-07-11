import { useState } from 'react'
import { AttachmentThumb, formatChanges, fieldDisplay } from './assetDisplay'

const OWNER_CHIP = { team: '🧑‍🤝‍🧑 Team', household: '🏠 Household' }

// Clean, read-first view of a single asset — everything laid out to read at a
// glance (no input rows). AssetModal renders this first for an existing asset;
// the Edit button flips the same modal into the editor (owner/editor only).
export default function AssetView({
  asset, template, linkedTasks, childAssets,
  canEdit, canManage, onEdit, onClose, onOpenAsset,
}) {
  const [showHistory, setShowHistory] = useState(false)

  const isForeign = !!asset._owner
  const isPool = asset._owner === 'team' || asset._owner === 'household'
  const status = asset.fields?.status
  // status is surfaced as a header badge, so drop it from the field grid
  const fieldDefs = (template?.fields || []).filter(f => f.key !== 'status')
  const notes = (asset.notes || '').trim()
  const attachments = asset.attachments || []
  const shares = (asset.shared_with || []).filter(s => s.target)
  const hidden = asset.hidden_from || []
  const history = asset.history || []
  const kids = Array.isArray(childAssets) ? childAssets : []

  function shareLabel(target) {
    if (target === 'team') return 'Team'
    if (target === 'household') return 'Household'
    return target
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
              {status && <span className="badge text-[10px]">{status}</span>}
              {isPool && <span className="text-blue-500">{OWNER_CHIP[asset._owner]}</span>}
              {isForeign && !isPool && <span className="text-blue-500">shared by {asset._owner}</span>}
              {asset.archived && <span>archived</span>}
            </div>
          </div>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200 shrink-0">✕</button>
        </div>

        <div className="space-y-4">
          {/* Attachments */}
          {attachments.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {attachments.map(f => (
                <AttachmentThumb key={f.id} assetId={asset.id} file={f} canEdit={false} onDelete={() => {}} />
              ))}
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

          {/* Sharing summary — only the owner/manager needs to see this */}
          {canManage && (shares.length > 0 || hidden.length > 0) && (
            <div className="text-xs space-y-0.5">
              {shares.length > 0 && (
                <div>
                  <span className="text-charcoal-400">Shared with: </span>
                  <span className="text-charcoal-600 dark:text-charcoal-300">
                    {shares.map(s => `${shareLabel(s.target)} (${s.access})`).join(', ')}
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
