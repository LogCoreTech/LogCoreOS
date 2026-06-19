import { useEffect, useState } from 'react'
import { profile as profileApi } from '../lib/api'
import { useNavigate } from 'react-router-dom'

const DEFAULT_PRIORITY_ORDER = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']
const BASE_CATS = ['God', 'Family', 'Job', 'Personal Growth', 'Hobbies']

function Accordion({ title, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 text-left font-semibold hover:bg-charcoal-50 dark:hover:bg-charcoal-800/50 transition-colors"
      >
        <span>{title}</span>
        <span className="text-charcoal-400 text-xs ml-3">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-5 pb-5 pt-4 border-t border-charcoal-100 dark:border-charcoal-800">
          {children}
        </div>
      )}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-1">
        {label}
      </label>
      {children}
    </div>
  )
}

export default function Profile() {
  const navigate = useNavigate()
  const [data, setData] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingSection, setSavingSection] = useState(null)
  const [savedSection, setSavedSection] = useState(null)
  const [error, setError] = useState('')
  const [dragIdx, setDragIdx] = useState(null)
  const [customCat, setCustomCat] = useState('')

  useEffect(() => {
    profileApi.get()
      .then(d => setData(d || {}))
      .catch(() => setError('Could not load profile.'))
      .finally(() => setLoading(false))
  }, [])

  function set(key, value) {
    setData(prev => ({ ...prev, [key]: value }))
  }

  async function save(sectionId) {
    setSavingSection(sectionId)
    setError('')
    try {
      await profileApi.save(data)
      setSavedSection(sectionId)
      setTimeout(() => setSavedSection(null), 2000)
    } catch (e) {
      setError(e.message || 'Save failed.')
    } finally {
      setSavingSection(null)
    }
  }

  const saveBtn = (id) => (
    <button
      onClick={() => save(id)}
      disabled={savingSection === id}
      className={`btn-primary text-sm px-4 mt-4 ${savedSection === id ? 'bg-green-500' : ''}`}
    >
      {savingSection === id ? '…' : savedSection === id ? 'Saved ✓' : 'Save'}
    </button>
  )

  // Life Priorities
  const priorityOrder = data.priority_order || [...DEFAULT_PRIORITY_ORDER]

  function setPriorityOrder(newOrder) {
    setData(prev => ({ ...prev, priority_order: newOrder }))
  }

  function onDragStart(i) { setDragIdx(i) }
  function onDragOver(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) return
    const next = [...priorityOrder]
    const [m] = next.splice(dragIdx, 1)
    next.splice(i, 0, m)
    setPriorityOrder(next)
    setDragIdx(i)
  }
  function onDragEnd() { setDragIdx(null) }

  function addCustomCat() {
    const v = customCat.trim()
    if (v && !priorityOrder.includes(v)) {
      setPriorityOrder([...priorityOrder, v])
      setCustomCat('')
    }
  }

  function removeCustomCat(cat) {
    if (BASE_CATS.includes(cat)) return
    setPriorityOrder(priorityOrder.filter(c => c !== cat))
  }

  // Children (Family section)
  const children = Array.isArray(data.children) ? data.children : []

  function addChild() { set('children', [...children, { name: '', age: '' }]) }
  function updateChild(i, field, value) {
    set('children', children.map((c, idx) => idx === i ? { ...c, [field]: value } : c))
  }
  function removeChild(i) { set('children', children.filter((_, idx) => idx !== i)) }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto space-y-3">
        {[1, 2, 3, 4].map(i => <div key={i} className="h-14 card animate-pulse" />)}
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-3 pb-8">
      <div className="flex items-center gap-3 mb-1">
        <button onClick={() => navigate('/settings')} className="btn-ghost text-sm shrink-0">
          ← Settings
        </button>
        <h1 className="text-2xl font-bold flex-1">Profile</h1>
      </div>
      <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-2">
        Your profile is read by the AI to personalize responses. All fields are optional.
      </p>
      {error && <p className="text-red-500 text-sm">{error}</p>}

      {/* Personal */}
      <Accordion title="Personal">
        <Field label="Date of Birth">
          <input type="date" value={data.dob || ''} onChange={e => set('dob', e.target.value)} className="input" />
        </Field>
        <Field label="Pronouns">
          <input type="text" value={data.pronouns || ''} onChange={e => set('pronouns', e.target.value)} placeholder="e.g. he/him" className="input" />
        </Field>
        <Field label="Phone">
          <input type="tel" value={data.phone || ''} onChange={e => set('phone', e.target.value)} placeholder="+1 555-000-0000" className="input" />
        </Field>
        <Field label="City">
          <input type="text" value={data.city || ''} onChange={e => set('city', e.target.value)} className="input" />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="State / Province">
            <input type="text" value={data.state || ''} onChange={e => set('state', e.target.value)} className="input" />
          </Field>
          <Field label="Country">
            <input type="text" value={data.country || ''} onChange={e => set('country', e.target.value)} className="input" />
          </Field>
        </div>
        {saveBtn('personal')}
      </Accordion>

      {/* Daily Routine */}
      <Accordion title="Daily Routine">
        <div className="grid grid-cols-2 gap-2">
          <Field label="Weekday Wake Time">
            <input type="text" value={data.wake_weekday || ''} onChange={e => set('wake_weekday', e.target.value)} placeholder="6:00 AM" className="input" />
          </Field>
          <Field label="Weekend Wake Time">
            <input type="text" value={data.wake_weekend || ''} onChange={e => set('wake_weekend', e.target.value)} placeholder="8:00 AM" className="input" />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Bedtime">
            <input type="text" value={data.bedtime || ''} onChange={e => set('bedtime', e.target.value)} placeholder="10:30 PM" className="input" />
          </Field>
          <Field label="Work Hours">
            <input type="text" value={data.work_hours || ''} onChange={e => set('work_hours', e.target.value)} placeholder="8 AM – 5 PM" className="input" />
          </Field>
        </div>
        {saveBtn('routine')}
      </Accordion>

      {/* Health */}
      <Accordion title="Health">
        <div className="grid grid-cols-2 gap-2">
          <Field label="Height">
            <input type="text" value={data.height || ''} onChange={e => set('height', e.target.value)} placeholder="5'11&quot;" className="input" />
          </Field>
          <Field label="Weight">
            <input type="text" value={data.weight || ''} onChange={e => set('weight', e.target.value)} placeholder="175 lbs" className="input" />
          </Field>
        </div>
        <Field label="Blood Type">
          <input type="text" value={data.blood_type || ''} onChange={e => set('blood_type', e.target.value)} placeholder="A+" className="input" />
        </Field>
        <Field label="Conditions">
          <textarea value={data.conditions || ''} onChange={e => set('conditions', e.target.value)} rows={2} placeholder="Diabetes, hypertension…" className="input" />
        </Field>
        <Field label="Medications">
          <textarea value={data.medications || ''} onChange={e => set('medications', e.target.value)} rows={2} placeholder="Metformin…" className="input" />
        </Field>
        <Field label="Dietary Restrictions">
          <input type="text" value={data.diet || ''} onChange={e => set('diet', e.target.value)} placeholder="No shellfish" className="input" />
        </Field>
        <Field label="Exercise Frequency">
          <input type="text" value={data.exercise || ''} onChange={e => set('exercise', e.target.value)} placeholder="3x per week" className="input" />
        </Field>
        {saveBtn('health')}
      </Accordion>

      {/* Work & Career */}
      <Accordion title="Work & Career">
        <Field label="Occupation">
          <input type="text" value={data.occupation || ''} onChange={e => set('occupation', e.target.value)} className="input" />
        </Field>
        <Field label="Employer">
          <input type="text" value={data.employer || ''} onChange={e => set('employer', e.target.value)} className="input" />
        </Field>
        <Field label="Industry">
          <input type="text" value={data.industry || ''} onChange={e => set('industry', e.target.value)} className="input" />
        </Field>
        <Field label="Education">
          <input type="text" value={data.education || ''} onChange={e => set('education', e.target.value)} placeholder="Trade school, Bachelor's…" className="input" />
        </Field>
        <Field label="Years of Experience">
          <input type="text" value={data.years_experience || ''} onChange={e => set('years_experience', e.target.value)} placeholder="10" className="input" />
        </Field>
        <Field label="Key Skills (comma-separated)">
          <input type="text" value={data.skills || ''} onChange={e => set('skills', e.target.value)} placeholder="Python, public speaking…" className="input" />
        </Field>
        {saveBtn('work')}
      </Accordion>

      {/* Family */}
      <Accordion title="Family">
        <Field label="Marital Status">
          <select value={data.marital_status || ''} onChange={e => set('marital_status', e.target.value)} className="input">
            <option value="">—</option>
            {['Single', 'Married', 'Divorced', 'Widowed', 'Partnered'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </Field>
        <Field label="Partner Name">
          <input type="text" value={data.partner || ''} onChange={e => set('partner', e.target.value)} className="input" />
        </Field>
        <Field label="Children">
          <div className="space-y-2">
            {children.map((child, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input
                  type="text"
                  value={child.name || ''}
                  onChange={e => updateChild(i, 'name', e.target.value)}
                  placeholder="Name"
                  className="input flex-1"
                />
                <input
                  type="text"
                  value={child.age || ''}
                  onChange={e => updateChild(i, 'age', e.target.value)}
                  placeholder="Age"
                  className="input w-20"
                />
                <button
                  onClick={() => removeChild(i)}
                  className="text-charcoal-400 hover:text-red-500 text-sm px-1"
                >✕</button>
              </div>
            ))}
            <button
              onClick={addChild}
              className="text-sm text-orange-500 hover:text-orange-600 font-medium"
            >
              + Add child
            </button>
          </div>
        </Field>
        <Field label="Pets">
          <input type="text" value={data.pets || ''} onChange={e => set('pets', e.target.value)} placeholder="Golden Retriever, 2 cats…" className="input" />
        </Field>
        {saveBtn('family')}
      </Accordion>

      {/* Finances */}
      <Accordion title="Finances">
        <Field label="Income Range">
          <select value={data.income_range || ''} onChange={e => set('income_range', e.target.value)} className="input">
            <option value="">—</option>
            {['Under $25k', '$25k–$50k', '$50k–$75k', '$75k–$100k', '$100k–$150k', '$150k–$200k', '$200k+'].map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </Field>
        <Field label="Savings Goal">
          <input type="text" value={data.savings_goal || ''} onChange={e => set('savings_goal', e.target.value)} placeholder="Emergency fund, house down payment…" className="input" />
        </Field>
        <Field label="Budget Style">
          <select value={data.budget_style || ''} onChange={e => set('budget_style', e.target.value)} className="input">
            <option value="">—</option>
            {['Frugal', 'Moderate', 'Comfortable', 'Flexible'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </Field>
        {saveBtn('finances')}
      </Accordion>

      {/* Goals & Values */}
      <Accordion title="Goals & Values">
        <Field label="Life Mission">
          <textarea value={data.life_mission || ''} onChange={e => set('life_mission', e.target.value)} rows={2} placeholder="To glorify God through…" className="input" />
        </Field>
        <Field label="Big Long-term Goal">
          <input type="text" value={data.big_goal || ''} onChange={e => set('big_goal', e.target.value)} placeholder="Pay off house by 2030" className="input" />
        </Field>
        <Field label="Core Values (comma-separated)">
          <input type="text" value={data.core_values || ''} onChange={e => set('core_values', e.target.value)} placeholder="Faith, integrity, family" className="input" />
        </Field>
        <Field label="Key Constraints">
          <textarea value={data.key_constraints || ''} onChange={e => set('key_constraints', e.target.value)} rows={2} placeholder="Limited childcare, work travel…" className="input" />
        </Field>
        {saveBtn('values')}
      </Accordion>

      {/* Life Priorities */}
      <Accordion title="Life Priorities">
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Drag to reorder. This determines how tasks are scored and surfaced by the AI.
        </p>
        <ul className="space-y-2 mb-3">
          {priorityOrder.map((cat, i) => (
            <li
              key={cat}
              draggable
              onDragStart={() => onDragStart(i)}
              onDragOver={e => onDragOver(e, i)}
              onDragEnd={onDragEnd}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                dragIdx === i
                  ? 'border-orange-500 bg-orange-500/10'
                  : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
              }`}
            >
              <span className="text-charcoal-400 text-xs w-4">{i + 1}</span>
              <span className="flex-1 text-sm">{cat}</span>
              {!BASE_CATS.includes(cat) && (
                <button
                  onClick={() => removeCustomCat(cat)}
                  className="text-charcoal-400 hover:text-red-500 text-xs"
                >✕</button>
              )}
              <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
            </li>
          ))}
        </ul>
        <div className="flex gap-2 mb-1">
          <input
            type="text"
            value={customCat}
            onChange={e => setCustomCat(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addCustomCat()}
            placeholder="Add category…"
            className="input"
          />
          <button onClick={addCustomCat} className="btn-primary px-3">+</button>
        </div>
        {saveBtn('priorities')}
      </Accordion>

      {/* AI Preferences */}
      <Accordion title="AI Preferences">
        <Field label="Communication Style">
          <select value={data.communication_style || ''} onChange={e => set('communication_style', e.target.value)} className="input">
            <option value="">—</option>
            {['Concise', 'Balanced', 'Detailed'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </Field>
        <Field label="Tone">
          <input type="text" value={data.tone || ''} onChange={e => set('tone', e.target.value)} placeholder="Encouraging, professional…" className="input" />
        </Field>
        <Field label="Response Language">
          <input type="text" value={data.response_language || ''} onChange={e => set('response_language', e.target.value)} placeholder="English" className="input" />
        </Field>
        <Field label="Topics to Emphasize">
          <textarea value={data.topics_to_emphasize || ''} onChange={e => set('topics_to_emphasize', e.target.value)} rows={2} placeholder="Faith, family time…" className="input" />
        </Field>
        <Field label="Things to Avoid">
          <textarea value={data.topics_to_avoid || ''} onChange={e => set('topics_to_avoid', e.target.value)} rows={2} placeholder="Politics, profanity…" className="input" />
        </Field>
        {saveBtn('ai')}
      </Accordion>

      {/* Personal Notes */}
      <Accordion title="Personal Notes">
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Anything else the AI should know about you.
        </p>
        <textarea
          value={data.notes || ''}
          onChange={e => set('notes', e.target.value)}
          rows={6}
          className="input w-full font-mono text-sm"
          placeholder="I work early mornings, prefer direct advice, am building a business on the side…"
        />
        {saveBtn('notes')}
      </Accordion>
    </div>
  )
}
