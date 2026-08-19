import { useState, useEffect } from 'react'
import { contacts as contactsApi } from '../../lib/api'
import { useWorkspace } from '../../lib/workspace'
import ContactPicker from './ContactPicker'
import { useContactPhotoUrl } from './ContactAvatar'
import TagInput from '../TagInput'
import SectionHeader from './SectionHeader'

const DEFAULT_PRIORITY_ORDER = ['Religion', 'Family', 'Job', 'Personal Growth', 'Hobbies']
const EDUCATION_LEVELS = [
  'Junior High', 'High School', 'Some College', 'Trade/Vocational School',
  "Associate's Degree", "Bachelor's Degree", "Master's Degree", 'Doctorate', 'Other',
]
const EXPERIENCE_LEVELS = [
  'Less than 1 year', '1-2 years', '3-5 years', '6-10 years', '11-15 years', '16-20 years', '20+ years',
]
const BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'Unknown']
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function Field({ label, children }) {
  return (
    <label className="block text-xs text-charcoal-500 dark:text-charcoal-400">{label}
      {children}
    </label>
  )
}

function formatPhoneNumber(digits) {
  const d = (digits || '').slice(0, 10)
  if (d.length <= 3) return d
  if (d.length <= 6) return `${d.slice(0, 3)}-${d.slice(3)}`
  return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`
}

// Multiple phone numbers, each with country code + auto-formatted local
// number (digits only, capped to 10) + optional extension.
function PhoneEditor({ phones, onChange }) {
  function update(i, patch) {
    onChange(phones.map((p, idx) => (idx === i ? { ...p, ...patch } : p)))
  }
  function remove(i) {
    onChange(phones.filter((_, idx) => idx !== i))
  }
  function add() {
    onChange([...phones, { country_code: '1', number: '', extension: '' }])
  }
  return (
    <div className="space-y-2">
      {phones.map((p, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input className="input !w-14 shrink-0 text-center" placeholder="1" maxLength={3}
            value={p.country_code || ''}
            onChange={e => update(i, { country_code: e.target.value.replace(/\D/g, '').slice(0, 3) })} />
          <input className="input flex-1 min-w-0" placeholder="555-123-4567"
            value={formatPhoneNumber(p.number)}
            onChange={e => update(i, { number: e.target.value.replace(/\D/g, '').slice(0, 10) })} />
          <input className="input !w-16 shrink-0" placeholder="ext." maxLength={6}
            value={p.extension || ''}
            onChange={e => update(i, { extension: e.target.value.replace(/\D/g, '').slice(0, 6) })} />
          <button type="button" onClick={() => remove(i)} className="text-charcoal-400 hover:text-red-500 text-sm px-1 shrink-0">✕</button>
        </div>
      ))}
      <button type="button" onClick={add} className="text-sm text-orange-500 hover:text-orange-600 font-medium">+ Add phone</button>
    </div>
  )
}

// Profile/contact photo — shows at the top of the read card in place of the
// type/gender icon when present. Uploads immediately (dedicated endpoint,
// like affiliations) rather than deferring to form save.
function PhotoUploader({ contactId, photoExt, onChanged }) {
  const [busy, setBusy] = useState(false)
  const previewUrl = useContactPhotoUrl(contactId, photoExt)

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !contactId) return
    setBusy(true)
    try { await contactsApi.uploadPhoto(contactId, file); onChanged() } catch { /* ignore */ } finally { setBusy(false) }
  }

  async function handleRemove() {
    if (!contactId) return
    setBusy(true)
    try { await contactsApi.removePhoto(contactId); onChanged() } catch { /* ignore */ } finally { setBusy(false) }
  }

  if (!contactId) {
    return <p className="text-xs text-charcoal-400">Save this contact first to add a photo.</p>
  }

  return (
    <div className="flex items-center gap-3">
      {previewUrl ? (
        <img src={previewUrl} alt="" className="w-16 h-16 rounded-full object-cover shrink-0" />
      ) : (
        <div className="w-16 h-16 rounded-full bg-charcoal-100 dark:bg-charcoal-800 flex items-center justify-center text-2xl shrink-0">🧑</div>
      )}
      <div className="flex flex-col gap-1 min-w-0">
        <label className="btn-ghost text-xs px-3 py-1.5 inline-block cursor-pointer w-fit">
          {busy ? 'Uploading…' : previewUrl ? 'Change photo' : 'Upload photo'}
          <input type="file" accept="image/jpeg,image/png,image/webp,image/avif" onChange={handleUpload} className="hidden" disabled={busy} />
        </label>
        {previewUrl && (
          <button type="button" onClick={handleRemove} disabled={busy} className="text-xs text-red-500 text-left">Remove photo</button>
        )}
      </div>
    </div>
  )
}

// Affiliated-contacts editor — a general bidirectional Contact<->Contact link
// (family, company<->person, etc.), not partner/children-typed. Mutations are
// dedicated endpoints (not part of the general PATCH), so they only work once
// the contact being edited already has an id.
function AffiliationEditor({ contactId, affiliated, onChange }) {
  const [picked, setPicked] = useState({ name: '', contactId: null })
  const [busy, setBusy] = useState(false)

  async function add() {
    if (!picked.contactId || picked.contactId === contactId) return
    setBusy(true)
    try {
      // The endpoint returns the updated contact object itself, not a tuple —
      // destructuring it as an array here used to throw (objects aren't
      // iterable), silently swallowed below, so the link succeeded server-side
      // but the pill never appeared until the whole modal was reopened.
      const updated = await contactsApi.linkAffiliation(contactId, picked.contactId)
      onChange(updated.affiliated_contact_ids || [])
      setPicked({ name: '', contactId: null })
    } catch { /* ignore */ } finally { setBusy(false) }
  }

  async function remove(otherId) {
    try {
      const updated = await contactsApi.unlinkAffiliation(contactId, otherId)
      onChange(updated.affiliated_contact_ids || [])
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-2">
      {affiliated.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {affiliated.map(a => (
            <span key={a.id} className="badge bg-charcoal-100 dark:bg-charcoal-700 flex items-center gap-1">
              {a.type === 'company' ? '🏢' : '🧑'} {a.name}
              <button type="button" onClick={() => remove(a.id)} className="text-red-500" title="Unlink">×</button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2 items-end">
        <div className="flex-1 min-w-0">
          <ContactPicker value={picked} onChange={(name, id) => setPicked({ name, contactId: id })} placeholder="Link a family member, company…" />
        </div>
        <button type="button" onClick={add} disabled={busy || !picked.contactId} className="btn-ghost text-xs shrink-0">＋ Link</button>
      </div>
    </div>
  )
}

// Resume-style career history: exactly one "current" (non-archived) entry is
// editable inline; "Archive" ends it (sets end_date, marks archived) and
// opens a fresh blank current entry. Past entries can *also* be added
// directly with their own real dates (not just produced by archiving
// "current"), and edited after the fact — owner, 2026-08-18: "put old one[s]
// and order them off dates" — rather than only ever appending a blank
// "current" and read-only-summarizing everything before it. Past roles
// display most-recent-first by start_date; the backend doesn't care about
// array order (see contacts_service._validate_career_history's own
// docstring), so this is purely a display-time sort.
function CareerHistoryEditor({ career, onChange }) {
  const [companyNames, setCompanyNames] = useState({})
  useEffect(() => {
    contactsApi.list().then(r => {
      const all = Array.isArray(r) ? r : []
      setCompanyNames(Object.fromEntries(all.map(c => [c.id, c.name])))
    }).catch(() => {})
  }, [])

  const current = career.find(c => !c.archived)
  const past = [...career.filter(c => c.archived)].sort((a, b) => (b.start_date || '').localeCompare(a.start_date || ''))
  const cur = current || {}
  // A single past entry being drafted (no `id` yet) or edited (has one) —
  // separate from the always-present current-entry form above it.
  const [editingPast, setEditingPast] = useState(null)

  function updateCurrent(patch) {
    if (current) {
      onChange(career.map(c => (c === current ? { ...c, ...patch } : c)))
    } else {
      onChange([...career, { title: '', archived: false, ...patch }])
    }
  }

  function archiveCurrent() {
    if (!current || !current.title?.trim()) return
    const today = new Date().toISOString().slice(0, 7)
    onChange([
      ...career.map(c => (c === current ? { ...c, end_date: today, archived: true } : c)),
      { title: '', archived: false, start_date: today },
    ])
  }

  function removePast(entry) {
    onChange(career.filter(c => c !== entry))
    if (editingPast === entry) setEditingPast(null)
  }

  function savePast() {
    if (!editingPast.title?.trim()) return
    if (editingPast.id) {
      onChange(career.map(c => (c.id === editingPast.id ? editingPast : c)))
    } else {
      onChange([...career, { ...editingPast, id: crypto.randomUUID(), archived: true }])
    }
    setEditingPast(null)
  }

  function pastField(patch) {
    setEditingPast(p => ({ ...p, ...patch }))
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-charcoal-400">{current ? 'Current role' : 'Add a role'}</p>
      <input className="input" placeholder="Job title" value={cur.title || ''} onChange={e => updateCurrent({ title: e.target.value })} />
      <ContactPicker
        label="Employer"
        value={{ name: companyNames[cur.company_id] || '', contactId: cur.company_id || null }}
        onChange={(_n, id) => updateCurrent({ company_id: id })}
        placeholder="Search or add a company…"
      />
      <div className="grid grid-cols-2 gap-3">
        <input className="input" placeholder="Industry" value={cur.industry || ''} onChange={e => updateCurrent({ industry: e.target.value })} />
        <select className="input" value={cur.education || ''} onChange={e => updateCurrent({ education: e.target.value })}>
          <option value="">Education —</option>
          {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <select className="input" value={cur.years_experience || ''} onChange={e => updateCurrent({ years_experience: e.target.value })}>
          <option value="">Experience —</option>
          {EXPERIENCE_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <Field label="Started">
          <input type="month" className="input" value={cur.start_date || ''} onChange={e => updateCurrent({ start_date: e.target.value })} />
        </Field>
      </div>
      <input className="input" placeholder="Skills (comma-separated)" value={cur.skills || ''} onChange={e => updateCurrent({ skills: e.target.value })} />
      <div className="flex gap-2 flex-wrap">
        {current && (
          <button type="button" onClick={archiveCurrent} className="btn-ghost text-xs">
            📁 Archive this role &amp; start a new one
          </button>
        )}
        {!editingPast && (
          <button type="button" onClick={() => setEditingPast({ archived: true })} className="btn-ghost text-xs">
            + Add a past role
          </button>
        )}
      </div>

      {editingPast && (
        <div className="space-y-2 p-2.5 rounded-lg border border-charcoal-200 dark:border-charcoal-700">
          <p className="text-[11px] text-charcoal-400">{editingPast.id ? 'Edit past role' : 'New past role'}</p>
          <input className="input" placeholder="Job title" value={editingPast.title || ''} onChange={e => pastField({ title: e.target.value })} />
          <ContactPicker
            label="Employer"
            value={{ name: companyNames[editingPast.company_id] || '', contactId: editingPast.company_id || null }}
            onChange={(_n, id) => pastField({ company_id: id })}
            placeholder="Search or add a company…"
          />
          <div className="grid grid-cols-2 gap-3">
            <input className="input" placeholder="Industry" value={editingPast.industry || ''} onChange={e => pastField({ industry: e.target.value })} />
            <select className="input" value={editingPast.education || ''} onChange={e => pastField({ education: e.target.value })}>
              <option value="">Education —</option>
              {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
            <select className="input" value={editingPast.years_experience || ''} onChange={e => pastField({ years_experience: e.target.value })}>
              <option value="">Experience —</option>
              {EXPERIENCE_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
            <Field label="Started">
              <input type="month" className="input" value={editingPast.start_date || ''} onChange={e => pastField({ start_date: e.target.value })} />
            </Field>
            <Field label="Ended">
              <input type="month" className="input" value={editingPast.end_date || ''} onChange={e => pastField({ end_date: e.target.value })} />
            </Field>
          </div>
          <input className="input" placeholder="Skills (comma-separated)" value={editingPast.skills || ''} onChange={e => pastField({ skills: e.target.value })} />
          <div className="flex gap-2">
            <button type="button" onClick={savePast} className="btn-primary text-xs">Save role</button>
            <button type="button" onClick={() => setEditingPast(null)} className="btn-ghost text-xs">Cancel</button>
          </div>
        </div>
      )}

      {past.length > 0 && (
        <div className="space-y-1 pt-2 border-t border-charcoal-100 dark:border-charcoal-800">
          <p className="text-[11px] text-charcoal-400">Past roles</p>
          {past.map((c, i) => (
            <div key={c.id || i} className="flex items-center gap-2 text-xs text-charcoal-500 dark:text-charcoal-400">
              <button type="button" onClick={() => setEditingPast(c)} className="flex-1 min-w-0 truncate text-left hover:text-orange-500">
                {c.title || '(untitled)'}{companyNames[c.company_id] ? ` · ${companyNames[c.company_id]}` : ''} ({c.start_date || '?'}–{c.end_date || '?'})
              </button>
              <button type="button" onClick={() => removePast(c)} className="text-red-500 shrink-0">×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Company locations — a plain repeatable list (label + address), unlike
// CareerHistoryEditor's one-current-role convention: every location is
// simultaneously active, so this mirrors PhoneEditor's shape instead.
function LocationsEditor({ locations, onChange }) {
  function update(i, patch) {
    onChange(locations.map((l, idx) => (idx === i ? { ...l, ...patch } : l)))
  }
  function remove(i) {
    onChange(locations.filter((_, idx) => idx !== i))
  }
  function add() {
    onChange([...locations, { label: '', address: '' }])
  }
  return (
    <div className="space-y-2">
      {locations.map((l, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input className="input !w-28 shrink-0" placeholder="Label (e.g. Main St)"
            value={l.label || ''} onChange={e => update(i, { label: e.target.value })} />
          <input className="input flex-1 min-w-0" placeholder="Address"
            value={l.address || ''} onChange={e => update(i, { address: e.target.value })} />
          <button type="button" onClick={() => remove(i)} className="text-charcoal-400 hover:text-red-500 text-sm px-1 shrink-0">✕</button>
        </div>
      ))}
      <button type="button" onClick={add} className="text-sm text-orange-500 hover:text-orange-600 font-medium">+ Add location</button>
    </div>
  )
}

const WEEK_DAYS = [
  { id: 'mon', label: 'Mon' }, { id: 'tue', label: 'Tue' }, { id: 'wed', label: 'Wed' },
  { id: 'thu', label: 'Thu' }, { id: 'fri', label: 'Fri' }, { id: 'sat', label: 'Sat' }, { id: 'sun', label: 'Sun' },
]

// Company hours — always exactly 7 rows (Mon-Sun), a weekly template rather
// than a real calendar. `hours` is always pre-seeded to all 7 days by the
// caller, so this never needs add/remove — just per-day edit-in-place.
function HoursEditor({ hours, onChange }) {
  function update(day, patch) {
    onChange(hours.map(h => (h.day === day ? { ...h, ...patch } : h)))
  }
  return (
    <div className="space-y-1.5">
      {WEEK_DAYS.map(({ id, label }) => {
        const h = hours.find(x => x.day === id) || { day: id, open: '', close: '', closed: true }
        return (
          <div key={id} className="flex gap-2 items-center">
            <span className="text-xs text-charcoal-500 dark:text-charcoal-400 w-8 shrink-0">{label}</span>
            <label className="flex items-center gap-1 text-xs shrink-0 w-16">
              <input type="checkbox" checked={!h.closed} onChange={e => update(id, { closed: !e.target.checked })} />
              Open
            </label>
            {!h.closed && (
              <div className="flex gap-1 items-center flex-1 min-w-0">
                <input type="time" className="input min-w-0" value={h.open || ''} onChange={e => update(id, { open: e.target.value })} />
                <span className="text-charcoal-400 text-xs shrink-0">–</span>
                <input type="time" className="input min-w-0" value={h.close || ''} onChange={e => update(id, { close: e.target.value })} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// Life/business priorities editor — mirrors the drag/up-down reorder UI that
// used to live on the standalone Profile page, retargeted to write into
// form.priority_order[workspace] (the one workspace-keyed field on Contact).
function PrioritiesEditor({ order, workspace, onChange }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [customCat, setCustomCat] = useState('')

  function move(from, to) {
    if (to < 0 || to >= order.length) return
    const next = [...order]
    const [m] = next.splice(from, 1)
    next.splice(to, 0, m)
    onChange(next)
  }

  function addCustom() {
    const v = customCat.trim()
    if (v && !order.includes(v)) { onChange([...order, v]); setCustomCat('') }
  }

  function removeCat(cat) {
    if (order.length <= 1) return
    onChange(order.filter(c => c !== cat))
  }

  return (
    <div>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-2">
        Drag to reorder. Determines how {workspace === 'business' ? 'work' : ''} tasks are scored and surfaced by the AI.
      </p>
      <ul className="space-y-1.5 mb-2">
        {order.map((cat, i) => (
          <li key={cat}
            draggable
            onDragStart={() => setDragIdx(i)}
            onDragOver={e => { e.preventDefault(); if (dragIdx !== null && dragIdx !== i) { move(dragIdx, i); setDragIdx(i) } }}
            onDragEnd={() => setDragIdx(null)}
            className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-sm ${
              dragIdx === i ? 'border-orange-500 bg-orange-500/10' : 'border-charcoal-200 dark:border-charcoal-700'}`}
          >
            <span className="text-charcoal-400 text-xs w-4 shrink-0">{i + 1}</span>
            <span className="flex-1 min-w-0 truncate">{cat}</span>
            <button type="button" onClick={() => move(i, i - 1)} disabled={i === 0} className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 text-xs px-1">▲</button>
            <button type="button" onClick={() => move(i, i + 1)} disabled={i === order.length - 1} className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 text-xs px-1">▼</button>
            <button type="button" onClick={() => removeCat(cat)} disabled={order.length <= 1} className="text-charcoal-400 hover:text-red-500 disabled:opacity-20 text-xs">✕</button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input type="text" value={customCat} onChange={e => setCustomCat(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addCustom())}
          placeholder="Add category…" className="input" />
        <button type="button" onClick={addCustom} className="btn-primary px-3">+</button>
      </div>
    </div>
  )
}

