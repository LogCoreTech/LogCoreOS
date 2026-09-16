import ContactPicker from '../../../components/contacts/ContactPicker'
import Field from './Field'

// The set of inputs describing one career_history entry (title, employer,
// industry, education, years of experience, start/end date, skills) —
// extracted out of ContactModal.jsx's CareerHistoryEditor, which rendered
// this exact block twice: once for the always-present "current role" entry
// (no end date — it's still ongoing) and once for the past-role draft/edit
// form (which adds an end date). `showEndDate` is the only difference
// between the two call sites; everything else, including field order and
// the EDUCATION_LEVELS/EXPERIENCE_LEVELS lists, is identical.
export const EDUCATION_LEVELS = [
  'Junior High', 'High School', 'Some College', 'Trade/Vocational School',
  "Associate's Degree", "Bachelor's Degree", "Master's Degree", 'Doctorate', 'Other',
]
export const EXPERIENCE_LEVELS = [
  'Less than 1 year', '1-2 years', '3-5 years', '6-10 years', '11-15 years', '16-20 years', '20+ years',
]

export default function CareerRoleFields({ entry, onChange, companyNames, showEndDate = false }) {
  return (
    <>
      <input className="input" placeholder="Job title" value={entry.title || ''} onChange={e => onChange({ title: e.target.value })} />
      <ContactPicker
        label="Employer"
        value={{ name: companyNames[entry.company_id] || '', contactId: entry.company_id || null }}
        onChange={(_n, id) => onChange({ company_id: id })}
        placeholder="Search or add a company…"
      />
      <div className="grid grid-cols-2 gap-3">
        <input className="input" placeholder="Industry" value={entry.industry || ''} onChange={e => onChange({ industry: e.target.value })} />
        <select className="input" value={entry.education || ''} onChange={e => onChange({ education: e.target.value })}>
          <option value="">Education —</option>
          {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <select className="input" value={entry.years_experience || ''} onChange={e => onChange({ years_experience: e.target.value })}>
          <option value="">Experience —</option>
          {EXPERIENCE_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <Field label="Started">
          <input type="month" className="input" value={entry.start_date || ''} onChange={e => onChange({ start_date: e.target.value })} />
        </Field>
        {showEndDate && (
          <Field label="Ended">
            <input type="month" className="input" value={entry.end_date || ''} onChange={e => onChange({ end_date: e.target.value })} />
          </Field>
        )}
      </div>
      <input className="input" placeholder="Skills (comma-separated)" value={entry.skills || ''} onChange={e => onChange({ skills: e.target.value })} />
    </>
  )
}
