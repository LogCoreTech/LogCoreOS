import { useEffect, useState, useCallback } from 'react'
import HelpButton from '../components/HelpButton'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { contacts as contactsApi, assets as assetsApi, finance as financeApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'

const money = cents => `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const toCents = v => Math.round(parseFloat(v || '0') * 100) || 0

// ── Contact create/edit modal ──────────────────────────────────────────────
function ContactModal({ contact, fields, onClose, onSaved }) {
  const editing = !!contact?.id
  const [form, setForm] = useState({
    type: contact?.type || 'person',
    name: contact?.name || '',
    emails: (contact?.emails || []).join(', '),
    phones: (contact?.phones || []).join(', '),
    address: contact?.address || '',
    tags: (contact?.tags || []).join(', '),
    birthday: contact?.birthday || '',
    status: contact?.status || '',
    notes: contact?.notes || '',
    custom: { ...(contact?.custom || {}) },
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const setCustom = (k, v) => setForm(f => ({ ...f, custom: { ...f.custom, [k]: v } }))
  const splitList = s => s.split(',').map(x => x.trim()).filter(Boolean)

  async function submit(e) {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required'); return }
    setBusy(true); setError('')
    const payload = {
      type: form.type, name: form.name.trim(),
      emails: splitList(form.emails), phones: splitList(form.phones),
      address: form.address, tags: splitList(form.tags),
      birthday: form.birthday || null, status: form.status,
      notes: form.notes, custom: form.custom,
    }
    try {
      const saved = editing
        ? await contactsApi.update(contact.id, payload)
        : await contactsApi.create(payload)
      onSaved(saved)
    } catch (err) { setError(err.message || 'Save failed'); setBusy(false) }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-lg w-full p-5">
        <h3 className="font-semibold mb-4">{editing ? 'Edit contact' : 'New contact'}</h3>
        <form onSubmit={submit} className="space-y-3">
          <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
            {['person', 'company'].map(t => (
              <button key={t} type="button" onClick={() => set('type', t)}
                className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  form.type === t ? 'bg-white dark:bg-charcoal-600 shadow-sm' : 'text-charcoal-500'}`}>
                {t === 'person' ? '🧑 Person' : '🏢 Company'}
              </button>
            ))}
          </div>
          <input className="input" placeholder="Name" value={form.name} onChange={e => set('name', e.target.value)} autoFocus maxLength={200} />
          <input className="input" placeholder="Emails (comma-separated)" value={form.emails} onChange={e => set('emails', e.target.value)} />
          <input className="input" placeholder="Phones (comma-separated)" value={form.phones} onChange={e => set('phones', e.target.value)} />
          <input className="input" placeholder="Address" value={form.address} onChange={e => set('address', e.target.value)} />
          <div className="grid grid-cols-2 gap-3">
            <input className="input" placeholder="Tags (comma-separated)" value={form.tags} onChange={e => set('tags', e.target.value)} />
            <input className="input" placeholder="Status" value={form.status} onChange={e => set('status', e.target.value)} maxLength={40} />
          </div>
          <label className="block text-xs text-charcoal-500">Birthday
            <input type="date" className="input" value={form.birthday || ''} onChange={e => set('birthday', e.target.value)} />
          </label>
          {fields.map(f => (
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
          <textarea className="input" rows={3} placeholder="Notes" value={form.notes} onChange={e => set('notes', e.target.value)} />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary flex-1">{busy ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Contact detail (view) ──────────────────────────────────────────────────
function ContactDetail({ contact, fields, pipeline, onClose, onEdit, onChanged }) {
  const navigate = useNavigate()
  const canEdit = contact._access === 'edit'
  const canContribute = contact._access === 'edit' || contact._access === 'contribute'
  const [interactions, setInteractions] = useState([])
  const [deals, setDeals] = useState([])
  const [fin, setFin] = useState(null)
  const [iForm, setIForm] = useState({ type: 'note', summary: '', date: '', follow_up: '' })
  const [dForm, setDForm] = useState(null)
  const [assetList, setAssetList] = useState([])          // for deal asset linking; [] if assets module off
  const [expandedDeal, setExpandedDeal] = useState(null)  // deal id whose panel is open
  const [linkSelect, setLinkSelect] = useState('')
  const [dealInvs, setDealInvs] = useState([])            // invoices billing the expanded deal
  const [refAssets, setRefAssets] = useState([])          // assets referencing this contact (contact-type fields)

  const load = useCallback(() => {
    contactsApi.interactions(contact.id).then(r => setInteractions(Array.isArray(r) ? r : [])).catch(() => {})
    contactsApi.deals(contact.id).then(r => setDeals(Array.isArray(r) ? r : [])).catch(() => {})
    contactsApi.finance(contact.id).then(setFin).catch(() => {})
    assetsApi.byContact(contact.id).then(r => setRefAssets(Array.isArray(r) ? r : [])).catch(() => {})
  }, [contact.id])
  useEffect(() => { load() }, [load])

  // Assets list feeds the deal link picker — silent no-op when the module is off
  useEffect(() => {
    assetsApi.list().then(r => setAssetList(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])

  // Invoices billing the expanded deal (viewer-scoped server-side)
  useEffect(() => {
    if (!expandedDeal) { setDealInvs([]); return }
    let alive = true
    financeApi.dealInvoices(expandedDeal)
      .then(r => { if (alive) setDealInvs(Array.isArray(r) ? r : []) })
      .catch(() => { if (alive) setDealInvs([]) })
    return () => { alive = false }
  }, [expandedDeal])

  async function linkAssetToDeal(dealId) {
    if (!linkSelect) return
    try { await contactsApi.linkAsset(contact.id, dealId, linkSelect); setLinkSelect(''); load() } catch { /* ignore */ }
  }

  async function unlinkAssetFromDeal(dealId, assetId) {
    try { await contactsApi.unlinkAsset(contact.id, dealId, assetId); load() } catch { /* ignore */ }
  }

  async function addInteraction(e) {
    e.preventDefault()
    if (!iForm.summary.trim() && iForm.type === 'note') return
    try {
      await contactsApi.addInteraction(contact.id, iForm)
      setIForm({ type: 'note', summary: '', date: '', follow_up: '' })
      load()
    } catch { /* ignore */ }
  }

  async function saveDeal(e) {
    e.preventDefault()
    const payload = { title: dForm.title, value_cents: toCents(dForm.value), stage: dForm.stage }
    try {
      if (dForm.id) await contactsApi.updateDeal(contact.id, dForm.id, payload)
      else await contactsApi.addDeal(contact.id, payload)
      setDForm(null); load()
    } catch { /* ignore */ }
  }

  async function moveDeal(deal, stage) {
    try { await contactsApi.updateDeal(contact.id, deal.id, { stage }); load() } catch { /* ignore */ }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-2xl w-full p-5 max-h-[90dvh] overflow-y-auto">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <h3 className="font-semibold text-lg">{contact.type === 'company' ? '🏢' : '🧑'} {contact.name}</h3>
            <div className="flex gap-1 flex-wrap mt-1">
              {contact.status && <span className="badge bg-charcoal-100 dark:bg-charcoal-700">{contact.status}</span>}
              {(contact.tags || []).map(t => <span key={t} className="badge bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300">{t}</span>)}
              {contact._owner && <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">{contact._owner}</span>}
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            {canEdit && <button onClick={onEdit} className="btn-ghost text-sm">✎ Edit</button>}
            <button onClick={onClose} className="btn-ghost text-sm">✕</button>
          </div>
        </div>

        {/* Fields */}
        <div className="text-sm space-y-1 mb-4">
          {(contact.emails || []).map(e => <p key={e}>✉️ <a href={`mailto:${e}`} className="text-orange-600">{e}</a></p>)}
          {(contact.phones || []).map(p => <p key={p}>📞 {p}</p>)}
          {contact.address && <p>📍 {contact.address}</p>}
          {contact.birthday && <p>🎂 {contact.birthday}</p>}
          {fields.map(f => contact.custom?.[f.key] != null && contact.custom[f.key] !== '' && (
            <p key={f.key}><span className="text-charcoal-500">{f.label}:</span> {String(contact.custom[f.key])}</p>
          ))}
          {contact.notes && <p className="text-charcoal-500 whitespace-pre-wrap mt-2">{contact.notes}</p>}
        </div>

        {/* References — money + every record linked to this contact */}
        {((fin?.available && (fin.tx_count > 0 || (fin.invoices || []).length > 0)) || refAssets.length > 0) && (
          <div className="card p-3 mb-4 text-sm space-y-2">
            {fin?.available && (fin.tx_count > 0 || fin.spent_cents > 0 || fin.received_cents > 0) && (
              <div className="flex gap-4 flex-wrap">
                <span>💸 Spent: <b>{money(fin.spent_cents)}</b></span>
                <span>💰 Received: <b>{money(fin.received_cents)}</b></span>
                <span className="text-charcoal-500">{fin.tx_count} transactions</span>
                {fin.outstanding_cents > 0 && (
                  <span className="text-orange-500">Outstanding: <b>{money(fin.outstanding_cents)}</b></span>
                )}
              </div>
            )}
            {refAssets.length > 0 && (
              <div className="flex gap-1 flex-wrap items-center">
                <span className="text-xs text-charcoal-500 shrink-0">Assets:</span>
                {refAssets.map(a => (
                  <button
                    key={a.id}
                    onClick={() => navigate(`/assets?asset=${a.id}`)}
                    className="badge bg-charcoal-100 dark:bg-charcoal-700 hover:underline"
                    title={a.template_label}
                  >{a.icon} {a.name}</button>
                ))}
              </div>
            )}
            {(fin?.invoices || []).length > 0 && (
              <div className="space-y-1">
                <span className="text-xs text-charcoal-500">Invoices:</span>
                {fin.invoices.map(inv => (
                  <div key={inv.id} className="flex items-center gap-2 text-xs">
                    <button onClick={() => navigate(`/finance?book=${inv.book_id}&view=invoices`)} className="font-mono text-orange-500 hover:underline">{inv.number}</button>
                    <span className="badge bg-charcoal-100 dark:bg-charcoal-700">{inv.status}</span>
                    {inv.overdue && <span className="text-red-500 font-medium">OVERDUE</span>}
                    <span className="ml-auto">
                      {inv.balance_cents > 0 && inv.status !== 'draft'
                        ? `${money(inv.balance_cents)} due`
                        : money(inv.total_cents)}
                    </span>
                    <span className="text-charcoal-400">{inv.book_name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Deals */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500">Deals</h4>
            {canContribute && <button onClick={() => setDForm({ title: '', value: '', stage: pipeline[0] || 'Lead' })} className="btn-ghost text-xs">＋ Add</button>}
          </div>
          {deals.length === 0 ? <p className="text-xs text-charcoal-400">No deals yet.</p> : (
            <div className="space-y-2">
              {deals.map(d => (
                <div key={d.id}>
                  <div className="flex items-center gap-2 text-sm">
                    <span className="flex-1 min-w-0 truncate">{d.title}</span>
                    <span className="font-medium">{money(d.value_cents)}</span>
                    {canContribute ? (
                      <select className="input !w-auto !py-1 text-xs" value={d.stage} onChange={e => moveDeal(d, e.target.value)}>
                        {pipeline.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    ) : <span className="badge bg-charcoal-100 dark:bg-charcoal-700">{d.stage}</span>}
                    <button
                      onClick={() => { setExpandedDeal(expandedDeal === d.id ? null : d.id); setLinkSelect('') }}
                      className={`btn-ghost text-xs ${expandedDeal === d.id ? 'text-orange-500' : ''}`}
                      title="Linked assets"
                    >
                      🔗{(d.linked_asset_ids || []).length > 0 ? (d.linked_asset_ids || []).length : ''}
                    </button>
                    {canEdit && d.stage?.toLowerCase() === 'won' && (
                      <button
                        onClick={() => navigate(`/finance?view=invoices&client_contact=${contact.id}&amount=${d.value_cents || 0}&title=${encodeURIComponent(d.title)}&deal_id=${d.id}`)}
                        className="btn-ghost text-xs" title="Create invoice in Finance"
                      >🧾</button>
                    )}
                    {canEdit && <button onClick={() => contactsApi.removeDeal(contact.id, d.id).then(load)} className="btn-ghost text-xs text-red-500">×</button>}
                  </div>
                  {expandedDeal === d.id && (() => {
                    const jp = (fin?.deals || []).find(x => x.deal_id === d.id)
                    return (
                      <div className="ml-3 mt-1 mb-2 pl-3 border-l-2 border-charcoal-200 dark:border-charcoal-700 space-y-2 text-sm">
                        <div className="flex gap-1 flex-wrap items-center">
                          {(d.linked_asset_ids || []).length === 0 && (
                            <span className="text-xs text-charcoal-400">No linked assets.</span>
                          )}
                          {(d.linked_asset_ids || []).map(aid => {
                            const a = assetList.find(x => x.id === aid)
                            return (
                              <span key={aid} className="badge bg-charcoal-100 dark:bg-charcoal-700 flex items-center gap-1">
                                <button onClick={() => navigate(`/assets?asset=${aid}`)} className="hover:underline" title="Open asset">
                                  {a ? a.name : '(asset)'}
                                </button>
                                {canContribute && (
                                  <button onClick={() => unlinkAssetFromDeal(d.id, aid)} className="text-red-500" title="Unlink">×</button>
                                )}
                              </span>
                            )
                          })}
                        </div>
                        {canContribute && assetList.length > 0 && (
                          <div className="flex gap-2 items-center">
                            <select className="input !w-auto !py-1 text-xs flex-1 min-w-0" value={linkSelect} onChange={e => setLinkSelect(e.target.value)}>
                              <option value="">Link an asset…</option>
                              {assetList.filter(a => !(d.linked_asset_ids || []).includes(a.id)).map(a => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                              ))}
                            </select>
                            <button onClick={() => linkAssetToDeal(d.id)} disabled={!linkSelect} className="btn-ghost text-xs shrink-0">＋ Link</button>
                          </div>
                        )}
                        {dealInvs.length > 0 && (
                          <div className="space-y-1">
                            <span className="text-xs text-charcoal-500">Invoices from this deal:</span>
                            {dealInvs.map(inv => (
                              <div key={inv.id} className="flex items-center gap-2 text-xs">
                                <button onClick={() => navigate(`/finance?book=${inv.book_id}&view=invoices`)} className="font-mono text-orange-500 hover:underline">{inv.number}</button>
                                <span className="badge bg-charcoal-100 dark:bg-charcoal-700">{inv.status}</span>
                                {inv.overdue && <span className="text-red-500 font-medium">OVERDUE</span>}
                                <span className="ml-auto">
                                  {inv.balance_cents > 0 && inv.status !== 'draft'
                                    ? `${money(inv.balance_cents)} due`
                                    : money(inv.total_cents)}
                                </span>
                                <span className="text-charcoal-400">{inv.book_name}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {jp && (jp.invoiced_cents > 0 || jp.expenses_cents > 0) && (
                          <div className="text-xs text-charcoal-500 flex gap-3 flex-wrap border-t border-charcoal-200 dark:border-charcoal-700 pt-1.5">
                            <span>Invoiced <b>{money(jp.invoiced_cents)}</b></span>
                            <span>Collected <b className="text-green-600">{money(jp.collected_cents)}</b></span>
                            <span>Expenses <b className="text-red-500">{money(jp.expenses_cents)}</b></span>
                            <span>Net job profit <b className={jp.net_cents < 0 ? 'text-red-500' : 'text-green-600'}>{money(jp.net_cents)}</b></span>
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              ))}
            </div>
          )}
          {dForm && (
            <form onSubmit={saveDeal} className="mt-2 flex gap-2 flex-wrap items-center">
              <input className="input flex-1 min-w-[120px]" placeholder="Deal title" value={dForm.title} onChange={e => setDForm({ ...dForm, title: e.target.value })} autoFocus />
              <input className="input !w-24" inputMode="decimal" placeholder="Value" value={dForm.value} onChange={e => setDForm({ ...dForm, value: e.target.value })} />
              <select className="input !w-auto" value={dForm.stage} onChange={e => setDForm({ ...dForm, stage: e.target.value })}>
                {pipeline.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <button type="submit" className="btn-primary text-xs">Save</button>
              <button type="button" onClick={() => setDForm(null)} className="btn-ghost text-xs">Cancel</button>
            </form>
          )}
        </div>

        {/* Interactions */}
        <div>
          <h4 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 mb-2">Interactions</h4>
          {canContribute && (
            <form onSubmit={addInteraction} className="flex gap-2 flex-wrap items-start mb-3">
              <select className="input !w-auto" value={iForm.type} onChange={e => setIForm({ ...iForm, type: e.target.value })}>
                {['note', 'call', 'email', 'meeting', 'text'].map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <input className="input flex-1 min-w-[140px]" placeholder="Summary…" value={iForm.summary} onChange={e => setIForm({ ...iForm, summary: e.target.value })} />
              <input type="date" className="input !w-auto" title="Follow-up date" value={iForm.follow_up} onChange={e => setIForm({ ...iForm, follow_up: e.target.value })} />
              <button type="submit" className="btn-primary text-xs">Log</button>
            </form>
          )}
          <div className="space-y-2">
            {interactions.map(x => (
              <div key={x.id} className="text-sm border-l-2 border-charcoal-200 dark:border-charcoal-700 pl-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-charcoal-400">{x.date}</span>
                  <span className="badge bg-charcoal-100 dark:bg-charcoal-700">{x.type}</span>
                  {x.follow_up && !x.follow_up_done && <span className="text-xs text-orange-500">follow-up {x.follow_up}</span>}
                </div>
                {x.summary && <p className="whitespace-pre-wrap">{x.summary}</p>}
              </div>
            ))}
            {interactions.length === 0 && <p className="text-xs text-charcoal-400">No interactions logged.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function Contacts() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const [items, setItems] = useState([])
  const [fields, setFields] = useState([])
  const [pipeline, setPipeline] = useState(['Lead', 'Contacted', 'Proposal', 'Negotiation', 'Won', 'Lost'])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
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
    if (found) setDetail(found)
    searchParams.delete('contact')
    setSearchParams(searchParams, { replace: true })
  }, [loading, items, searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  const q = search.trim().toLowerCase()
  const filtered = items.filter(c => !q ||
    (c.name || '').toLowerCase().includes(q) ||
    (c.emails || []).some(e => e.toLowerCase().includes(q)) ||
    (c.tags || []).some(t => t.toLowerCase().includes(q)))

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
            <button key={c.id} onClick={() => setDetail(c)}
              className={`w-full text-left card p-3 flex items-center gap-3 hover:border-orange-500/40 ${c.archived ? 'opacity-50' : ''}`}>
              <span className="text-xl shrink-0">{c.type === 'company' ? '🏢' : '🧑'}</span>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{c.name}</p>
                <p className="text-xs text-charcoal-500 truncate">
                  {(c.emails || [])[0] || (c.phones || [])[0] || (c.tags || []).join(', ') || '—'}
                </p>
              </div>
              {c._owner && <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 shrink-0">{c._owner}</span>}
            </button>
          ))}
        </div>
      )}

      {modal && (
        <ContactModal
          contact={modal.contact}
          fields={fields}
          onClose={() => setModal(null)}
          onSaved={saved => { setModal(null); load(); if (detail) setDetail(saved) }}
        />
      )}
      {detail && (
        <ContactDetail
          contact={detail}
          fields={fields}
          pipeline={pipeline}
          onClose={() => setDetail(null)}
          onEdit={() => { setModal({ contact: detail }); setDetail(null) }}
          onChanged={load}
        />
      )}
    </div>
  )
}
