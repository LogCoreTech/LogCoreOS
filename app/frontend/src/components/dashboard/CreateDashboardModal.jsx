import { useEffect, useState } from 'react'
import { dashboardTemplates as templatesApi, dashboards as dashboardsApi } from '../../lib/api'
import EmojiPicker from '../EmojiPicker'
import ContactPicker from '../contacts/ContactPicker'
import AssetPickerField from '../AssetPickerField'

/**
 * Blank dashboard, or one seeded from a template — replaces the old direct
 * `dashboardsApi.create('New Dashboard', '📊')` calls in Dashboard.jsx's empty
 * state and DashboardSwitcher.jsx's "+ New Dashboard". Templates aren't
 * mandatory (owner: "just an easy way to make the same dashboard"), so
 * "Start blank" stays a first-class, equally-easy option here, not buried.
 */
export default function CreateDashboardModal({ pool = false, onCreated, onClose }) {
  const [templates, setTemplates] = useState([])
  const [template, setTemplate] = useState(null) // null = blank
  const [step, setStep] = useState('choose') // choose | details
  const [name, setName] = useState('New Dashboard')
  const [icon, setIcon] = useState('📊')
  const [subjectId, setSubjectId] = useState(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    templatesApi.list().then(setTemplates).catch(() => setTemplates([]))
  }, [])

  function pickBlank() {
    setTemplate(null)
    setName('New Dashboard')
    setIcon('📊')
    setSubjectId(null)
    setStep('details')
  }

  function pickTemplate(t) {
    setTemplate(t)
    setName(t.label)
    setIcon(t.icon || '📊')
    setSubjectId(null)
    setStep('details')
  }

  const needsSubject = !!template?.subject_type
  const canCreate = name.trim() && (!needsSubject || subjectId)

  async function create() {
    if (!canCreate) return
    setCreating(true); setError('')
    try {
      const dashboard = await dashboardsApi.create(
        name.trim(), icon, pool, template?.id || null, needsSubject ? subjectId : null
      )
      onCreated(dashboard)
    } catch (e) {
      setError(e.message || 'Failed to create dashboard')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">New Dashboard</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
        </div>

        {step === 'choose' && (
          <div className="space-y-4">
            <button
              onClick={pickBlank}
              className="w-full text-left p-3 rounded-lg border border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400 flex items-center gap-2"
            >
              <span className="text-lg">📄</span>
              <div>
                <p className="text-sm font-medium">Start blank</p>
                <p className="text-xs text-charcoal-400">Add and arrange blocks yourself</p>
              </div>
            </button>

            {templates.length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-wide text-charcoal-400 mb-2">Or from a template</p>
                <div className="space-y-1.5 max-h-[40vh] overflow-y-auto">
                  {templates.map(t => (
                    <button
                      key={t.id}
                      onClick={() => pickTemplate(t)}
                      className="w-full text-left p-2 rounded-lg border border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400 flex items-center gap-2"
                    >
                      <span>{t.icon || '📊'}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{t.label}</p>
                        <p className="text-[10px] text-charcoal-400">
                          {(t.blocks || []).length} block{(t.blocks || []).length !== 1 ? 's' : ''}
                          {t.subject_type ? ` · pick a ${t.subject_type}` : ''}
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {step === 'details' && (
          <div className="space-y-4">
            <div className="flex gap-3 items-end">
              <div className="w-24 shrink-0">
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Icon</label>
                <EmojiPicker value={icon} onChange={setIcon} />
              </div>
              <div className="flex-1 min-w-0">
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Name</label>
                <input className="input w-full" value={name} onChange={e => setName(e.target.value)} maxLength={80} autoFocus />
              </div>
            </div>

            {needsSubject && template.subject_type === 'contact' && (
              <ContactPicker
                label="Which contact is this dashboard for?"
                value={{ contactId: subjectId }}
                onChange={(_name, id) => setSubjectId(id)}
                placeholder="Search contacts…"
              />
            )}
            {needsSubject && template.subject_type === 'asset' && (
              <AssetPickerField
                label="Which asset is this dashboard for?"
                value={subjectId}
                onChange={setSubjectId}
              />
            )}

            {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}
            <div className="flex gap-2 pt-1">
              <button className="btn-ghost flex-1" onClick={() => setStep('choose')}>Back</button>
              <button className="btn-primary flex-1" onClick={create} disabled={!canCreate || creating}>
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
