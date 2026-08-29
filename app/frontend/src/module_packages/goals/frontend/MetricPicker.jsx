import { useEffect, useState } from 'react'
import { goals as goalsApi } from './api'
import ContactPicker from '../../../components/contacts/ContactPicker'
import FinanceBookPicker from '../../../components/finance/FinanceBookPicker'
import ContactNumberFieldPicker from '../../../components/dashboard/ContactNumberFieldPicker'

// Dispatches one metric-provider config field to its real picker, by `kind`
// — the same dispatch shape BlockPicker.jsx's renderField already
// established for dashboard blocks, kept as its own small local copy here
// rather than trying to export/reuse that file's internal (unexported)
// function for an unrelated config shape.
function renderConfigField(f, config, setConfig) {
  const val = config[f.key]
  const set = v => setConfig({ ...config, [f.key]: v })
  const label = f.optional ? `${f.label} (optional)` : f.label

  switch (f.kind) {
    case 'contact':
      return (
        <ContactPicker
          label={label}
          value={{ contactId: val }}
          onChange={(_name, id) => set(id)}
          placeholder="Search contacts… (leave blank for your own profile)"
        />
      )
    case 'financeBook':
      return <FinanceBookPicker label={label} value={val} onChange={set} optional={f.optional} />
    case 'contactNumberField':
      return <ContactNumberFieldPicker label={label} value={val} onChange={set} />
    case 'number':
      return (
        <div>
          <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>
          <input
            type="number"
            className="input w-full"
            value={val ?? ''}
            onChange={e => set(e.target.value === '' ? null : Number(e.target.value))}
          />
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
 * Props: value (goal's `metric` object, or null/undefined), onChange(metric|null)
 */
export default function MetricPicker({ value, onChange }) {
  const [providers, setProviders] = useState(null)

  useEffect(() => {
    goalsApi.metricProviders().then(setProviders).catch(() => setProviders([]))
  }, [])

  const selectedKey = value?.provider || ''
  const selectedProvider = (providers || []).find(p => p.key === selectedKey)
  const config = value?.config || {}

  function pickProvider(key) {
    if (!key) { onChange(null); return }
    onChange({ provider: key, config: {}, history: key === 'manual' ? [] : undefined })
  }

  function setConfig(newConfig) {
    onChange({ ...value, config: newConfig })
  }

  return (
    <div className="space-y-2">
      <label className="text-xs text-charcoal-500 dark:text-charcoal-400">
        Metric (optional — drives progress automatically instead of a manual checkbox)
      </label>
      <select className="input w-full" value={selectedKey} onChange={e => pickProvider(e.target.value)}>
        <option value="">No metric — manual / based on subgoals &amp; tasks</option>
        {(providers || []).map(p => <option key={p.key} value={p.key}>{p.label}</option>)}
      </select>
      {selectedProvider && (
        <div className="space-y-2 pl-3 border-l-2 border-charcoal-200 dark:border-charcoal-700">
          {selectedProvider.config_schema.map(f => (
            <div key={f.key}>{renderConfigField(f, config, setConfig)}</div>
          ))}
        </div>
      )}
    </div>
  )
}
