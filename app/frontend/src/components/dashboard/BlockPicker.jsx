import { useEffect, useState } from 'react'
import { dashboards as dashboardsApi } from '../../lib/api'
import { BLOCK_REGISTRY, CONFIG_FIELD_SCHEMAS } from './blockRegistry'
import { ACTION_PRESETS_BY_KIND } from './actionKinds'
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
import TemplatePicker from './TemplatePicker'
import TemplateFieldsPicker from './TemplateFieldsPicker'

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
    case 'assetTemplate':
      return <TemplatePicker label={label} value={val} onChange={set} />
    case 'templateFields':
      return (
        <TemplateFieldsPicker
          label={label}
          templateId={config[f.dependsOn]}
          value={val}
          onChange={set}
        />
      )
    case 'templateSelectField':
      return (
        <AssetSelectFieldPicker
          label={label}
          templateId={config[f.dependsOn]}
          value={val}
          onChange={set}
        />
      )
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

// A user-built repeater of block-embedded action buttons (config.actions —
// see actionKinds.js). Deliberately not a fully free-form composer: each
// block's recordKind (blockRegistry.js) already fixes what an "Open" button
// means (the record's own page) and which status presets make sense, so the
// picker only ever asks for the parts that actually vary — which preset, and
// an optional label override — mirroring LocationsEditor's plain add/remove/
// edit repeater shape (ContactModal.jsx) rather than TemplateManager's fuller
// per-field composer, since there's no free-typed "key" here to define.
function ActionsEditor({ config, setConfig, recordKind }) {
  const actions = config.actions || []
  const presets = ACTION_PRESETS_BY_KIND[recordKind] || []

  function update(i, patch) {
    setConfig({ ...config, actions: actions.map((a, j) => (j === i ? { ...a, ...patch } : a)) })
  }
  function remove(i) {
    setConfig({ ...config, actions: actions.filter((_, j) => j !== i) })
  }
  function add(kind) {
    const base = kind === 'status' ? { kind, preset: presets[0]?.value } : { kind: 'nav' }
    setConfig({ ...config, actions: [...actions, base] })
  }

  return (
    <div>
      <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Buttons on this block</label>
      <div className="space-y-2 mt-1">
        {actions.map((a, i) => (
          <div key={i} className="flex items-center gap-1.5 border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-2">
            <select
              value={a.kind}
              onChange={e => update(i, e.target.value === 'status' ? { kind: 'status', preset: presets[0]?.value } : { kind: 'nav', preset: undefined })}
              className="input !py-1 !w-24 text-xs shrink-0"
            >
              <option value="nav">Open</option>
              {presets.length > 0 && <option value="status">Status</option>}
            </select>
            {a.kind === 'status' && (
              <select value={a.preset || ''} onChange={e => update(i, { preset: e.target.value })} className="input !py-1 !w-32 text-xs shrink-0">
                {presets.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            )}
            <input
              type="text"
              value={a.label || ''}
              onChange={e => update(i, { label: e.target.value })}
              placeholder="Button label (optional)"
              className="input !py-1 flex-1 text-xs min-w-0"
            />
            <button type="button" onClick={() => remove(i)} className="text-red-400 hover:text-red-500 px-0.5 shrink-0">✕</button>
          </div>
        ))}
        <div className="flex gap-2">
          <button type="button" onClick={() => add('nav')} className="btn-ghost text-xs px-2 py-1">＋ Open button</button>
          {presets.length > 0 && (
            <button type="button" onClick={() => add('status')} className="btn-ghost text-xs px-2 py-1">＋ Status button</button>
          )}
        </div>
      </div>
    </div>
  )
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
  const [query, setQuery] = useState('')

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

  const q = query.trim().toLowerCase()
  const grouped = (catalog || []).reduce((acc, c) => {
    if (!BLOCK_REGISTRY[c.type]) return acc
    if (q && !BLOCK_REGISTRY[c.type].label.toLowerCase().includes(q)) return acc
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
          <div className="space-y-4">
            {catalog !== null && catalog.length > 0 && (
              <input
                className="input w-full"
                placeholder="Search blocks…"
                value={query}
                onChange={e => setQuery(e.target.value)}
                autoFocus
              />
            )}
            <div className="space-y-4 max-h-[55vh] overflow-y-auto">
            {catalog === null && <p className="text-sm text-charcoal-400">Loading…</p>}
            {catalog !== null && Object.keys(grouped).length === 0 && (
              <p className="text-sm text-charcoal-400">No blocks match &quot;{query}&quot;.</p>
            )}
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
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium">{BLOCK_REGISTRY[selected].icon} {BLOCK_REGISTRY[selected].label}</p>
            {fields.map(f => <div key={f.key}>{renderField(f, config, setConfig, templateMode, subjectType)}</div>)}
            {BLOCK_REGISTRY[selected].recordKind && (
              <ActionsEditor config={config} setConfig={setConfig} recordKind={BLOCK_REGISTRY[selected].recordKind} />
            )}
            {fields.length === 0 && !BLOCK_REGISTRY[selected].recordKind && (
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
