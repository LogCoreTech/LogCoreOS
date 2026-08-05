import { BLOCK_REGISTRY } from './blockRegistry'
import LockedBlockPlaceholder from './LockedBlockPlaceholder'

export default function BlockRenderer({ block, onRemove, editing }) {
  const meta = BLOCK_REGISTRY[block.type]
  if (!meta) {
    return (
      <div className="card h-full p-3 flex items-center justify-center text-xs text-charcoal-400">
        Unknown block type
      </div>
    )
  }
  const Comp = meta.Component
  return (
    <div className="card h-full p-3 overflow-hidden flex flex-col">
      <div className="flex items-center justify-between mb-2 shrink-0">
        <span className="text-xs font-semibold uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 truncate flex items-center gap-1">
          <span>{meta.icon}</span>{meta.label}
        </span>
        {editing && (
          <button
            onClick={() => onRemove(block.id)}
            className="text-charcoal-400 hover:text-red-500 text-xs shrink-0"
            title="Remove block"
          >
            ✕
          </button>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {block.ok ? <Comp data={block.data} /> : <LockedBlockPlaceholder reason={block.locked_reason} />}
      </div>
    </div>
  )
}
