import { useEffect, useState } from 'react'
import { contacts as contactsApi } from '../../lib/api'

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

export default function ContactAvatar({ contact, size = 'w-8 h-8', textSize = 'text-xl' }) {
  const url = useContactPhotoUrl(contact.id, contact.photo_ext)
  if (url) {
    return <img src={url} alt="" className={`${size} rounded-full object-cover shrink-0`} />
  }
  return <span className={`${textSize} shrink-0`}>{defaultIcon(contact)}</span>
}
