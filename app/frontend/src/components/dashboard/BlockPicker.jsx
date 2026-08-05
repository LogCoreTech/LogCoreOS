import { useEffect, useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'
import { BLOCK_REGISTRY } from './blockRegistry'

const CATEGORY_LABELS = { live_aggregate: 'Live data', record_linked: 'Record-linked', freeform: 'Freeform' }

// Config fields each record-linked / configurable block type needs, keyed the
// same way the backend resolvers read ctx.config — kept minimal (plain text
// id entry) for v1; a polished search-picker per record type is follow-up work.
const CONFIG_FIELDS = {
  single_task: [{ key: 'task_id', label: 'Task ID' }],
  finance_activity: [
    { key: 'asset_id', label: 'Asset ID (optional)' },
    { key: 'contact_id', label: 'Contact ID (optional)' },
    { key: 'book_id', label: 'Finance Book ID (optional)' },
  ],
  finance_book_report: [{ key: 'book_id', label: 'Finance Book ID' }],
  linked_deals: [{ key: 'contact_id', label: 'Contact ID' }],
  custom_fields: [
    { key: 'contact_id', label: 'Contact ID (optional)' },
    { key: 'asset_id', label: 'Asset ID (optional)' },
  ],
  linked_assets: [{ key: 'contact_id', label: 'Contact ID' }],
  documents: [{ key: 'asset_id', label: 'Asset ID' }],
  linked_tasks: [{ key: 'asset_id', label: 'Asset ID' }],
  linked_contact: [{ key: 'asset_id', label: 'Asset ID' }],
  note_embed: [{ key: 'path', label: 'Note path' }],
  journal_entry: [{ key: 'date', label: 'Date (YYYY-MM-DD)' }],
  single_event: [{ key: 'event_id', label: 'Event ID' }],
  workflow_status: [{ key: 'workflow_id', label: 'Workflow ID' }],
  text_block: [{ key: 'text', label: 'Text', textarea: true }],
  link_button: [{ key: 'label', label: 'Button label' }, { key: 'url', label: 'URL (https://...)' }],
  heading_divider: [
    { key: 'text', label: 'Heading text (leave blank for a plain divider)' },
    { key: 'style', label: 'Style: "heading" or "divider"' },
  ],
}

export default function BlockPicker({ onAdd, onClose }) {
  const [catalog, setCatalog] = useState(null)
  const [selected, setSelected] = useState(null)
  const [config, setConfig] = useState({})

  useEffect(() => { dashboardsApi.catalog().then(setCatalog).catch(() => setCatalog([])) }, [])

  function pick(type) {
    setSelected(type)
    setConfig({})
  }

  function add() {
    onAdd(selected, { ...config })
  }

  const grouped = (catalog || []).reduce((acc, c) => {
    if (!BLOCK_REGISTRY[c.type]) return acc
    acc[c.category] = acc[c.category] || []
    acc[c.category].push(c)
    return acc
  }, {})

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Add block</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>

        {!selected ? (
          <div className="space-y-4 max-h-[60vh] overflow-y-auto">
            {catalog === null && <p className="text-sm text-charcoal-400">Loading…</p>}
            {Object.entries(grouped).map(([cat, items]) => (
              <div key={cat}>
                <h3 className="text-xs uppercase tracking-wide text-charcoal-400 mb-2">{CATEGORY_LABELS[cat] || cat}</h3>
                <div className="grid grid-cols-2 gap-2">
                  {items.map(c => (
                    <button
                      key={c.type}
                      onClick={() => pick(c.type)}
                      className="text-left p-2 rounded-lg border border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400 flex items-center gap-2"
                    >
                      <span>{BLOCK_REGISTRY[c.type].icon}</span>
                      <span className="text-sm truncate">{BLOCK_REGISTRY[c.type].label}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium">{BLOCK_REGISTRY[selected].icon} {BLOCK_REGISTRY[selected].label}</p>
            {(CONFIG_FIELDS[selected] || []).map(f => (
              <div key={f.key}>
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{f.label}</label>
                {f.textarea ? (
                  <textarea
                    className="input w-full"
                    rows={4}
                    value={config[f.key] || ''}
                    onChange={e => setConfig({ ...config, [f.key]: e.target.value })}
                  />
                ) : (
                  <input
                    className="input w-full"
                    value={config[f.key] || ''}
                    onChange={e => setConfig({ ...config, [f.key]: e.target.value })}
                  />
                )}
              </div>
            ))}
            {!CONFIG_FIELDS[selected] && (
              <p className="text-xs text-charcoal-400">No configuration needed — shows your own data.</p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn-ghost" onClick={() => setSelected(null)}>Back</button>
              <button className="btn-primary" onClick={add}>Add to dashboard</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
