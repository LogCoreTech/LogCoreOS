import { useState } from 'react'
import { ALL_MODULES } from '../../lib/constants'
import { MODULE_SECTIONS } from '../../lib/deepLinks'
import { useAuth } from '../../lib/auth'
import TaskPicker from '../TaskPicker'
import EventPicker from '../EventPicker'
import NotePicker from '../NotePicker'
import AssetPickerField from '../AssetPickerField'
import FinanceBookPicker from '../finance/FinanceBookPicker'
import ContactPicker from '../contacts/ContactPicker'

// Modules with an existing single-record picker component. Automations has
// no per-workflow detail page to land on yet, so workflow-specific deep
// links aren't offered even though a WorkflowPicker exists — module-page-only
// for that one until Automations.jsx has somewhere to land a specific id.
const RECORD_PICKERS = {
  tasks: TaskPicker,
  calendar: EventPicker,
  notes: NotePicker,
  assets: AssetPickerField,
  finance: FinanceBookPicker,
}

const NAV_MODULE_OPTIONS = ALL_MODULES.filter(m => m.to)

// Settings isn't a real module (no ALL_MODULES entry, no require_module
// gate, no record concept at all) but it's the page with by far the most
// worthwhile sub-sections to jump straight to — added as a hand-picked
// extra option here rather than in ALL_MODULES, which drives unrelated
// things (sidebar nav, per-user module toggles) that Settings has no part in.
const SETTINGS_OPTION = { id: 'settings', icon: '⚙️', label: 'Settings' }

/**
 * Nav-button target picker: stage 1 picks a module (a real app page, or
 * Settings), stage 2 optionally narrows to a specific section/sub-page
 * (for modules in MODULE_SECTIONS) or a specific record (reusing whichever
 * existing picker that module already has) — mutually exclusive, since a
 * button that goes to a specific record vs. a specific tab are two
 * different, simpler questions rather than one combined picker. Writes
 * {module, record_id, section} via onChange(module, recordId, section) —
 * the caller (BlockPicker's renderField) sets all three as flat config keys.
 */
export default function ModuleAndRecordPicker({ value, onChange, label }) {
  const { user } = useAuth()
  const module = value?.module || ''
  const recordId = value?.record_id || null
  const section = value?.section || null
  const [mode, setMode] = useState(section ? 'section' : recordId ? 'record' : 'page')

  function setModule(next) {
    setMode('page')
    onChange(next, null, null)
  }

  function setMode_(next) {
    setMode(next)
    onChange(module, null, null)
  }

  const RecordPicker = RECORD_PICKERS[module]
  const supportsRecord = module === 'contacts' || !!RecordPicker
  const sections = (MODULE_SECTIONS[module] || []).filter(s => !s.adminOnly || user?.role === 'admin')
  const supportsSection = sections.length > 0

  return (
    <div className="space-y-2">
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select className="input w-full" value={module} onChange={e => setModule(e.target.value)}>
        <option value="">Choose a page…</option>
        {NAV_MODULE_OPTIONS.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
        <option value={SETTINGS_OPTION.id}>{SETTINGS_OPTION.icon} {SETTINGS_OPTION.label}</option>
      </select>

      {module && (supportsSection || supportsRecord) && (
        <select className="input w-full" value={mode} onChange={e => setMode_(e.target.value)}>
          <option value="page">Go to the whole page</option>
          {supportsSection && <option value="section">Go to a specific section</option>}
          {supportsRecord && <option value="record">Go to a specific record</option>}
        </select>
      )}

      {mode === 'section' && supportsSection && (
        <select
          className="input w-full"
          value={section || ''}
          onChange={e => onChange(module, null, e.target.value)}
        >
          <option value="">Choose a section…</option>
          {sections.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      )}

      {mode === 'record' && module === 'contacts' && (
        <ContactPicker
          value={{ contactId: recordId }}
          onChange={(_name, id) => onChange(module, id, null)}
          placeholder="Search contacts…"
        />
      )}
      {mode === 'record' && RecordPicker && (
        <RecordPicker value={recordId} onChange={id => onChange(module, id, null)} />
      )}
    </div>
  )
}
