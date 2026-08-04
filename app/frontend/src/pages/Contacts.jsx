import { useEffect, useState, useCallback } from 'react'
import HelpButton from '../components/HelpButton'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { contacts as contactsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import ContactDetail from '../components/contacts/ContactDetail'
import ContactModal from '../components/contacts/ContactModal'
import ContactAvatar from '../components/contacts/ContactAvatar'

const TYPE_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'person', label: 'People' },
  { id: 'company', label: 'Companies' },
]

export default function Contacts() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { workspace } = useWorkspace()
  const [items, setItems] = useState([])
  const [fields, setFields] = useState([])
  const [pipeline, setPipeline] = useState(['Lead', 'Contacted', 'Proposal', 'Negotiation', 'Won', 'Lost'])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [showArchived, setShowArchived] = useState(false)
  const [modal, setModal] = useState(null)      // { contact } for edit / {} for new
  const [detail, setDetail] = useState(null)    // contact being viewed

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, f, p] = await Promise.all([
        contactsApi.list(showArchived),
        contactsApi.fields().catch(() => []),
        contactsApi.pipeline().catch(() => ({ stages: [] })),
      ])
      setItems(Array.isArray(list) ? list : [])
      setFields(Array.isArray(f) ? f : [])
      if (p?.stages?.length) setPipeline(p.stages)
    } finally { setLoading(false) }
  }, [workspace, showArchived])
  useEffect(() => { load() }, [load])

  // ?contact=<id> deep link (from asset contact fields, invoice/tx source chips)
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const target = searchParams.get('contact')
    if (!target || loading) return
    const found = items.find(c => c.id === target)
    if (found) openContact(found)
    searchParams.delete('contact')
    setSearchParams(searchParams, { replace: true })
  }, [loading, items, searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  const q = search.trim().toLowerCase()
  const matches = c => (!q ||
    (c.name || '').toLowerCase().includes(q) ||
    (c.emails || []).some(e => e.toLowerCase().includes(q)) ||
    (c.tags || []).some(t => t.toLowerCase().includes(q))) &&
    (typeFilter === 'all' || c.type === typeFilter)

  // The viewer's own self-contact is pinned to the top of THEIR OWN list only
  // (never shown pinned to anyone else) — see contacts_service.list_visible_contacts.
  const mine = items.find(c => c.self_of === user?.name)
  const rest = items.filter(c => c !== mine)
  const filtered = [mine, ...rest].filter(Boolean).filter(matches)

  function openContact(c) {
    // Your own profile has a lot more data and lives at its own full page —
    // everyone else's contact (including someone else's shared self-contact)
    // still opens in the regular modal card.
    if (c.self_of === user?.name) { navigate('/profile'); return }
    setDetail(c)
  }

  async function handleImport(e) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const preview = await contactsApi.csvPreview(file)
      // Simple import: re-read full rows client-side then commit.
      const text = await file.text()
      const lines = text.split(/\r?\n/).filter(Boolean)
      const headers = (preview.headers || []).map(h => h.trim())
      const rows = lines.slice(1).map(line => {
        const cells = line.split(',')
        const row = {}
        headers.forEach((h, i) => { row[h] = (cells[i] || '').trim() })
        return row
      })
      const res = await contactsApi.csvCommit(rows)
      alert(`Imported ${res.created}, skipped ${res.skipped}`)
      load()
    } catch (err) { alert(err.message || 'Import failed') }
    e.target.value = ''
  }

  return (
    <div key={workspace} className="w-full max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="flex items-center gap-2"><h1 className="text-2xl font-bold">Contacts</h1><HelpButton section="contacts" /></span>
        <div className="flex gap-2">
          <button onClick={() => setShowArchived(s => !s)} className="btn-ghost text-sm">{showArchived ? 'Hide archived' : 'Show archived'}</button>
          <label className="btn-ghost text-sm cursor-pointer">Import
            <input type="file" accept=".csv" className="hidden" onChange={handleImport} />
          </label>
          <button onClick={() => contactsApi.exportCsv()} className="btn-ghost text-sm">Export</button>
          <button onClick={() => setModal({})} className="btn-primary">＋ New</button>
        </div>
      </div>

      <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
        Your {workspace} people & organizations — clients, leads, vendors, friends. Track details,
        conversations, and deals; Finance links a contact to their money.
      </p>

      <input className="input" placeholder="Search name, email, tag…" value={search} onChange={e => setSearch(e.target.value)} />

      <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1 w-fit">
        {TYPE_FILTERS.map(f => (
          <button key={f.id} onClick={() => setTypeFilter(f.id)}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              typeFilter === f.id ? 'bg-white dark:bg-charcoal-600 shadow-sm' : 'text-charcoal-500'}`}>
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-16 card animate-pulse" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500">
          <p className="text-4xl mb-2">👥</p>
          <p>{items.length === 0 ? 'No contacts yet.' : 'No matches.'}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(c => (
            <button key={c.id} onClick={() => openContact(c)}
              className={`w-full text-left card p-3 flex items-center gap-3 hover:border-orange-500/40 ${c.archived ? 'opacity-50' : ''}`}>
              <ContactAvatar contact={c} size="w-9 h-9" textSize="text-xl" />
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate flex items-center gap-1.5">
                  {c.name}
                  {c.self_of === user?.name && (
                    <span className="badge bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 font-semibold text-[10px] shrink-0">ME</span>
                  )}
                </p>
                <p className="text-xs text-charcoal-500 truncate">
                  {(c.emails || [])[0] || (c.phones || [])[0]?.number || (c.tags || []).join(', ') || '—'}
                </p>
              </div>
              {c._owner && <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 shrink-0">{c._owner}</span>}
            </button>
          ))}
          {/* Clears the fixed mobile footer nav so the last row is never hidden behind it */}
          <div className="h-20 md:hidden" aria-hidden="true" />
        </div>
      )}

      {modal && (
        <ContactModal
          contact={modal.contact}
          fields={fields}
          user={user}
          onClose={() => setModal(null)}
          onSaved={saved => { setModal(null); load(); if (detail) setDetail(saved) }}
        />
      )}
      {detail && (
        <ContactDetail
          contact={detail}
          fields={fields}
          pipeline={pipeline}
          user={user}
          onClose={() => setDetail(null)}
          onEdit={() => { setModal({ contact: detail }); setDetail(null) }}
        />
      )}
    </div>
  )
}
