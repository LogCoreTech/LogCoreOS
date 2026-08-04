import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { contacts as contactsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import ContactDetail from '../components/contacts/ContactDetail'
import ContactModal from '../components/contacts/ContactModal'

// Profile is the user's own self-contact — a Contact record IS their profile
// now. This is a thin page: fetch it via /contacts/me (gated by login only,
// not the contacts module, so nobody loses their own profile because
// Contacts is disabled for them), then render the same read-first
// ContactDetail / ContactModal pair Contacts.jsx uses, with a local view/edit
// mode switch mirroring AssetModal's pattern.
export default function Profile() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const [contact, setContact] = useState(null)
  const [fields, setFields] = useState([])
  const [pipeline, setPipeline] = useState(['Lead', 'Contacted', 'Proposal', 'Negotiation', 'Won', 'Lost'])
  const [mode, setMode] = useState('view')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    Promise.all([
      contactsApi.me(),
      contactsApi.fields().catch(() => []),
      contactsApi.pipeline().catch(() => ({ stages: [] })),
    ])
      .then(([me, f, p]) => {
        setContact(me)
        setFields(Array.isArray(f) ? f : [])
        if (p?.stages?.length) setPipeline(p.stages)
      })
      .catch(() => setError('Could not load profile.'))
      .finally(() => setLoading(false))
  }, [workspace])

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto space-y-3">
        {[1, 2, 3, 4].map(i => <div key={i} className="h-14 card animate-pulse" />)}
      </div>
    )
  }

  if (error || !contact) {
    return <p className="text-red-500 text-sm max-w-2xl mx-auto">{error || 'Profile unavailable.'}</p>
  }

  return mode === 'edit' ? (
    <ContactModal
      contact={contact}
      fields={fields}
      user={user}
      fullPage
      onClose={() => setMode('view')}
      onSaved={saved => { setContact(saved); setMode('view') }}
    />
  ) : (
    <ContactDetail
      contact={contact}
      fields={fields}
      pipeline={pipeline}
      user={user}
      fullPage
      onClose={() => navigate('/settings')}
      onEdit={() => setMode('edit')}
    />
  )
}
