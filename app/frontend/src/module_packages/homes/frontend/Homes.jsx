import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { homes as homesApi } from './api'
import HomeDetail from './HomeDetail'
import HelpButton from '../../../components/HelpButton'
import ConfirmDialog from '../../../components/ConfirmDialog'
import { useAuth } from '../../../lib/auth'
import { useWorkspace } from '../../../lib/workspace'
import useEscapeToClose from '../../../lib/useEscapeToClose'
import useFocusTrap from '../../../lib/useFocusTrap'
import useScrollLock from '../../../lib/useScrollLock'

function Portal({ children }) {
  return createPortal(children, document.body)
}

function emptyForm() {
  return { name: '', ownership_type: 'rent', address: '', pool: false, rent: {}, own: {} }
}

function NewHomeModal({ onClose, onCreated, canCreatePool, poolLabel }) {
  const [form, setForm] = useState(emptyForm())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const cardRef = useRef(null)

  useEscapeToClose(onClose)
  useFocusTrap(cardRef)
  useScrollLock()

  async function submit(e) {
    e.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    setError('')
    try {
      const payload = {
        name: form.name,
        ownership_type: form.ownership_type,
        address: form.address,
        pool: form.pool,
        [form.ownership_type]: form[form.ownership_type],
      }
      const created = await homesApi.create(payload)
      onCreated(created)
    } catch (err) {
      setError(err.message || 'Failed to create home')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Portal>
      <div className="modal-overlay" onClick={onClose}>
        <div ref={cardRef} className="modal-card max-w-md" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between gap-2 mb-4">
            <h2 className="font-semibold">New Home</h2>
            <button onClick={onClose} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-600">✕</button>
          </div>
          <form onSubmit={submit} className="space-y-3">
            {error && <p className="text-sm text-red-500 dark:text-red-400">{error}</p>}
            <div>
              <label className="block text-sm font-medium mb-1">Name</label>
              <input
                className="input w-full"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. 123 Main St"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Address</label>
              <input className="input w-full" value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
            </div>
            <div>
              <span className="block text-sm font-medium mb-1">Do you rent or own it?</span>
              <div role="radiogroup" className="flex gap-2">
                {['rent', 'own'].map(t => (
                  <button
                    key={t}
                    type="button"
                    role="radio"
                    aria-checked={form.ownership_type === t}
                    onClick={() => setForm(f => ({ ...f, ownership_type: t }))}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      form.ownership_type === t
                        ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                        : 'border-charcoal-200 dark:border-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                    }`}
                  >
                    {t === 'rent' ? '🔑 Rent' : '🏡 Own'}
                  </button>
                ))}
              </div>
            </div>
            {form.ownership_type === 'rent' ? (
              <div>
                <label className="block text-sm font-medium mb-1">Monthly rent</label>
                <input type="text" inputMode="decimal" className="input w-full" value={form.rent.monthly_rent || ''} onChange={e => setForm(f => ({ ...f, rent: { ...f.rent, monthly_rent: e.target.value } }))} />
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium mb-1">Monthly payment</label>
                <input type="text" inputMode="decimal" className="input w-full" value={form.own.monthly_payment || ''} onChange={e => setForm(f => ({ ...f, own: { ...f.own, monthly_payment: e.target.value } }))} />
              </div>
            )}
            {canCreatePool && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.pool} onChange={e => setForm(f => ({ ...f, pool: e.target.checked }))} className="accent-orange-500 w-4 h-4" />
                <span className="text-sm">Share with everyone in the {poolLabel}</span>
              </label>
            )}
            <p className="text-xs text-charcoal-400">More details (lease dates, purchase price, linked contact) can be added after creation.</p>
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={saving || !form.name.trim()} className="btn-primary">{saving ? 'Creating…' : 'Create Home'}</button>
              <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
            </div>
          </form>
        </div>
      </div>
    </Portal>
  )
}

