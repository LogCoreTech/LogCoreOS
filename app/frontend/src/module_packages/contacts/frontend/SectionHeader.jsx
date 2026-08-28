// A section heading, optionally with a "hide from others" toggle sticky to
// its far right — self-contact-only (owner, 2026-08-18: "hiddeable for user
// contacts by the user themself only"). `sectionKey` must be one of
// contacts_service.py's _HIDEABLE_SECTIONS keys; omit `sectionKey` (and
// `hidden`/`onToggle`) for an ordinary, non-toggleable heading — every
// existing call site that doesn't pass it renders exactly as before.
export default function SectionHeader({ title, suffix, sectionKey, hidden, onToggle }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <p className="text-[11px] uppercase tracking-wide text-charcoal-400">
        {title}{suffix ? ` — ${suffix}` : ''}
      </p>
      {sectionKey && (
        <label
          className="flex items-center gap-1.5 text-[11px] normal-case text-charcoal-400 cursor-pointer shrink-0"
          title="Only you can ever see this section regardless — this controls whether anyone else with access to your contact can"
        >
          <input type="checkbox" checked={!!hidden} onChange={e => onToggle(sectionKey, e.target.checked)} />
          Hide from others
        </label>
      )}
    </div>
  )
}
