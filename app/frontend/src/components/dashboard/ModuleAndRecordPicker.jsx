import { useState } from 'react'
import { ALL_MODULES } from '../../lib/constants'
import TaskPicker from '../TaskPicker'
import EventPicker from '../EventPicker'
import NotePicker from '../NotePicker'
import WorkflowPicker from '../WorkflowPicker'
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

/**
 * Nav-button target picker: stage 1 picks a module (a real app page), stage
 * 2 optionally picks one specific record within it, reusing whichever
 * existing picker that module already has. Writes {module, record_id} as
 * two flat values via onChange(module, recordId) — the caller (BlockPicker's
 * renderField) sets both as top-level config keys directly.
 */
export default function ModuleAndRecordPicker({ value, onChange, label }) {
  const module = value?.module || ''
  const recordId = value?.record_id || null
  const [pickSpecific, setPickSpecific] = useState(!!recordId)

  function setModule(next) {
    setPickSpecific(false)
    onChange(next, null)
  }

  const RecordPicker = RECORD_PICKERS[module]
  const supportsRecord = module === 'contacts' || !!RecordPicker

  return (
    <div className="space-y-2">
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select className="input w-full" value={module} onChange={e => setModule(e.target.value)}>
        <option value="">Choose a page…</option>
        {NAV_MODULE_OPTIONS.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
      </select>

      {module && supportsRecord && (
        <label className="flex items-center gap-2 text-xs text-charcoal-500 dark:text-charcoal-400">
          <input
            type="checkbox"
            checked={pickSpecific}
            onChange={e => { setPickSpecific(e.target.checked); if (!e.target.checked) onChange(module, null) }}
          />
          Go to a specific record instead of the whole page
        </label>
      )}

      {module === 'contacts' && pickSpecific && (
        <ContactPicker
          value={{ contactId: recordId }}
          onChange={(_name, id) => onChange(module, id)}
          placeholder="Search contacts…"
        />
      )}
      {RecordPicker && pickSpecific && (
        <RecordPicker value={recordId} onChange={id => onChange(module, id)} />
      )}
    </div>
  )
}