export default function Homes() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const [homes, setHomes] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [confirmState, setConfirmState] = useState(null)
  const [converting, setConverting] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()

  // Same poolId/poolLabel split Goals'/Calendar's own frontend already use —
  // business workspace's pool is Team, personal workspace's is Household.
  const poolId = workspace === 'business' ? 'team' : 'household'
  const poolLabel = workspace === 'business' ? 'Team' : 'Household'
  const canCreatePool = user?.role === 'admin' || (user?.poolEdit || []).includes(poolId)

  async function load() {
    setLoading(true)
    try {
      const list = await homesApi.list()
      setHomes(list)
      if (list.length > 0 && !list.some(h => h.id === selectedId)) {
        setSelectedId(list[0].id)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Deep link (?homeId=<id>) — app-wide search bar click-through, now that
  // Homes has its own SearchProviderSpec (2026-09-20). Same "wait for the
  // list to load, then select and strip the param" shape Calendar.jsx's own
  // `?event=` handling already uses.
  useEffect(() => {
    const target = searchParams.get('homeId')
    if (!target || loading) return
    if (homes.some(h => h.id === target)) setSelectedId(target)
    searchParams.delete('homeId')
    setSearchParams(searchParams, { replace: true })
  }, [loading, homes, searchParams, setSearchParams])

  const selected = homes.find(h => h.id === selectedId) || null
  const selectedIsPool = selected?._owner === 'household' || selected?._owner === 'team'

  function handleCreated(created) {
    setShowCreate(false)
    setHomes(prev => [...prev, created])
    setSelectedId(created.id)
  }

  function handleUpdated(updated) {
    setHomes(prev => prev.map(h => (h.id === updated.id ? { ...h, ...updated } : h)))
  }

  function confirmConvertToPool() {
    if (!selected) return
    setConfirmState({
      title: `Share with ${poolLabel}`,
      message: `Everyone in your ${poolLabel} will be able to see and edit "${selected.name}" going forward. This can't be undone from here — to make it private again later, delete it (recoverable from Trash) and recreate it as personal.`,
      confirmLabel: 'Share',
      onConfirm: async () => {
        setConfirmState(null)
        setConverting(true)
        try {
          const converted = await homesApi.convertToPool(selected.id)
          setHomes(prev => prev.map(h => (h.id === converted.id ? converted : h)))
        } finally {
          setConverting(false)
        }
      },
    })
  }

  function confirmDelete() {
    if (!selected) return
    setConfirmState({
      title: 'Delete home',
      message: `Delete "${selected.name}"? It moves to Trash and can be restored within 30 days. Tagged items elsewhere are never touched.`,
      confirmLabel: 'Delete',
      danger: true,
      onConfirm: async () => {
        setConfirmState(null)
        await homesApi.remove(selected.id, selectedIsPool)
        setHomes(prev => prev.filter(h => h.id !== selected.id))
        setSelectedId(null)
      },
    })
  }

  return (
    <div className="w-full max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Homes</h1>
          <HelpButton section="homes" />
        </span>
        <button onClick={() => setShowCreate(true)} className="btn-primary">＋ New Home</button>
      </div>

      {loading ? (
        <div className="space-y-3">{[1, 2].map(i => <div key={i} className="h-24 card animate-pulse" />)}</div>
      ) : homes.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-4xl mb-2">🏘️</p>
          <p className="mb-1">No homes yet.</p>
          <p className="text-sm">Add one to start pulling its tasks, notes, and money together in one place.</p>
        </div>
      ) : (
        <>
          <div className="flex gap-2 flex-wrap">
            {homes.map(h => (
              <button
                key={h.id}
                onClick={() => setSelectedId(h.id)}
                className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                  selectedId === h.id
                    ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                    : 'border-charcoal-200 dark:border-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                }`}
              >
                {h.icon || '🏘️'} {h.name}
                {h._owner === 'household' && ' 🏠'}
                {h._owner === 'team' && ' 🧑‍🤝‍🧑'}
              </button>
            ))}
          </div>

          {selected && (
            <HomeDetail
              home={selected}
              pool={selectedIsPool}
              workspace={workspace}
              onChanged={handleUpdated}
              canEdit
              canConvertToPool={canCreatePool}
              poolLabel={poolLabel}
              onConvertToPool={confirmConvertToPool}
              converting={converting}
              onDeleteHome={confirmDelete}
            />
          )}
        </>
      )}

      {showCreate && (
        <NewHomeModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
          canCreatePool={canCreatePool}
          poolLabel={poolLabel}
        />
      )}

      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          message={confirmState.message}
          danger={confirmState.danger}
          confirmLabel={confirmState.confirmLabel}
          onConfirm={confirmState.onConfirm}
          onCancel={() => setConfirmState(null)}
        />
      )}
    </div>
  )
}
