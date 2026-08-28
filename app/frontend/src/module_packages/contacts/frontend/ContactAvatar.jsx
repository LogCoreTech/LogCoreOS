import { useEffect, useRef, useState } from 'react'
import { contacts as contactsApi } from './api'
import { formatLastSeen } from './presence'

// Shared by the Contacts list, ContactDetail's header, and ContactModal's
// PhotoUploader preview — fetches the photo as an authenticated blob (a plain
// <img src="/api/v1/contacts/{id}/photo"> can't carry the X-Workspace header
// the endpoint needs to resolve a non-self contact in the active workspace).
export function useContactPhotoUrl(contactId, photoExt) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    if (!contactId || !photoExt) { setUrl(null); return }
    let objectUrl = null
    contactsApi.photoBlob(contactId)
      .then(blob => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) })
      .catch(() => setUrl(null))
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [contactId, photoExt])
  return url
}

function defaultIcon(contact) {
  if (contact.type === 'company') return '🏢'
  if (contact.gender === 'female') return '👩'
  if (contact.gender === 'male') return '👨'
  return '🧑'
}

// Online/offline dot — only for a user-linked contact (self_of set); an
// ordinary contact never shows one, since it doesn't represent a real
// account that could be "online" at all. `_online`/`_last_seen` come
// pre-resolved from contacts_service.annotate() — the backend already gates
// both behind the same access check that let the viewer see this contact in
// the first place, so the frontend never needs (and never gets) a way to
// look up an arbitrary user's presence directly. Purely visual now — see
// the click handling on the photo/icon below.
function PresenceDot({ online }) {
  return (
    <span
      className={`absolute bottom-0 right-0 block w-2.5 h-2.5 rounded-full border-2 border-white dark:border-charcoal-900 pointer-events-none ${
        online ? 'bg-green-500' : 'bg-red-500'}`}
    />
  )
}

// The dot itself used to be the click target for the "last seen" popover —
// too small to reliably tap (owner report, 2026-08-17: "the dot is too
// small"). The click now lands on the photo/icon instead — a much bigger,
// easier target — while the dot stays purely as the at-a-glance color
// indicator. Popover still opens from the dot's own corner (same
// click-toggles-a-small-popover shape as EmojiPicker.jsx/BlockPicker.jsx's
// ColorSwatchPicker; click-outside via a document `mousedown` listener).
//
// A real `<button>` here would be invalid HTML — ContactRow (Contacts.jsx)
// renders the whole row as a `<button>`, and a `<button>` can't nest inside
// another `<button>` — so this wraps the photo/icon in a `<span
// role="button">` with matching keyboard support instead, valid in both
// that context and ContactDetail's plain (non-button) header.
export default function ContactAvatar({ contact, size = 'w-8 h-8', textSize = 'text-xl', onPopoverToggle }) {
  const url = useContactPhotoUrl(contact.id, contact.photo_ext)
  const showPresence = !!contact.self_of
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  // Purely informational for a parent that needs to react to this popover's
  // own open state (e.g. ContactRow boosting its row's stacking context so
  // the popover isn't painted over by the next row — see Contacts.jsx).
  // Optional — ContactDetail's header usage has no sibling-row problem and
  // doesn't pass this.
  useEffect(() => { onPopoverToggle?.(open) }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  function toggle(e) {
    e.stopPropagation()
    e.preventDefault()
    setOpen(o => !o)
  }

  const photo = url ? (
    <img src={url} alt="" className={`${size} rounded-full object-cover shrink-0`} />
  ) : (
    <span className={`${textSize} shrink-0`}>{defaultIcon(contact)}</span>
  )

  return (
    <span className="relative inline-flex shrink-0" ref={ref}>
      {showPresence ? (
        <span
          role="button"
          tabIndex={0}
          onClick={toggle}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggle(e) }}
          className="cursor-pointer"
          title={contact._online ? 'Online' : 'Offline'}
        >
          {photo}
        </span>
      ) : photo}
      {showPresence && <PresenceDot online={!!contact._online} />}
      {showPresence && open && (
        <span className="absolute z-50 top-full left-0 mt-1 px-2 py-1 rounded-md shadow-lg bg-charcoal-800 dark:bg-charcoal-700 text-white text-xs whitespace-nowrap">
          {contact._online ? 'Online now' : formatLastSeen(contact._last_seen)}
        </span>
      )}
    </span>
  )
}
