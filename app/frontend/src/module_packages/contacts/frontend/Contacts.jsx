import { useEffect, useState, useCallback } from 'react'
import HelpButton from '../../../components/HelpButton'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { contacts as contactsApi } from './api'
import { useAuth } from '../../../lib/auth'
import { useWorkspace } from '../../../lib/workspace'
import ContactDetail from './ContactDetail'
import ContactModal from './ContactModal'
import ContactAvatar from './ContactAvatar'
import BulkConvertContactsModal from './BulkConvertContactsModal'
import { formatPhone } from './phone'

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
  const [showBulkConvert, setShowBulkConvert] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, f, p] = await Promise.all([
        contactsApi.list(showArchived),
        contactsApi.fields().catch(() => []),
        contactsApi.pipeline().catch(() => ({ stages: [] })),
      ])
      const cleanList = Array.isArray(list) ? list : []
      setItems(cleanList)
      setFields(Array.isArray(f) ? f : [])
      if (p?.stages?.length) setPipeline(p.stages)
      // Re-sync the open detail panel (if any) from the same fresh list —
      // load() previously only ever touched `items`, so a contact left open
      // in the detail view (presence dot included) went stale forever until
      // manually reopened. Falls back to the previous value if the contact's
      // no longer visible (e.g. it was just archived out from under it).
      setDetail(prev => (prev ? cleanList.find(c => c.id === prev.id) || prev : prev))
    } finally { setLoading(false) }
    // `workspace` isn't referenced in this callback's own body (the active
    // workspace flows through api.js's request header instead) — it's kept
    // as a dependency deliberately, purely so `load` gets a new reference
    // (and the effect below re-runs) when the workspace switches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, showArchived])
  useEffect(() => { load() }, [load])

  // Presence (and anything else time-sensitive) goes stale while this page
  // sits open — Contacts had no refresh mechanism at all before this (owner
  // report, 2026-08-17: "been on the app a few minutes and the [presence]
  // dot is still red" — the ping itself was working fine server-side, this
  // page just never refetched to see the updated result). Mirrors
  // Dashboard.jsx's own poll-while-visible pattern, at a slightly longer
  // interval since presence only needs to be approximately fresh, not tight.
  useEffect(() => {
    function refresh() {
      if (document.visibilityState === 'visible') load()
    }
    const interval = setInterval(refresh, 60000)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [load])

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
  const mineMatch = mine && matches(mine) ? mine : null

  // Eligible for bulk convert-to-pool: the viewer's own personal contacts
  // only — no `_owner` (not already pool, not shared-to-me from someone
  // else) and not a self-contact (already permanently pool). Independent of
  // the current search/type filter — bulk convert operates over everything
  // eligible, not just what's currently visible on screen.
  const eligibleForConvert = items.filter(c => !c._owner && !c.self_of)

  // Everyone else, alphabetical by name, grouped into first-letter buckets
  // with a sticky header per letter + a jump strip — makes a long list
  // actually navigable instead of just insertion order.
  const restSorted = rest.filter(matches).sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  const letterGroups = []
  for (const c of restSorted) {
    const first = (c.name || '').trim()[0] || ''
    const letter = /[a-z]/i.test(first) ? first.toUpperCase() : '#'
    const last = letterGroups[letterGroups.length - 1]
    if (last && last.letter === letter) last.contacts.push(c)
    else letterGroups.push({ letter, contacts: [c] })
  }
  const ALPHABET = [...'ABCDEFGHIJKLMNOPQRSTUVWXYZ', '#']
  const availableLetters = new Set(letterGroups.map(g => g.letter))

  function jumpToLetter(letter) {
    document.getElementById(`contact-letter-${letter}`)?.scrollIntoView({ block: 'start' })
  }

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
          {eligibleForConvert.length > 0 && (
            <button onClick={() => setShowBulkConvert(true)} className="btn-ghost text-sm">
              → {workspace === 'business' ? 'Team' : 'Household'} ({eligibleForConvert.length})
            </button>
          )}
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
      ) : !mineMatch && letterGroups.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500">
          <p className="text-4xl mb-2">👥</p>
          <p>{items.length === 0 ? 'No contacts yet.' : 'No matches.'}</p>
        </div>
      ) : (
        <div className="flex gap-2">
          <div className="flex-1 min-w-0 space-y-2">
            {mineMatch && <ContactRow contact={mineMatch} user={user} onOpen={openContact} />}
            {letterGroups.map(g => (
              <div key={g.letter} id={`contact-letter-${g.letter}`}>
                <h2 className="sticky top-0 z-10 -mx-1 px-1 py-1 bg-charcoal-50/95 dark:bg-charcoal-900/95 backdrop-blur-sm text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400">
                  {g.letter}
                </h2>
                <div className="space-y-2 mt-1">
                  {g.contacts.map(c => <ContactRow key={c.id} contact={c} user={user} onOpen={openContact} />)}
                </div>
              </div>
            ))}
            {/* Clears the fixed mobile footer nav so the last row is never hidden behind it */}
            <div className="h-20 md:hidden" aria-hidden="true" />
          </div>

          {/* A-Z jump strip */}
          <div className="hidden sm:flex flex-col items-center gap-0.5 shrink-0 py-1 sticky top-8 self-start">
            {ALPHABET.map(letter => (
              <button
                key={letter}
                type="button"
                onClick={() => jumpToLetter(letter)}
                disabled={!availableLetters.has(letter)}
                className={`text-[10px] leading-none w-4 text-center rounded transition-colors ${
                  availableLetters.has(letter)
                    ? 'text-charcoal-500 dark:text-charcoal-400 hover:text-orange-500 dark:hover:text-orange-400 cursor-pointer'
                    : 'text-charcoal-300 dark:text-charcoal-700 cursor-default'
                }`}
              >
                {letter}
              </button>
            ))}
          </div>
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
      {showBulkConvert && (
        <BulkConvertContactsModal
          contacts={eligibleForConvert}
          workspace={workspace}
          onClose={() => setShowBulkConvert(false)}
          onDone={res => {
            setShowBulkConvert(false)
            load()
            alert(`Converted ${res.converted}${res.skipped ? `, skipped ${res.skipped}` : ''}.`)
          }}
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

function ContactRow({ contact: c, user, onOpen }) {
  // `.card`'s backdrop-blur gives every row its own stacking context, so the
  // presence popover's z-index only ever wins comparisons inside its own
  // row — the next row (a later, un-elevated sibling stacking context) was
  // painting over it regardless (owner report, 2026-08-18: popover
  // "partially hidden by the contact below it"). Boosting *this* row's own
  // stacking context above its siblings while its popover is open fixes it
  // without introducing this codebase's first portal-based popover.
  const [popoverOpen, setPopoverOpen] = useState(false)
  return (
    <button onClick={() => onOpen(c)}
      className={`w-full text-left card p-3 flex items-center gap-3 hover:border-orange-500/40 ${popoverOpen ? 'relative z-20' : ''} ${c.archived ? 'opacity-50' : ''}`}>
      <ContactAvatar contact={c} size="w-9 h-9" textSize="text-xl" onPopoverToggle={setPopoverOpen} />
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate flex items-center gap-1.5">
          {c.name}
          {c.self_of === user?.name && (
            <span className="badge bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 font-semibold text-[10px] shrink-0">ME</span>
          )}
        </p>
        <p className="text-xs text-charcoal-500 truncate">
          {(c.emails || [])[0] || ((c.phones || [])[0] && formatPhone(c.phones[0])) || (c.tags || []).join(', ') || '—'}
        </p>
      </div>
      {c._owner && <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 shrink-0">{c._owner}</span>}
    </button>
  )
}
