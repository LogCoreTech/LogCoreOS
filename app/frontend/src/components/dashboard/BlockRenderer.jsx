import { BLOCK_REGISTRY, isConfigurable } from './blockRegistry'
import LockedBlockPlaceholder from './LockedBlockPlaceholder'

export default function BlockRenderer({ block, onRemove, onEdit, onAction, editing, locked = false }) {
  const meta = BLOCK_REGISTRY[block.type]
  if (!meta) {
    return (
      <div className="card h-full p-3 flex items-center justify-center text-xs text-charcoal-400">
        Unknown block type
      </div>
    )
  }
  const Comp = meta.Component

  // Chromeless blocks (action buttons) skip the card/header entirely — just
  // the bare pill filling the cell. Edit/remove still need a way in while
  // editing, so they get a tiny corner overlay instead of a reserved header.
  // `locked` (a templated dashboard — see Dashboard.jsx) suppresses both:
  // the block SET is template-controlled there, only layout is this
  // instance's own to customize, so there's nothing for ✎/✕ to do.
  if (meta.chromeless) {
    return (
      <div className="h-full w-full relative flex items-center justify-center">
        {block.ok ? <Comp data={block.data} onAction={onAction} /> : <LockedBlockPlaceholder reason={block.locked_reason} />}
        {editing && !locked && (
          <span className="absolute -top-2 -right-2 flex items-center gap-1 bg-white dark:bg-charcoal-800 border border-charcoal-200 dark:border-charcoal-600 rounded-full px-1.5 py-0.5 shadow shrink-0">
            {isConfigurable(block.type) && (
              <button
                onClick={() => onEdit(block)}
                className="text-charcoal-400 hover:text-orange-500 text-[10px] leading-none"
                title="Edit block config"
              >
                ✎
              </button>
            )}
            <button
              onClick={() => onRemove(block.id)}
              className="text-charcoal-400 hover:text-red-500 text-[10px] leading-none"
              title="Remove block"
            >
              ✕
            </button>
          </span>
        )}
      </div>
    )
  }

  // The icon+label header is edit-mode-only now (owner: "hide that until
  // edit mode is open. makes it look cleaner") — it exists purely to
  // identify/manage a block while arranging the dashboard, not as permanent
  // view-mode chrome. No reserved space for it at all in view mode, not just
  // hidden-but-present, so content gets the card's full height back.
  //
  // `shape` (default 'detail') is the content-aware styling pass — a block
  // that's just rows of related items (Top 3 Tasks, a contact's linked
  // assets, …) drops the bordered/frosted `.card` treatment entirely, since
  // every block getting identical box chrome regardless of what's inside it
  // was the single biggest contributor to the dashboard reading as "blocky."
  // 'detail'-shaped blocks (single-record content) keep today's card look
  // unchanged. The header row itself stays the same across shapes — only the
  // content wrapper's chrome changes.
  const shape = meta.shape || 'detail'
  const isListShape = shape === 'list'

  return (
    <div className={isListShape ? 'h-full p-2 overflow-hidden flex flex-col' : 'card h-full p-3 overflow-hidden flex flex-col'}>
      {editing && (
        <div className={`flex items-center justify-between mb-2 shrink-0 ${isListShape ? 'pb-2 border-b border-charcoal-200 dark:border-charcoal-700' : ''}`}>
          <span className="text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 truncate flex items-center gap-1">
            <span>{meta.icon}</span>{meta.label}
          </span>
          {!locked && (
            <span className="flex items-center gap-2 shrink-0">
              {isConfigurable(block.type) && (
                <button
                  onClick={() => onEdit(block)}
                  className="text-charcoal-400 hover:text-orange-500 text-xs"
                  title="Edit block config"
                >
                  ✎
                </button>
              )}
              <button
                onClick={() => onRemove(block.id)}
                className="text-charcoal-400 hover:text-red-500 text-xs"
                title="Remove block"
              >
                ✕
              </button>
            </span>
          )}
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto">
        {block.ok ? <Comp data={block.data} onAction={onAction} /> : <LockedBlockPlaceholder reason={block.locked_reason} />}
      </div>
    </div>
  )
}
