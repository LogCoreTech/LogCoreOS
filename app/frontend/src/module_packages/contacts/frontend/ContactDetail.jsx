import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { finance as financeApi } from '../../finance/frontend/api'
import { contacts as contactsApi } from './api'
import { assets as assetsApi } from '../../assets/frontend/api'
import { useWorkspace } from '../../../lib/workspace'
import ContactAvatar from './ContactAvatar'
import { formatPhone } from './phone'

const money = cents => `$${((cents || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const toCents = v => Math.round(parseFloat(v || '0') * 100) || 0

function formatHeight(cm, unit) {
  if (!cm) return ''
  if (unit === 'cm') return `${Math.round(cm)} cm`
  const totalIn = Math.round(cm / 2.54)
  return `${Math.floor(totalIn / 12)}'${totalIn % 12}"`
}

function formatWeight(kg, unit) {
  if (!kg) return ''
  if (unit === 'kg') return `${kg.toFixed(1)} kg`
  return `${(kg * 2.20462).toFixed(1)} lbs`
}

// A labeled group of profile fields — only ever renders when at least one of
// its fields is actually populated (decision: show everything populated,
// let empty fields/sections vanish entirely rather than showing placeholders).
// A list value (e.g. core_values, pill-based as of 2026-08-18) renders as
// pills instead of flat text.
function ProfileSection({ title, items, hiddenBadge }) {
  const populated = (items || []).filter(([, v]) => (Array.isArray(v) ? v.length > 0 : v))
  if (populated.length === 0) return null
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1 flex items-center gap-1.5">
        {title}{hiddenBadge}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
        {populated.map(([label, v]) => (
          <div key={label} className="min-w-0">
            <dt className="text-[11px] text-charcoal-400">{label}</dt>
            <dd className="text-sm break-words">
              {Array.isArray(v) ? (
                <span className="flex flex-wrap gap-1 mt-0.5">
                  {v.map(tag => (
                    <span key={tag} className="badge bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300">{tag}</span>
                  ))}
                </span>
              ) : v}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

// Small, non-interactive "hidden from others" marker next to a section
// heading — owner-view-only (toggling itself only happens in edit mode via
// ContactModal/SectionHeader), so there's a way to notice a section is
// hidden without opening edit mode.
function HiddenBadge() {
  return (
    <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-500 dark:text-charcoal-400 text-[10px] normal-case">
      hidden from others
    </span>
  )
}

// Read-first view of a single contact — everything laid out to read at a
// glance. ContactModal (the edit form) is a separate component; the ✎ Edit
// button flips the caller's mode, mirroring the AssetView/AssetModal split.
export default function ContactDetail({ contact, fields, pipeline, user, onClose, onEdit, fullPage = false }) {
  const navigate = useNavigate()
  const { workspace } = useWorkspace()
  const canEdit = contact._access === 'edit'
  const canContribute = contact._access === 'edit' || contact._access === 'contribute'
  const isMe = contact.self_of && contact.self_of === user?.name
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
  const [allContacts, setAllContacts] = useState([])      // for resolving affiliated/employer contact names

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

  useEffect(() => {
    const needsLookup = (contact.affiliated_contact_ids || []).length > 0 ||
      (contact.career_history || []).some(c => c.company_id)
    if (!needsLookup) return
    contactsApi.list().then(r => setAllContacts(Array.isArray(r) ? r : [])).catch(() => {})
  }, [contact.affiliated_contact_ids, contact.career_history])

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

  const affiliated = (contact.affiliated_contact_ids || [])
    .map(id => allContacts.find(c => c.id === id))
    .filter(Boolean)
  const companyName = id => allContacts.find(c => c.id === id)?.name
  const career = contact.career_history || []
  const currentCareer = career.find(c => !c.archived)
  // Most recent past role first — matches CareerHistoryEditor's own sort.
  const pastCareer = [...career.filter(c => c.archived)].sort((a, b) => (b.start_date || '').localeCompare(a.start_date || ''))
  // Owner-only "hidden from others" markers (2026-08-18) — a non-owner
  // viewer never needs this: a hidden section's fields are already stripped
  // server-side, so it just reads as empty/absent to them, same as any
  // other unfilled section.
  const hiddenSections = contact.hidden_sections || []
  const isHidden = key => isMe && hiddenSections.includes(key)

  const cardShell = fullPage ? 'w-full max-w-2xl mx-auto p-4 md:p-0' : 'modal-card max-w-2xl w-full p-5 max-h-[90dvh] overflow-y-auto'

  return (
    <div className={fullPage ? '' : 'modal-overlay'}>
      <div className={cardShell}>
        {fullPage && (
          <button onClick={onClose} className="text-sm text-charcoal-500 hover:text-orange-500 transition-colors mb-2">← Back</button>
        )}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-3 min-w-0">
            <ContactAvatar contact={contact} size="w-12 h-12" textSize="text-2xl" />
            <div className="min-w-0">
              <h3 className="font-semibold text-lg truncate">{contact.name}</h3>
              <div className="flex gap-1 flex-wrap mt-1">
                {isMe && <span className="badge bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 font-semibold">ME</span>}
                {contact.status && <span className="badge bg-charcoal-100 dark:bg-charcoal-700">{contact.status}</span>}
                {(contact.tags || []).map(t => <span key={t} className="badge bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300">{t}</span>)}
                {contact._owner && <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">{contact._owner}</span>}
              </div>
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            {canEdit && <button onClick={onEdit} className="btn-ghost text-sm">✎ Edit</button>}
            {!fullPage && <button onClick={onClose} className="btn-ghost text-sm">✕</button>}
          </div>
        </div>

        <div className="space-y-4">
          {/* Basic contact info */}
          <div className="text-sm space-y-1">
            {(contact.emails || []).map(e => <p key={e}>✉️ <a href={`mailto:${e}`} className="text-orange-600">{e}</a></p>)}
            {(contact.phones || []).map((p, i) => <p key={i}>📞 {formatPhone(p)}</p>)}
            {contact.address && <p className="flex items-center gap-1.5">📍 {contact.address} {isHidden('address') && <HiddenBadge />}</p>}
            {contact.birthday && <p>🎂 {contact.birthday}</p>}
            {(contact.city || contact.state || contact.country) && (
              <p>🌎 {[contact.city, contact.state, contact.country].filter(Boolean).join(', ')}</p>
            )}
            {contact.pronouns && <p className="text-charcoal-500">{contact.pronouns}</p>}
            {fields.filter(f => (f.applies_to || ['person', 'company']).includes(contact.type)).map(f => contact.custom?.[f.key] != null && contact.custom[f.key] !== '' && (
              <p key={f.key}><span className="text-charcoal-500">{f.label}:</span> {String(contact.custom[f.key])}</p>
            ))}
          </div>

          {contact.type !== 'company' && (currentCareer || pastCareer.length > 0) && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1 flex items-center gap-1.5">
                Career{isHidden('career') && <HiddenBadge />}
              </div>
              {currentCareer && (
                <div className="text-sm space-y-0.5">
                  <p className="font-medium">
                    {currentCareer.title || '(untitled role)'}
                    {companyName(currentCareer.company_id) && ` · ${companyName(currentCareer.company_id)}`}
                    {currentCareer.start_date && <span className="text-charcoal-400 font-normal"> (since {currentCareer.start_date})</span>}
                  </p>
                  {currentCareer.industry && <p className="text-charcoal-500">{currentCareer.industry}</p>}
                  {currentCareer.education && <p className="text-charcoal-500">{currentCareer.education}</p>}
                  {currentCareer.years_experience && <p className="text-charcoal-500">{currentCareer.years_experience} experience</p>}
                  {currentCareer.skills && <p className="text-charcoal-500">{currentCareer.skills}</p>}
                </div>
              )}
              {pastCareer.length > 0 && (
                <div className="mt-1.5 space-y-0.5">
                  {pastCareer.map((c, i) => (
                    <p key={c.id || i} className="text-xs text-charcoal-400">
                      {c.title || '(untitled role)'}{companyName(c.company_id) ? ` · ${companyName(c.company_id)}` : ''} ({c.start_date || '?'}–{c.end_date || '?'})
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {contact.type === 'company' && (contact.locations || []).length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">Locations</div>
              <div className="text-sm space-y-0.5">
                {contact.locations.map(l => (
                  <p key={l.id}>📍 {l.label && <span className="font-medium">{l.label}:</span>} {l.address}</p>
                ))}
              </div>
            </div>
          )}

          {contact.type === 'company' && (contact.hours || []).some(h => !h.closed) && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">Hours</div>
              <dl className="text-sm grid grid-cols-2 gap-x-4 gap-y-0.5">
                {contact.hours.map(h => (
                  <div key={h.day} className="flex justify-between gap-2">
                    <dt className="text-charcoal-500 capitalize">{h.day}</dt>
                    <dd>{h.closed ? 'Closed' : `${h.open || '?'}–${h.close || '?'}`}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {(contact.type === 'company' || contact.marital_status || contact.pets || affiliated.length > 0) && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1 flex items-center gap-1.5">
                {contact.type === 'company' ? 'Affiliated People' : 'Family'}{isHidden('family') && <HiddenBadge />}
              </div>
              {contact.type !== 'company' && (
                <div className="text-sm space-y-1">
                  {contact.marital_status && <p>{contact.marital_status}</p>}
                  {contact.pets && <p>🐾 {contact.pets}</p>}
                </div>
              )}
              {affiliated.length > 0 ? (
                <div className="flex gap-1 flex-wrap mt-1">
                  {affiliated.map(a => (
                    <button key={a.id} onClick={() => navigate(`/contacts?contact=${a.id}`)}
                      className="badge bg-charcoal-100 dark:bg-charcoal-700 hover:underline">
                      {a.type === 'company' ? '🏢' : '🧑'} {a.name}
                    </button>
                  ))}
                </div>
              ) : contact.type === 'company' && (
                <p className="text-xs text-charcoal-400">No one linked yet.</p>
              )}
            </div>
          )}

          <ProfileSection title="Values & Principles" hiddenBadge={isHidden('values_principles') && <HiddenBadge />} items={[
            ['Life mission', contact.life_mission], ['Core values', contact.core_values],
            ['Key constraints', contact.key_constraints],
          ]} />

          {contact.priority_order?.[workspace]?.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1 flex items-center gap-1.5">
                {workspace === 'business' ? 'Business Priorities' : 'Life Priorities'}{isHidden('priorities') && <HiddenBadge />}
              </div>
              <ol className="text-sm list-decimal list-inside space-y-0.5">
                {contact.priority_order[workspace].map(cat => <li key={cat}>{cat}</li>)}
              </ol>
            </div>
          )}

          <ProfileSection title="Daily Routine" items={[
            ['Wake (weekdays)', contact.wake_weekday], ['Wake (weekends)', contact.wake_weekend],
            ['Bedtime', contact.bedtime],
            ['Work hours', contact.work_start || contact.work_end ? `${contact.work_start || '?'}–${contact.work_end || '?'}` : ''],
          ]} />

          <ProfileSection title="Health" items={[
            ['Height', formatHeight(contact.height_cm, contact.height_unit)],
            ['Weight', formatWeight(contact.weight_kg, contact.weight_unit)],
            ['Blood type', contact.blood_type],
            ['Conditions', contact.conditions], ['Medications', contact.medications],
            ['Dietary restrictions', contact.diet], ['Exercise', contact.exercise],
          ]} />

          <ProfileSection title="Finances" items={[
            ['Income range', contact.income_range], ['Budget style', contact.budget_style],
          ]} />

          <ProfileSection title="AI Preferences" items={[
            ['Communication style', contact.communication_style], ['Tone', contact.tone],
            ['Response language', contact.response_language],
            ['Emphasize', contact.topics_to_emphasize], ['Avoid', contact.topics_to_avoid],
          ]} />

          {contact.notes && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-charcoal-400 mb-1">Notes</div>
              <p className="text-sm whitespace-pre-wrap break-words text-charcoal-600 dark:text-charcoal-300">{contact.notes}</p>
            </div>
          )}

          {/* References — money + every record linked to this contact */}
          {((fin?.available && (fin.tx_count > 0 || (fin.invoices || []).length > 0)) || refAssets.length > 0) && (
            <div className="card p-3 text-sm space-y-2">
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
          <div>
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
          {/* fullPage renders as normal page content inside <main>, which the
              fixed mobile footer nav floats over — without this the last
              section sits behind the footer until you force-scroll past it. */}
          {fullPage && <div className="h-20 md:hidden" aria-hidden="true" />}
        </div>
      </div>
    </div>
  )
}
