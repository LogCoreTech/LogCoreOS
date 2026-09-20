import { useNavigate } from 'react-router-dom'
import { ALL_MODULES } from '../../../lib/constants'
import { deepLinkUrl } from '../../../lib/deepLinks'

// One generic row per tagged item, reused across every tab in
// HomeDetail.jsx. search_service.search()'s own lightweight
// {title, snippet, tags, record_id, _module} shape doesn't carry the
// fields a true per-type native row (TaskRow's category/streak/status,
// say) would need — a second per-record fetch per module would undercut
// the whole point of reusing search() for this view, so a single honest
// generic row is the deliberate v1 choice here, not a shortcut.
export default function TaggedItemRow({ item }) {
  const navigate = useNavigate()
  const mod = ALL_MODULES.find(m => m.id === item._module)

  return (
    <button
      onClick={() => navigate(deepLinkUrl(item._module, item.record_id))}
      className="w-full flex items-start gap-3 p-3 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 text-left transition-colors"
    >
      <span className="text-lg shrink-0" aria-hidden>{mod?.icon || '📄'}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{item.title}</p>
        {item.snippet && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 truncate">{item.snippet}</p>
        )}
      </div>
      <span className="text-xs text-charcoal-400 shrink-0">{mod?.label || item._module}</span>
    </button>
  )
}
