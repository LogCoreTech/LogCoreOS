import { useEffect, useRef, useState } from 'react'
import { homes as homesApi } from './api'
import HomeHero from './HomeHero'
import TaggedItemRow from './TaggedItemRow'
import ContactPicker from '../../../components/contacts/ContactPicker'
import TaskModal from '../../../components/TaskModal'
import { handleTabListKeyDown } from '../../../lib/tabListKeyboard'

const TABS = ['overview', 'tasks', 'notes', 'money', 'events', 'assets', 'contacts']
const TAB_LABELS = {
  overview: 'Overview',
  tasks: 'Tasks',
  notes: 'Notes',
  money: 'Money',
  events: 'Events',
  assets: 'Assets',
  contacts: 'Contacts',
}

function daysUntil(dateStr) {
  if (!dateStr) return null
  const diff = new Date(dateStr) - new Date()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function yearsSince(dateStr) {
  if (!dateStr) return null
  const years = (new Date() - new Date(dateStr)) / (1000 * 60 * 60 * 24 * 365.25)
  return Math.max(0, Math.floor(years))
}

// A pool-scoped task/goal/event doesn't come back from search() with
// `_module` set to "tasks"/"goals"/"calendar" — household's/team's own
// SearchProviderSpecs cover those (not tasks'/goals'/calendar's own
// personal-only providers), so `_module` is "household"/"team" instead,
// same as any of THEIR OTHER record types would be. `_provider` is the
// fully namespaced key search_service.py actually assigns per result
// ("household:events", "tasks:tasks", "team:goals", ...) — every provider
// across every module that can hold this record type uses the same
// suffix ("tasks"/"goals"/"events"/"notes"/"finance") regardless of which
// module owns it, so the suffix alone is what actually identifies the
// record type. Real bug found live 2026-09-18: household/team events
// showed up in Overview's unfiltered "recent activity" but never in the
// Events tab, which checked `_module === 'calendar'` only.
function itemKind(item) {
  return (item._provider || item._module || '').split(':').pop()
}

// Owner ask, 2026-09-18: a past calendar event tagged with a home is
// no longer useful to see there — hide it rather than let the Events tab
// (and Overview's recent-activity preview) accumulate every event that's
// already happened. Date-only comparison (not time-of-day) so an event
// happening later today never disappears before it's actually over.
function isPastEvent(item) {
  if (itemKind(item) !== 'events') return false
  const dateStr = item.end_date || item.start_date
  if (!dateStr) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return new Date(dateStr) < today
}

// Owner ask, 2026-09-18: quick-create common maintenance/warranty reminders
// tagged with the home, mirroring Goals' own "+ Task" button (GoalModal.jsx's
// poolTaskApi/PoolAwareTaskCreateModal) rather than inventing a bypass —
// this always opens the real TaskModal, pre-filled, so the user still
// reviews/adjusts before saving.
const REMINDER_PRESETS = [
  { key: 'hvac_filter', label: 'HVAC filter — monthly', title: 'Replace HVAC filter' },
  { key: 'gutter_cleaning', label: 'Gutter cleaning — every 6 months', title: 'Clean gutters' },
  {
    key: 'smoke_detector',
    label: 'Smoke detector batteries — every 6 months',
    title: 'Replace smoke detector batteries',
  },
  { key: 'water_heater', label: 'Water heater flush — yearly', title: 'Flush water heater' },
  { key: 'custom', label: 'Custom…', title: '' },
]

// Dates computed from "today" at pick-time, no clamping — same convention
// RecurrencePicker.jsx's own defaultRuleForFreq() already uses. The user can
// still edit this in the real, editable RecurrencePicker before saving.
function presetRecurrence(key) {
  const d = new Date()
  const day = d.getDate()
  const month = d.getMonth() + 1
  switch (key) {
    case 'hvac_filter':
      return { freq: 'monthly', interval: 1, month_day: day }
    case 'gutter_cleaning':
    case 'smoke_detector':
      return { freq: 'monthly', interval: 6, month_day: day }
    case 'water_heater':
      return { freq: 'yearly', interval: 1, month, month_day: day }
    default:
      return null
  }
}

// Not cross-imported from GoalModal.jsx (which defines/exports its own copy
// locally too) — Homes keeps its own pieces self-contained, same convention
// homes/backend/service.py's own docstring already states.
async function poolTaskApi(workspace) {
  if (workspace === 'business') {
    const { team } = await import('../../team/frontend/api')
    return team
  }
  const { shared } = await import('../../household/frontend/api')
  return shared
}

function fmtMoney(n) {
  if (n === null || n === undefined) return null
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function StatChip({ label, value }) {
  if (value === null || value === undefined) return null
  return (
    <div className="card px-3 py-2 flex-1 min-w-[110px]">
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</p>
      <p className="text-sm font-semibold">{value}</p>
    </div>
  )
}

export default function HomeDetail({
  home, pool, workspace, onChanged, canEdit, canConvertToPool, poolLabel, onConvertToPool,
  converting, onDeleteHome,
}) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('overview')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [reminderPreset, setReminderPreset] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const tabRefs = useRef([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    homesApi.items(home.id, pool)
      .then(r => { if (!cancelled) setItems(r.items || []) })
      .catch(() => { if (!cancelled) setItems([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [home.id, pool, refreshKey])

  const visibleItems = items.filter(i => !isPastEvent(i))
  const taskCount = visibleItems.filter(i => ['tasks', 'goals'].includes(itemKind(i))).length
  const noteCount = visibleItems.filter(i => itemKind(i) === 'notes').length

  const variant = home.ownership_type === 'rent' ? home.rent : home.own
  const isRent = home.ownership_type === 'rent'

  function startEdit() {
    setForm({
      name: home.name,
      address: home.address || '',
      notes: home.notes || '',
      ownership_type: home.ownership_type,
      rent: { ...(home.rent || {}) },
      own: { ...(home.own || {}) },
    })
    setError('')
    setEditing(true)
  }

  async function save() {
    setSaving(true)
    setError('')
    try {
      const payload = {
        name: form.name,
        address: form.address,
        notes: form.notes,
        ownership_type: form.ownership_type,
        [form.ownership_type]: form.ownership_type === 'rent' ? form.rent : form.own,
        // Real bug found live 2026-09-18: without this, a home converted to
        // the household/team pool 404'd on its very next edit — the update
        // request never said which store to look in, so it defaulted to
        // the caller's own personal store (HomeUpdate.pool defaults False),
        // which no longer has the record after conversion.
        pool: !!pool,
      }
      const updated = await homesApi.update(home.id, payload)
      setEditing(false)
      onChanged?.(updated)
    } catch (e) {
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const filtered = {
    overview: visibleItems.slice(0, 5),
    tasks: visibleItems.filter(i => ['tasks', 'goals'].includes(itemKind(i))),
    notes: visibleItems.filter(i => itemKind(i) === 'notes'),
    money: visibleItems.filter(i => itemKind(i) === 'finance'),
    events: visibleItems.filter(i => itemKind(i) === 'events'),
    assets: visibleItems.filter(i => itemKind(i) === 'assets'),
    contacts: visibleItems.filter(i => itemKind(i) === 'contacts'),
  }

  return (
    <div className="space-y-4">
      <HomeHero home={home} />

      {!pool && canConvertToPool && (
        <button
          onClick={onConvertToPool}
          disabled={converting}
          className="text-sm text-orange-500 hover:text-orange-600 font-medium"
        >
          {converting ? 'Sharing…' : `Share with ${poolLabel} →`}
        </button>
      )}

      <div className="flex gap-2 flex-wrap">
        {isRent ? (
          <>
            <StatChip label="Rent" value={fmtMoney(variant?.monthly_rent) ? `${fmtMoney(variant.monthly_rent)}/mo` : null} />
            <StatChip
              label="Lease"
              value={
                variant?.lease_end
                  ? (daysUntil(variant.lease_end) >= 0 ? `${daysUntil(variant.lease_end)}d left` : 'Expired')
                  : 'Month-to-month'
              }
            />
            <StatChip label="Deposit" value={fmtMoney(variant?.security_deposit)} />
          </>
        ) : (
          <>
            <StatChip label="Payment" value={fmtMoney(variant?.monthly_payment) ? `${fmtMoney(variant.monthly_payment)}/mo` : null} />
            <StatChip label="Owned" value={variant?.purchase_date ? `${yearsSince(variant.purchase_date)}y` : null} />
            <StatChip label="Property tax" value={fmtMoney(variant?.property_tax_annual) ? `${fmtMoney(variant.property_tax_annual)}/yr` : null} />
          </>
        )}
        <StatChip label="Open tasks" value={loading ? '…' : taskCount} />
        <StatChip label="Notes" value={loading ? '…' : noteCount} />
      </div>

      <div role="tablist" aria-label="Home view" className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1 overflow-x-auto">
        {TABS.map((t, i) => (
          <button
            key={t}
            ref={el => { tabRefs.current[i] = el }}
            role="tab"
            aria-selected={tab === t}
            tabIndex={tab === t ? 0 : -1}
            onClick={() => setTab(t)}
            onKeyDown={e => handleTabListKeyDown(e, { tabs: TABS, activeIndex: i, onActivate: setTab, refs: tabRefs })}
            className={`flex-1 py-1.5 px-2 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              tab === t
                ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                : 'text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">Details</h2>
              {canEdit && !editing && (
                <button onClick={startEdit} className="text-sm text-orange-500 hover:text-orange-600">Edit</button>
              )}
            </div>

            {!editing ? (
              <div className="space-y-1 text-sm">
                <p><span className="text-charcoal-500 dark:text-charcoal-400">Tag:</span> <span className="font-mono">{home.tag}</span></p>
                {home.address && <p><span className="text-charcoal-500 dark:text-charcoal-400">Address:</span> {home.address}</p>}
                {isRent ? (
                  <>
                    {variant?.landlord_name && <p><span className="text-charcoal-500 dark:text-charcoal-400">Landlord:</span> {variant.landlord_name}</p>}
                    {variant?.lease_start && <p><span className="text-charcoal-500 dark:text-charcoal-400">Lease:</span> {variant.lease_start} → {variant.lease_end || '—'}</p>}
                  </>
                ) : (
                  <>
                    {variant?.lender_name && <p><span className="text-charcoal-500 dark:text-charcoal-400">Lender:</span> {variant.lender_name}</p>}
                    {variant?.purchase_date && <p><span className="text-charcoal-500 dark:text-charcoal-400">Purchased:</span> {variant.purchase_date}</p>}
                  </>
                )}
                {home.notes && <p className="pt-1 text-charcoal-600 dark:text-charcoal-300">{home.notes}</p>}
              </div>
            ) : (
              <div className="space-y-3">
                {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}
                <div>
                  <label className="block text-sm font-medium mb-1">Name</label>
                  <input className="input w-full" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Address</label>
                  <input className="input w-full" value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
                </div>
                {form.ownership_type === 'rent' ? (
                  <>
                    <ContactPicker
                      label="Landlord"
                      pool={!!pool}
                      value={{ name: form.rent.landlord_name, contactId: form.rent.landlord_contact_id }}
                      onChange={(name, contactId) => setForm(f => ({ ...f, rent: { ...f.rent, landlord_name: name, landlord_contact_id: contactId } }))}
                    />
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-sm font-medium mb-1">Monthly rent</label>
                        <input type="text" inputMode="decimal" className="input w-full" value={form.rent.monthly_rent || ''} onChange={e => setForm(f => ({ ...f, rent: { ...f.rent, monthly_rent: e.target.value } }))} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Security deposit</label>
                        <input type="text" inputMode="decimal" className="input w-full" value={form.rent.security_deposit || ''} onChange={e => setForm(f => ({ ...f, rent: { ...f.rent, security_deposit: e.target.value } }))} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Lease start</label>
                        <input type="date" className="input w-full" value={form.rent.lease_start || ''} onChange={e => setForm(f => ({ ...f, rent: { ...f.rent, lease_start: e.target.value } }))} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Lease end</label>
                        <input type="date" className="input w-full" value={form.rent.lease_end || ''} onChange={e => setForm(f => ({ ...f, rent: { ...f.rent, lease_end: e.target.value } }))} />
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <ContactPicker
                      label="Lender"
                      pool={!!pool}
                      value={{ name: form.own.lender_name, contactId: form.own.lender_contact_id }}
                      onChange={(name, contactId) => setForm(f => ({ ...f, own: { ...f.own, lender_name: name, lender_contact_id: contactId } }))}
                    />
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-sm font-medium mb-1">Monthly payment</label>
                        <input type="text" inputMode="decimal" className="input w-full" value={form.own.monthly_payment || ''} onChange={e => setForm(f => ({ ...f, own: { ...f.own, monthly_payment: e.target.value } }))} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Purchase price</label>
                        <input type="text" inputMode="decimal" className="input w-full" value={form.own.purchase_price || ''} onChange={e => setForm(f => ({ ...f, own: { ...f.own, purchase_price: e.target.value } }))} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Purchase date</label>
                        <input type="date" className="input w-full" value={form.own.purchase_date || ''} onChange={e => setForm(f => ({ ...f, own: { ...f.own, purchase_date: e.target.value } }))} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Property tax / yr</label>
                        <input type="text" inputMode="decimal" className="input w-full" value={form.own.property_tax_annual || ''} onChange={e => setForm(f => ({ ...f, own: { ...f.own, property_tax_annual: e.target.value } }))} />
                      </div>
                    </div>
                  </>
                )}
                <div>
                  <label className="block text-sm font-medium mb-1">Notes</label>
                  <textarea className="input w-full" rows={2} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
                </div>
                <div className="flex gap-2">
                  <button onClick={save} disabled={saving} className="btn-primary">{saving ? 'Saving…' : 'Save'}</button>
                  <button onClick={() => setEditing(false)} className="btn-ghost">Cancel</button>
                  {onDeleteHome && (
                    <button
                      type="button"
                      onClick={onDeleteHome}
                      className="ml-auto px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                    >
                      Delete home
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          <div>
            <h2 className="font-semibold mb-2 text-sm text-charcoal-500 dark:text-charcoal-400">Recent activity</h2>
            {loading ? (
              <p className="text-sm text-charcoal-400">Loading…</p>
            ) : filtered.overview.length === 0 ? (
              <p className="text-sm text-charcoal-400">Nothing tagged with <span className="font-mono">{home.tag}</span> yet.</p>
            ) : (
              <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
                {filtered.overview.map(item => <TaggedItemRow key={`${item._module}-${item.record_id}`} item={item} />)}
              </div>
            )}
          </div>
        </div>
      )}

      {tab !== 'overview' && (
        <div className="space-y-3">
          {tab === 'tasks' && canEdit && (
            <div className="flex justify-end">
              <select
                className="input !w-auto text-sm"
                value=""
                onChange={e => { if (e.target.value) setReminderPreset(e.target.value) }}
              >
                <option value="">+ Reminder</option>
                {REMINDER_PRESETS.map(p => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </select>
            </div>
          )}
          {loading ? (
            <p className="text-sm text-charcoal-400">Loading…</p>
          ) : filtered[tab].length === 0 ? (
            <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
              <p className="text-sm">Nothing here yet. Tag a {tab === 'money' ? 'transaction' : tab.slice(0, -1)} with <span className="font-mono">{home.tag}</span> to see it here.</p>
            </div>
          ) : (
            <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
              {filtered[tab].map(item => <TaggedItemRow key={`${item._module}-${item.record_id}`} item={item} />)}
            </div>
          )}
        </div>
      )}

      {reminderPreset && (
        <HomeTaskCreateModal
          pool={!!pool}
          workspace={workspace}
          home={home}
          presetKey={reminderPreset}
          onClose={() => setReminderPreset(null)}
          onSave={() => { setReminderPreset(null); setRefreshKey(k => k + 1) }}
        />
      )}
    </div>
  )
}

// Mirrors GoalModal.jsx's own PoolAwareTaskCreateModal verbatim — resolves
// the pool task API client asynchronously (dynamic import) before rendering
// TaskModal, since a pool home's reminder must be created in the household/
// team store, not the caller's own personal one.
function HomeTaskCreateModal({ pool, workspace, home, presetKey, onClose, onSave }) {
  const [saveApi, setSaveApi] = useState(undefined)
  const [ready, setReady] = useState(!pool)

  useEffect(() => {
    if (!pool) return
    poolTaskApi(workspace).then(api => { setSaveApi(() => api); setReady(true) })
  }, [pool, workspace])

  if (!ready) return null

  const preset = REMINDER_PRESETS.find(p => p.key === presetKey)
  const recurrence = presetRecurrence(presetKey)

  return (
    <TaskModal
      defaultTags={[home.tag]}
      defaultTitle={preset?.title || ''}
      defaultRecurrence={recurrence}
      defaultType={recurrence ? 'recurring' : undefined}
      saveApi={saveApi}
      onClose={onClose}
      onSave={onSave}
    />
  )
}
