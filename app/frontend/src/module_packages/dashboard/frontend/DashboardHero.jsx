import ContactAvatar from '../../../components/contacts/ContactAvatar'

/**
 * Identity banner for a dashboard made from a template with a subject — the
 * one thing missing before this: nothing on screen announced who/what a
 * dashboard was about, only individual block configs knew. Deliberately
 * minimal for v1 — avatar/icon, name, and the template's own label; no
 * configurable extra fields (those were illustrative in the original mockup,
 * not a real requirement yet).
 */
export default function DashboardHero({ subject, templateLabel }) {
  if (!subject) return null

  return (
    <div className="card p-4 flex items-center gap-3">
      {subject.type === 'contact' ? (
        <ContactAvatar
          contact={{ id: subject.id, type: subject.contact_type, gender: subject.gender, photo_ext: subject.photo_ext }}
          size="w-12 h-12"
          textSize="text-2xl"
        />
      ) : (
        <span className="w-12 h-12 rounded-full bg-orange-500 text-white flex items-center justify-center text-xl shrink-0">
          {subject.icon || '📦'}
        </span>
      )}
      <div className="min-w-0">
        {templateLabel && (
          <p className="text-xs font-semibold uppercase tracking-wide text-orange-500">{templateLabel}</p>
        )}
        <h3 className="font-semibold text-lg truncate">{subject.name}</h3>
      </div>
    </div>
  )
}
