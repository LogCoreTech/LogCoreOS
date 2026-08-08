import { useEffect, useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'
import { BLOCK_REGISTRY, CONFIG_FIELD_SCHEMAS } from './blockRegistry'
import ContactPicker from '../contacts/ContactPicker'
import AssetPickerField from '../AssetPickerField'
import TaskPicker from '../TaskPicker'
import EventPicker from '../EventPicker'
import NotePicker from '../NotePicker'
import WorkflowPicker from '../WorkflowPicker'
import FinanceBookPicker from '../finance/FinanceBookPicker'
import ModuleAndRecordPicker from './ModuleAndRecordPicker'
import AssetSelectFieldPicker from './AssetSelectFieldPicker'
import ContactFieldPicker from './ContactFieldPicker'

const CATEGORY_LABELS = {
  live_aggregate: 'Live data',
  record_linked: 'Record-linked',
  freeform: 'Freeform',
  action: 'Actions',
}

// Dispatches a config field to the real picker/input for its `kind` (see
// CONFIG_FIELD_SCHEMAS in blockRegistry.js). Record-referencing kinds render
// a real search/tree/select picker — never a raw id/path text box — and
// render their own label internally; the plain input kinds render a label here.
//
// templateMode + subjectType (only meaningful when editing a dashboard
// TEMPLATE's block, not a real dashboard's) offer a "$subject" toggle on any
// contact/asset field whose kind matches the template's own declared subject
// type — checking it stores the literal sentinel "$subject" instead of a
// concrete id, resolved per-instance at render time against that dashboard's
// own subject (see dashboard_blocks/render.py's _resolve_subject_config).
function renderField(f, config, setConfig, templateMode = false, subjectType = null) {
  const val = config[f.key]
  const set = v => setConfig({ ...config, [f.key]: v })
  const label = f.optional ? `${f.label} (optional)` : f.label

  if (templateMode && subjectType && f.kind === subjectType) {
    const usingSubject = val === '$subject'
    return (
      <div className="space-y-1.5">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={usingSubject}
            onChange={e => set(e.target.checked ? '$subject' : '')}
          />
          Use this dashboard&apos;s own {subjectType}
        </label>
        {!usingSubject && renderField(f, config, setConfig)}
      </div>
    )
  }

  switch (f.kind) {
    case 'contact':
      return (
        <ContactPicker
          label={label}
          value={{ contactId: val }}
          onChange={(_name, id) => set(id)}
          placeholder="Search contacts…"
        />
      )
    case 'asset':
      return <AssetPickerField label={label} value={val} onChange={set} />
    case 'task':
      return <TaskPicker label={label} value={val} onChange={set} />
    case 'event':
      return <EventPicker label={label} value={val} onChange={set} />
    case 'note':
      return <NotePicker label={label} value={val} onChange={set} />
    case 'workflow':
      return <WorkflowPicker label={label} value={val} onChange={set} />
    case 'financeBook':
      return <FinanceBookPicker label={label} value={val} onChange={set} optional={f.optional} />
    case 'moduleAndRecord':
      return (
        <ModuleAndRecordPicker
          label={label}
          value={{ module: config.module, record_id: config.record_id, section: config.section }}
          onChange={(module, recordId, section) => setConfig({ ...config, module, record_id: recordId, section })}
        />
      )
    case 'assetSelectField':
      return (
        <AssetSelectFieldPicker
          label={label}
          assetId={config[f.dependsOn]}
          value={val}
          onChange={set}
        />
      )
    case 'contactField':
      return <ContactFieldPicker label={label} value={val} onChange={set} />
    case 'date':
      return (
        <div>
          <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>
          <input type="date" className="input w-full" value={val || ''} onChange={e => set(e.target.value)} />
        </div>
      )
    case 'select':
      return (
        <div>
          <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>
          <select className="input w-full" value={val || f.options[0].value} onChange={e => set(e.target.value)}>
            {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      )
    case 'textarea':
      return (
        <div>
          <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>
          <textarea className="input w-full" rows={4} value={val || ''} onChange={e => set(e.target.value)} />
        </div>
      )
    default:
      return (
        <div>
          <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>
          <input className="input w-full" value={val || ''} onChange={e => set(e.target.value)} />
        </div>
      )
  }
}

/**
 * Add-a-block picker, dual-purpose: pass `editingBlock` ({type, config}) to
 * reopen an existing block's config for editing instead of picking a new
 * type — same renderField dispatcher either way, just skips the type-grid
 * step. Add mode calls onAdd(type, config); edit mode calls onSave(config).
 *
 * templateMode + subjectType: pass when this picker is editing a dashboard
 * TEMPLATE's block (see DashboardTemplateManager.jsx) rather than a real
 * dashboard's — enables the "$subject" toggle in renderField.
 */
export default function BlockPicker({ editingBlock = null, onAdd, onSave, onClose, templateMode = false, subjectType = null }) {
  const isEditing = !!editingBlock
  const [catalog, setCatalog] = useState(null)
  const [selected, setSelected] = useState(editingBlock?.type || null)
  const [config, setConfig] = useState(editingBlock?.config || {})

  useEffect(() => {
    if (isEditing) return // no type-grid step to populate in edit mode
    dashboardsApi.catalog().then(setCatalog).catch(() => setCatalog([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function pick(type) {
    setSelected(type)
    setConfig({})
  }

  function submit() {
    if (isEditing) onSave({ ...config })
    else onAdd(selected, { ...config })
  }

  const grouped = (catalog || []).reduce((acc, c) => {
    if (!BLOCK_REGISTRY[c.type]) return acc
    acc[c.category] = acc[c.category] || []
    acc[c.category].push(c)
    return acc
  }, {})

  const fields = (selected ? CONFIG_FIELD_SCHEMAS[selected] || [] : [])
    .filter(f => !f.showIf || config[f.showIf.key] === f.showIf.equals)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">{isEditing ? 'Edit block config' : 'Add block'}</h2>
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
            {fields.map(f => <div key={f.key}>{renderField(f, config, setConfig, templateMode, subjectType)}</div>)}
            {fields.length === 0 && (
              <p className="text-xs text-charcoal-400">No configuration needed — shows your own data.</p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              {!isEditing && <button className="btn-ghost" onClick={() => setSelected(null)}>Back</button>}
              <button className="btn-primary" onClick={submit}>{isEditing ? 'Save changes' : 'Add to dashboard'}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