const WEEK_DAY_IDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

// Always exactly 7 rows, Mon-Sun in order — a brand-new contact has no
// `hours` yet, so seed the full week (closed by default) client-side too,
// matching what the backend's own validator would normalize an empty/partial
// list into anyway.
function seedHours(existing) {
  const byDay = Object.fromEntries((existing || []).map(h => [h.day, h]))
  return WEEK_DAY_IDS.map(day => byDay[day] || { day, open: '', close: '', closed: true })
}

export default function ContactModal({ contact, fields, user, onClose, onSaved, fullPage = false }) {
  const { workspace } = useWorkspace()
  const editing = !!contact?.id
  const isSelf = editing && contact.self_of === user?.name
  // No delete UI existed anywhere in Contacts (owner report, 2026-08-17) even
  // though DELETE /contacts/{id} always worked — this was a pure frontend
  // gap. A self-contact can never be deleted directly (dies with the
  // account only); pool contacts mirror Assets' own established pattern —
  // admin-only, even for the contact's own creator, since it's a shared
  // household/team resource, not a personal one.
  const isPoolContact = editing && (contact._owner === 'household' || contact._owner === 'team')
  const isAdmin = user?.role === 'admin'
  const canDelete = editing && !isSelf && (isPoolContact ? isAdmin : contact._access === 'edit')
  const [form, setForm] = useState({
    type: contact?.type || 'person',
    name: contact?.name || '',
    emails: (contact?.emails || []).join(', '),
    address: contact?.address || '',
    tags: (contact?.tags || []).join(', '),
    birthday: contact?.birthday || '',
    status: contact?.status || '',
    notes: contact?.notes || '',
    custom: { ...(contact?.custom || {}) },
    pronouns: contact?.pronouns || '',
    gender: contact?.gender || '',
    city: contact?.city || '',
    state: contact?.state || '',
    country: contact?.country || '',
    marital_status: contact?.marital_status || '',
    pets: contact?.pets || '',
    life_mission: contact?.life_mission || '',
    key_constraints: contact?.key_constraints || '',
    wake_weekday: contact?.wake_weekday || '',
    wake_weekend: contact?.wake_weekend || '',
    bedtime: contact?.bedtime || '',
    work_start: contact?.work_start || '',
    work_end: contact?.work_end || '',
    height_unit: contact?.height_unit || 'ftin',
    height_cm: contact?.height_cm || '',
    weight_unit: contact?.weight_unit || 'lbs',
    weight_kg: contact?.weight_kg || '',
    blood_type: contact?.blood_type || '',
    conditions: contact?.conditions || '',
    medications: contact?.medications || '',
    diet: contact?.diet || '',
    exercise: contact?.exercise || '',
    income_range: contact?.income_range || '',
    budget_style: contact?.budget_style || '',
    communication_style: contact?.communication_style || '',
    tone: contact?.tone || '',
    response_language: contact?.response_language || '',
    topics_to_emphasize: contact?.topics_to_emphasize || '',
    topics_to_avoid: contact?.topics_to_avoid || '',
  })
  const [phones, setPhones] = useState(contact?.phones?.length ? contact.phones : [])
  const [careerHistory, setCareerHistory] = useState(contact?.career_history || [])
  const [locations, setLocations] = useState(contact?.locations || [])
  const [hours, setHours] = useState(() => seedHours(contact?.hours))
  // Pills, like tags/options elsewhere — not a comma-split string (owner,
  // 2026-08-18: "every entry becomes a pill... instead of having to split
  // with commas"). `Array.isArray` guard covers a not-yet-migrated legacy
  // string value defensively, same as TagInput's own prop guard.
  const [coreValues, setCoreValues] = useState(Array.isArray(contact?.core_values) ? contact.core_values : [])
  // Which of the (self-contact-only) hideable sections are hidden from
  // everyone but the owner — owner, 2026-08-18: "hiddeable for user
  // contacts by the user themself only."
  const [hiddenSections, setHiddenSections] = useState(contact?.hidden_sections || [])
  const [photoExt, setPhotoExt] = useState(contact?.photo_ext || null)
  const contactId = contact?.id || null
  const [priorityOrder, setPriorityOrder] = useState({ ...(contact?.priority_order || {}) })
  // Pool default-sharing (create-only — fixed once a contact exists) and the
  // cross-workspace toggle (editable anytime, except for a self-contact,
  // which is always cross-workspace and forced server-side regardless).
  const [keepPersonal, setKeepPersonal] = useState(false)
  const [crossWorkspace, setCrossWorkspace] = useState(!!contact?.cross_workspace)
  const [affiliatedIds, setAffiliatedIds] = useState(contact?.affiliated_contact_ids || [])
  const [affiliatedContacts, setAffiliatedContacts] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const setCustom = (k, v) => setForm(f => ({ ...f, custom: { ...f.custom, [k]: v } }))
  const splitList = s => s.split(',').map(x => x.trim()).filter(Boolean)
  const activeOrder = priorityOrder[workspace] || [...DEFAULT_PRIORITY_ORDER]
  function toggleSection(key, hide) {
    setHiddenSections(prev => (hide ? [...new Set([...prev, key])] : prev.filter(k => k !== key)))
  }

  // Height/weight feet+inches entry state, derived from height_cm on load.
  const initialTotalIn = contact?.height_cm ? Math.round(contact.height_cm / 2.54) : null
  const [heightFt, setHeightFt] = useState(initialTotalIn != null ? Math.floor(initialTotalIn / 12) : '')
  const [heightIn, setHeightIn] = useState(initialTotalIn != null ? initialTotalIn % 12 : '')

  function commitHeightFtIn(ft, inch) {
    const f = ft === '' ? 0 : Number(ft)
    const i = inch === '' ? 0 : Number(inch)
    set('height_cm', ft === '' && inch === '' ? '' : Math.round((f * 12 + i) * 2.54))
  }

  // Weight entry mirrors height: form.weight_kg stays the canonical value the
  // backend stores and formats from; the input shows/edits it converted into
  // whichever unit is currently selected so the two never get conflated.
  // Kept to 1 decimal place (not rounded to whole numbers) — rounding both on
  // the way in and the way back out to display compounds into a visible drift
  // (155 lbs -> 70 kg -> 154 lbs).
  const round1 = n => Math.round(n * 10) / 10
  const [weightDisplay, setWeightDisplay] = useState(
    contact?.weight_kg
      ? round1(contact.weight_unit === 'kg' ? contact.weight_kg : contact.weight_kg * 2.20462)
      : ''
  )

  function commitWeight(display, unit) {
    setWeightDisplay(display)
    set('weight_kg', display === '' ? '' : round1(unit === 'kg' ? Number(display) : Number(display) / 2.20462))
  }

  function changeWeightUnit(unit) {
    if (weightDisplay !== '') {
      const kg = form.weight_unit === 'kg' ? Number(weightDisplay) : Number(weightDisplay) / 2.20462
      setWeightDisplay(round1(unit === 'kg' ? kg : kg * 2.20462))
    }
    set('weight_unit', unit)
  }

  useEffect(() => {
    if (!affiliatedIds.length) return
    contactsApi.list().then(r => {
      const all = Array.isArray(r) ? r : []
      setAffiliatedContacts(affiliatedIds.map(id => all.find(c => c.id === id)).filter(Boolean))
    }).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const emailList = splitList(form.emails)
  const hasInvalidEmail = emailList.some(e => !EMAIL_RE.test(e))

  async function submit(e) {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required'); return }
    if (hasInvalidEmail) { setError('Enter a valid email address (e.g. name@example.com)'); return }
    setBusy(true); setError('')
    const payload = {
      type: form.type, name: form.name.trim(),
      emails: emailList,
      phones: phones.filter(p => p.number),
      address: form.address, tags: splitList(form.tags),
      birthday: form.birthday || null, status: form.status,
      notes: form.notes, custom: form.custom,
      pronouns: form.pronouns, gender: form.gender, city: form.city, state: form.state, country: form.country,
      marital_status: form.marital_status, pets: form.pets,
      life_mission: form.life_mission, core_values: coreValues, key_constraints: form.key_constraints,
      career_history: careerHistory,
      locations, hours,
    }
    if (!editing) {
      payload.pool = !keepPersonal
    }
    if (!isSelf) {
      payload.cross_workspace = crossWorkspace
    }
    if (isSelf) {
      Object.assign(payload, {
        hidden_sections: hiddenSections,
        priority_order: { ...priorityOrder, [workspace]: activeOrder },
        wake_weekday: form.wake_weekday, wake_weekend: form.wake_weekend,
        bedtime: form.bedtime, work_start: form.work_start, work_end: form.work_end,
        height_cm: form.height_cm || null, height_unit: form.height_unit,
        weight_kg: form.weight_kg || null, weight_unit: form.weight_unit,
        blood_type: form.blood_type,
        conditions: form.conditions, medications: form.medications,
        diet: form.diet, exercise: form.exercise,
        income_range: form.income_range, budget_style: form.budget_style,
        communication_style: form.communication_style, tone: form.tone,
        response_language: form.response_language,
        topics_to_emphasize: form.topics_to_emphasize, topics_to_avoid: form.topics_to_avoid,
      })
    }
    try {
      const saved = editing
        ? (isSelf ? await contactsApi.updateMe(payload) : await contactsApi.update(contact.id, payload))
        : await contactsApi.create(payload)
      onSaved(saved)
    } catch (err) { setError(err.message || 'Save failed'); setBusy(false) }
  }

  async function handleDelete() {
    if (!confirm(`Permanently delete "${contact.name}"? This cannot be undone.`)) return
    setBusy(true); setError('')
    try {
      await contactsApi.remove(contact.id)
      onSaved(null)
    } catch (err) { setError(err.message || 'Delete failed'); setBusy(false) }
  }

  async function handleConvert() {
    const poolLabel = workspace === 'business' ? 'Team' : 'Household'
    if (!confirm(`Make "${contact.name}" a shared ${poolLabel} contact? Everyone with access to ${poolLabel} will be able to see it.`)) return
    setBusy(true); setError('')
    try {
      const updated = await contactsApi.convert(contact.id)
      onSaved(updated)
    } catch (err) { setError(err.message || 'Convert failed'); setBusy(false) }
  }

  async function refreshPhoto() {
    const fresh = contactId && (isSelf ? await contactsApi.me() : await contactsApi.get(contactId))
    if (fresh) setPhotoExt(fresh.photo_ext || null)
  }

  const shellClass = fullPage
    ? 'w-full max-w-2xl mx-auto p-4 md:p-0'
    : 'modal-card max-w-lg w-full p-5 max-h-[92dvh] overflow-y-auto'

  const body = (
    <>
      {fullPage ? (
        <button type="button" onClick={onClose} className="text-sm text-charcoal-500 hover:text-orange-500 transition-colors mb-2">← Back</button>
      ) : null}
      <h3 className="font-semibold mb-4">{editing ? 'Edit contact' : 'New contact'}</h3>
      <form onSubmit={submit} className="space-y-3">
        <PhotoUploader contactId={contactId} photoExt={photoExt} onChanged={refreshPhoto} />
        {/* A user's own profile always stays a person — no toggle to switch it,
            enforced server-side too (contacts_service.update_contact). */}
        {!isSelf && (
          <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
            {['person', 'company'].map(t => (
              <button key={t} type="button" onClick={() => set('type', t)}
                className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  form.type === t ? 'bg-white dark:bg-charcoal-600 shadow-sm' : 'text-charcoal-500'}`}>
                {t === 'person' ? '🧑 Person' : '🏢 Company'}
              </button>
            ))}
          </div>
        )}
        {!isSelf && (!editing || (user?.workspaces || []).length > 1) && (
          <div className="flex flex-col gap-1.5 bg-charcoal-50 dark:bg-charcoal-800/50 rounded-lg p-2.5 text-xs">
            {!editing && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={keepPersonal} onChange={e => setKeepPersonal(e.target.checked)} />
                Keep this contact personal (don&apos;t share with {workspace === 'business' ? 'Team' : 'Household'})
              </label>
            )}
            {(user?.workspaces || []).length > 1 && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={crossWorkspace} onChange={e => setCrossWorkspace(e.target.checked)} />
                Also show this contact in my {workspace === 'business' ? 'personal' : 'business'} workspace
              </label>
            )}
          </div>
        )}
        <input className="input" placeholder="Name" value={form.name} onChange={e => set('name', e.target.value)} autoFocus maxLength={200} />
        <div>
          <input type="email" className="input" placeholder="Emails (comma-separated)" value={form.emails} onChange={e => set('emails', e.target.value)} />
          {hasInvalidEmail && <p className="text-xs text-red-500 mt-1">Each email must look like name@example.com</p>}
        </div>
        <PhoneEditor phones={phones} onChange={setPhones} />
        {/* For a self-contact, Address moves into its own toggleable section
            further down (isSelf block below) instead of sitting bare here —
            every other contact keeps it exactly where it's always been. */}
        {!isSelf && (
          <input className="input" placeholder="Address" value={form.address} onChange={e => set('address', e.target.value)} />
        )}
        <div className="grid grid-cols-2 gap-3">
          <input className="input" placeholder="Tags (comma-separated)" value={form.tags} onChange={e => set('tags', e.target.value)} />
          <input className="input" placeholder="Status" value={form.status} onChange={e => set('status', e.target.value)} maxLength={40} />
        </div>
        <Field label="Birthday">
          <input type="date" className="input" value={form.birthday || ''} onChange={e => set('birthday', e.target.value)} />
        </Field>
        {fields.filter(f => (f.applies_to || ['person', 'company']).includes(form.type)).map(f => (
          <label key={f.key} className="block text-xs text-charcoal-500">{f.label}
            {f.type === 'select' ? (
              <select className="input" value={form.custom[f.key] || ''} onChange={e => setCustom(f.key, e.target.value)}>
                <option value="">—</option>
                {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : f.type === 'boolean' ? (
              <input type="checkbox" className="ml-2" checked={!!form.custom[f.key]} onChange={e => setCustom(f.key, e.target.checked)} />
            ) : (
              <input type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                className="input" value={form.custom[f.key] || ''} onChange={e => setCustom(f.key, e.target.value)} />
            )}
          </label>
        ))}

        {form.type === 'company' ? (
          <>
            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">Locations</p>
              <LocationsEditor locations={locations} onChange={setLocations} />
            </div>
            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">Hours</p>
              <HoursEditor hours={hours} onChange={setHours} />
            </div>
          </>
        ) : (
          <>
            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <SectionHeader title="Personal" sectionKey={isSelf ? 'personal' : null}
                hidden={hiddenSections.includes('personal')} onToggle={toggleSection} />
              <div className="grid grid-cols-2 gap-3">
                <select className="input" value={form.gender} onChange={e => set('gender', e.target.value)}>
                  <option value="">Gender —</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                </select>
                <input className="input" placeholder="Pronouns" value={form.pronouns} onChange={e => set('pronouns', e.target.value)} />
                <input className="input" placeholder="City" value={form.city} onChange={e => set('city', e.target.value)} />
                <input className="input" placeholder="State/Province" value={form.state} onChange={e => set('state', e.target.value)} />
                <input className="input" placeholder="Country" value={form.country} onChange={e => set('country', e.target.value)} />
              </div>
            </div>

            {isSelf && (
              <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
                <SectionHeader title="Address" sectionKey="address"
                  hidden={hiddenSections.includes('address')} onToggle={toggleSection} />
                <input className="input" placeholder="Address" value={form.address} onChange={e => set('address', e.target.value)} />
              </div>
            )}

            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <SectionHeader title="Career" sectionKey={isSelf ? 'career' : null}
                hidden={hiddenSections.includes('career')} onToggle={toggleSection} />
              <CareerHistoryEditor career={careerHistory} onChange={setCareerHistory} />
            </div>
          </>
        )}

        <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
          <SectionHeader title={form.type === 'company' ? 'Affiliated People' : 'Family'}
            sectionKey={isSelf ? 'family' : null} hidden={hiddenSections.includes('family')} onToggle={toggleSection} />
          {form.type !== 'company' && (
            <div className="grid grid-cols-2 gap-3">
              <select className="input" value={form.marital_status} onChange={e => set('marital_status', e.target.value)}>
                <option value="">Marital status —</option>
                {['Single', 'Married', 'Divorced', 'Widowed', 'Partnered'].map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <input className="input" placeholder="Pets" value={form.pets} onChange={e => set('pets', e.target.value)} />
            </div>
          )}
          {editing ? (
            <AffiliationEditor
              contactId={contact.id}
              affiliated={affiliatedContacts}
              onChange={ids => {
                setAffiliatedIds(ids)
                contactsApi.list().then(r => {
                  const all = Array.isArray(r) ? r : []
                  setAffiliatedContacts(ids.map(id => all.find(c => c.id === id)).filter(Boolean))
                }).catch(() => {})
              }}
            />
          ) : (
            <p className="text-xs text-charcoal-400">Save this contact first to link family or affiliated contacts.</p>
          )}
        </div>

        <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
          <SectionHeader title="Values & Principles" sectionKey={isSelf ? 'values_principles' : null}
            hidden={hiddenSections.includes('values_principles')} onToggle={toggleSection} />
          <textarea className="input" rows={2} placeholder="Life mission" value={form.life_mission} onChange={e => set('life_mission', e.target.value)} />
          <TagInput value={coreValues} onChange={setCoreValues} placeholder="Add a core value…" />
          <textarea className="input" rows={2} placeholder="Key constraints" value={form.key_constraints} onChange={e => set('key_constraints', e.target.value)} />
        </div>

        {isSelf && (
          <>
            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3">
              <SectionHeader title={workspace === 'business' ? 'Business Priorities' : 'Life Priorities'}
                sectionKey="priorities" hidden={hiddenSections.includes('priorities')} onToggle={toggleSection} />
              <div className="mt-2">
                <PrioritiesEditor order={activeOrder} workspace={workspace}
                  onChange={next => setPriorityOrder(p => ({ ...p, [workspace]: next }))} />
              </div>
            </div>

            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">Daily Routine — private</p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Wake (weekdays)">
                  <input type="time" className="input" value={form.wake_weekday} onChange={e => set('wake_weekday', e.target.value)} />
                </Field>
                <Field label="Wake (weekends)">
                  <input type="time" className="input" value={form.wake_weekend} onChange={e => set('wake_weekend', e.target.value)} />
                </Field>
                <Field label="Bedtime">
                  <input type="time" className="input" value={form.bedtime} onChange={e => set('bedtime', e.target.value)} />
                </Field>
                <Field label="Work hours">
                  <div className="flex gap-1 items-center">
                    <input type="time" className="input min-w-0" value={form.work_start} onChange={e => set('work_start', e.target.value)} />
                    <span className="text-charcoal-400 text-xs shrink-0">–</span>
                    <input type="time" className="input min-w-0" value={form.work_end} onChange={e => set('work_end', e.target.value)} />
                  </div>
                </Field>
              </div>
            </div>

            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">Health — private</p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Height">
                  <div className="flex gap-1 items-center">
                    {form.height_unit === 'cm' ? (
                      <input type="number" min="0" max="300" className="input min-w-0" placeholder="cm"
                        value={form.height_cm} onChange={e => set('height_cm', e.target.value)} />
                    ) : (
                      <>
                        <select className="input min-w-0 !px-1" value={heightFt}
                          onChange={e => { setHeightFt(e.target.value); commitHeightFtIn(e.target.value, heightIn) }}>
                          <option value="">ft</option>
                          {Array.from({ length: 8 }, (_, i) => i + 1).map(f => <option key={f} value={f}>{f}&apos;</option>)}
                        </select>
                        <select className="input min-w-0 !px-1" value={heightIn}
                          onChange={e => { setHeightIn(e.target.value); commitHeightFtIn(heightFt, e.target.value) }}>
                          <option value="">in</option>
                          {Array.from({ length: 12 }, (_, i) => i).map(i => <option key={i} value={i}>{i}&quot;</option>)}
                        </select>
                      </>
                    )}
                    <select className="input !w-auto shrink-0 text-xs" value={form.height_unit}
                      onChange={e => set('height_unit', e.target.value)}>
                      <option value="ftin">ft/in</option>
                      <option value="cm">cm</option>
                    </select>
                  </div>
                </Field>
                <Field label="Weight">
                  <div className="flex gap-1 items-center">
                    <input type="number" min="0" max={form.weight_unit === 'kg' ? 500 : 1102} step="0.1" className="input min-w-0" placeholder={form.weight_unit}
                      value={weightDisplay} onChange={e => commitWeight(e.target.value, form.weight_unit)} />
                    <select className="input !w-auto shrink-0 text-xs" value={form.weight_unit}
                      onChange={e => changeWeightUnit(e.target.value)}>
                      <option value="lbs">lbs</option>
                      <option value="kg">kg</option>
                    </select>
                  </div>
                </Field>
              </div>
              <select className="input" value={form.blood_type} onChange={e => set('blood_type', e.target.value)}>
                <option value="">Blood type —</option>
                {BLOOD_TYPES.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
              <textarea className="input" rows={2} placeholder="Conditions" value={form.conditions} onChange={e => set('conditions', e.target.value)} />
              <textarea className="input" rows={2} placeholder="Medications" value={form.medications} onChange={e => set('medications', e.target.value)} />
              <div className="grid grid-cols-2 gap-3">
                <input className="input" placeholder="Dietary restrictions" value={form.diet} onChange={e => set('diet', e.target.value)} />
                <input className="input" placeholder="Exercise frequency" value={form.exercise} onChange={e => set('exercise', e.target.value)} />
              </div>
            </div>

            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">Finances — private</p>
              <div className="grid grid-cols-2 gap-3">
                <select className="input" value={form.income_range} onChange={e => set('income_range', e.target.value)}>
                  <option value="">Income range —</option>
                  {['Under $25k', '$25k–$50k', '$50k–$75k', '$75k–$100k', '$100k–$150k', '$150k–$200k', '$200k+'].map(r => <option key={r} value={r}>{r}</option>)}
                </select>
                <select className="input" value={form.budget_style} onChange={e => set('budget_style', e.target.value)}>
                  <option value="">Budget style —</option>
                  {['Frugal', 'Moderate', 'Comfortable', 'Flexible'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>

            <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-3">
              <p className="text-[11px] uppercase tracking-wide text-charcoal-400">AI Preferences — private</p>
              <div className="grid grid-cols-2 gap-3">
                <select className="input" value={form.communication_style} onChange={e => set('communication_style', e.target.value)}>
                  <option value="">Communication style —</option>
                  {['Concise', 'Balanced', 'Detailed'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <input className="input" placeholder="Tone" value={form.tone} onChange={e => set('tone', e.target.value)} />
              </div>
              <input className="input" placeholder="Response language" value={form.response_language} onChange={e => set('response_language', e.target.value)} />
              <textarea className="input" rows={2} placeholder="Topics to emphasize" value={form.topics_to_emphasize} onChange={e => set('topics_to_emphasize', e.target.value)} />
              <textarea className="input" rows={2} placeholder="Things to avoid" value={form.topics_to_avoid} onChange={e => set('topics_to_avoid', e.target.value)} />
            </div>
          </>
        )}

        <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3">
          <textarea className="input" rows={3} placeholder="Notes" value={form.notes} onChange={e => set('notes', e.target.value)} />
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        <div className="flex flex-wrap gap-2 pt-1 pb-4">
          {canDelete && (
            <button type="button" onClick={handleDelete} disabled={busy}
              className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
              Delete
            </button>
          )}
          {editing && !isSelf && !isPoolContact && contact._access === 'edit' && (
            <button type="button" onClick={handleConvert} disabled={busy} className="btn-ghost px-3"
              title="Move into the shared pool so your household/team can see it too">
              → {workspace === 'business' ? 'Team' : 'Household'}
            </button>
          )}
          <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          <button type="submit" disabled={busy || hasInvalidEmail} className="btn-primary flex-1">{busy ? 'Saving…' : 'Save'}</button>
        </div>
        {/* fullPage renders as normal page content inside <main>, which the
            fixed mobile footer nav floats over — the modal card's own %-based
            max-height/scroll doesn't apply here, so without this the Save/
            Cancel row sits behind the footer until you force-scroll past it. */}
        {fullPage && <div className="h-20 md:hidden" aria-hidden="true" />}
      </form>
    </>
  )

  if (fullPage) {
    return <div className={shellClass}>{body}</div>
  }
  return (
    <div className="modal-overlay">
      <div className={shellClass}>{body}</div>
    </div>
  )
}
