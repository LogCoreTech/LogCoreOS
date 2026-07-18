import { useState, useEffect, useCallback, useRef } from 'react'
import HelpButton from '../components/HelpButton'
import { home as homeApi } from '../lib/api'

const DOMAIN_TABS = [
  { id: 'all',       label: 'All' },
  { id: 'light',     label: 'Lights' },
  { id: 'climate',   label: 'Climate' },
  { id: 'switch',    label: 'Switches' },
  { id: 'sensor',    label: 'Sensors' },
  { id: 'cover',     label: 'Covers' },
  { id: 'lock',      label: 'Locks' },
]

function entityDomain(entity_id) {
  return (entity_id || '').split('.')[0]
}

function friendlyName(entity) {
  return entity?.attributes?.friendly_name || entity?.entity_id || ''
}

function stateColor(state) {
  if (state === 'on') return 'text-orange-500 dark:text-orange-400'
  if (state === 'off') return 'text-charcoal-400 dark:text-charcoal-500'
  return 'text-charcoal-500 dark:text-charcoal-400'
}

// ── Entity tile ───────────────────────────────────────────────────────────────

function EntityTile({ entity, isFav, onToggleFav, onCall }) {
  const [busy, setBusy] = useState(false)
  const [localState, setLocalState] = useState(entity.state)
  const domain = entityDomain(entity.entity_id)
  const attrs = entity.attributes || {}

  useEffect(() => { setLocalState(entity.state) }, [entity.state])

  async function toggle() {
    if (busy) return
    setBusy(true)
    const next = localState === 'on' ? 'off' : 'on'
    setLocalState(next)
    try {
      await onCall(entity.entity_id, `turn_${next}`, {})
    } catch {
      setLocalState(localState)
    } finally {
      setBusy(false)
    }
  }

  async function setBrightness(pct) {
    setBusy(true)
    try { await onCall(entity.entity_id, 'turn_on', { brightness_pct: pct }) }
    finally { setBusy(false) }
  }

  async function lockToggle() {
    if (busy) return
    if (!window.confirm(`${localState === 'locked' ? 'Unlock' : 'Lock'} ${friendlyName(entity)}?`)) return
    setBusy(true)
    const svc = localState === 'locked' ? 'unlock' : 'lock'
    setLocalState(svc === 'lock' ? 'locked' : 'unlocked')
    try { await onCall(entity.entity_id, svc, {}) }
    catch { setLocalState(entity.state) }
    finally { setBusy(false) }
  }

  async function coverAction(svc) {
    setBusy(true)
    try { await onCall(entity.entity_id, svc, {}) }
    finally { setBusy(false) }
  }

  const isOn = localState === 'on'

  return (
    <div className={`card p-3 flex flex-col gap-2 relative ${busy ? 'opacity-70' : ''}`}>
      {/* Favourite star */}
      <button
        onClick={() => onToggleFav(entity.entity_id)}
        className="absolute top-2 right-2 text-sm opacity-50 hover:opacity-100"
        title={isFav ? 'Remove from favourites' : 'Add to favourites'}
      >
        {isFav ? '★' : '☆'}
      </button>

      <p className="text-xs text-charcoal-400 dark:text-charcoal-500 uppercase tracking-wide pr-5">{domain}</p>
      <p className="font-medium text-sm leading-tight pr-5">{friendlyName(entity)}</p>

      {/* Light */}
      {domain === 'light' && (
        <>
          <button onClick={toggle} className={`text-left text-sm font-semibold ${stateColor(localState)}`}>
            {localState}
          </button>
          {isOn && attrs.brightness != null && (
            <input
              type="range" min={1} max={100}
              defaultValue={Math.round((attrs.brightness / 255) * 100)}
              onMouseUp={e => setBrightness(Number(e.target.value))}
              onTouchEnd={e => setBrightness(Number(e.target.value))}
              className="w-full accent-orange-500"
            />
          )}
        </>
      )}

      {/* Switch / binary_sensor */}
      {(domain === 'switch' || domain === 'input_boolean') && (
        <button onClick={toggle} className={`text-left text-sm font-semibold ${stateColor(localState)}`}>
          {localState}
        </button>
      )}

      {/* Binary sensor — read only */}
      {domain === 'binary_sensor' && (
        <p className={`text-sm font-semibold ${localState === 'on' ? 'text-green-500' : 'text-charcoal-400 dark:text-charcoal-500'}`}>
          {attrs.device_class ? (localState === 'on' ? 'detected' : 'clear') : localState}
        </p>
      )}

      {/* Sensor — read only */}
      {domain === 'sensor' && (
        <p className="text-sm font-semibold">
          {localState}
          {attrs.unit_of_measurement ? ` ${attrs.unit_of_measurement}` : ''}
        </p>
      )}

      {/* Climate */}
      {domain === 'climate' && (
        <div className="text-sm space-y-1">
          <p className="font-semibold">{localState}</p>
          {attrs.current_temperature != null && (
            <p className="text-charcoal-500 dark:text-charcoal-400">
              Current: {attrs.current_temperature}{attrs.temperature_unit || '°'}
            </p>
          )}
          {attrs.temperature != null && (
            <p>Target: {attrs.temperature}{attrs.temperature_unit || '°'}</p>
          )}
        </div>
      )}

      {/* Cover */}
      {domain === 'cover' && (
        <div className="flex gap-1">
          <button onClick={() => coverAction('open_cover')}  className="btn-ghost text-xs flex-1">Open</button>
          <button onClick={() => coverAction('stop_cover')}  className="btn-ghost text-xs flex-1">Stop</button>
          <button onClick={() => coverAction('close_cover')} className="btn-ghost text-xs flex-1">Close</button>
        </div>
      )}

      {/* Lock */}
      {domain === 'lock' && (
        <button onClick={lockToggle} className={`text-left text-sm font-semibold ${localState === 'locked' ? 'text-green-500' : 'text-red-500'}`}>
          {localState}
        </button>
      )}

      {/* Generic fallback */}
      {!['light','switch','input_boolean','binary_sensor','sensor','climate','cover','lock'].includes(domain) && (
        <p className={`text-sm font-semibold ${stateColor(localState)}`}>{localState}</p>
      )}
    </div>
  )
}

// ── Scenes panel ──────────────────────────────────────────────────────────────

function ScenesPanel({ scenes, onActivate }) {
  if (!scenes.length) return null
  return (
    <div>
      <h3 className="text-sm font-semibold text-charcoal-500 dark:text-charcoal-400 mb-2 uppercase tracking-wide">Scenes</h3>
      <div className="flex flex-wrap gap-2">
        {scenes.map(s => (
          <button
            key={s.entity_id}
            onClick={() => onActivate(s.entity_id)}
            className="btn-ghost text-sm"
          >
            {friendlyName(s)}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── HA Automations panel ──────────────────────────────────────────────────────

function AutomationsPanel({ automations, onTrigger }) {
  if (!automations.length) return null
  return (
    <div>
      <h3 className="text-sm font-semibold text-charcoal-500 dark:text-charcoal-400 mb-2 uppercase tracking-wide">Automations</h3>
      <div className="space-y-1">
        {automations.map(a => (
          <div key={a.entity_id} className="flex items-center justify-between gap-2 p-2 rounded-lg bg-charcoal-50 dark:bg-charcoal-800">
            <span className="text-sm">{friendlyName(a)}</span>
            <button onClick={() => onTrigger(a.entity_id)} className="btn-ghost text-xs shrink-0">▶ Run</button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Home() {
  const [entities, setEntities]     = useState([])
  const [scenes, setScenes]         = useState([])
  const [haAutomations, setHaAutomations] = useState([])
  const [favourites, setFavourites] = useState([])
  const [tab, setTab]               = useState('all')
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [toast, setToast]           = useState(null)
  const pollRef = useRef(null)

  function showToast(msg, ok = true) {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3000)
  }

  const loadAll = useCallback(async () => {
    try {
      const [ents, sc, autos, favs] = await Promise.all([
        homeApi.entities(),
        homeApi.scenes(),
        homeApi.automations(),
        homeApi.getFavourites(),
      ])
      setEntities(ents || [])
      setScenes(sc || [])
      setHaAutomations(autos || [])
      setFavourites(favs || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAll()
    pollRef.current = setInterval(loadAll, 30000)
    return () => clearInterval(pollRef.current)
  }, [loadAll])

  async function handleCall(entity_id, service, data) {
    await homeApi.callService(entity_id, { service, data })
    setTimeout(loadAll, 800)
  }

  async function handleActivateScene(entity_id) {
    try {
      await homeApi.activateScene(entity_id)
      showToast('Scene activated')
    } catch (e) {
      showToast(e.message, false)
    }
  }

  async function handleTriggerAutomation(entity_id) {
    try {
      await homeApi.triggerAutomation(entity_id)
      showToast('Automation triggered')
    } catch (e) {
      showToast(e.message, false)
    }
  }

  async function toggleFav(entity_id) {
    const next = favourites.includes(entity_id)
      ? favourites.filter(id => id !== entity_id)
      : [...favourites, entity_id]
    setFavourites(next)
    try { await homeApi.saveFavourites(next) }
    catch (e) { showToast(e.message, false) }
  }

  const filtered = tab === 'all'
    ? entities.filter(e => !['scene','automation'].includes(entityDomain(e.entity_id)))
    : entities.filter(e => entityDomain(e.entity_id) === tab)

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto p-4">
        <p className="text-charcoal-400 dark:text-charcoal-500">Loading devices…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto p-4 space-y-3">
        <h1 className="text-2xl font-bold">Smart Home</h1>
        <div className="card p-4">
          <p className="text-red-500 text-sm">{error}</p>
          <p className="text-charcoal-400 dark:text-charcoal-500 text-sm mt-2">
            Configure your Home Assistant URL and token in <strong>Admin → Smart Home</strong>.
          </p>
        </div>
      </div>
    )
  }

  if (!entities.length) {
    return (
      <div className="max-w-2xl mx-auto p-4 space-y-3">
        <h1 className="text-2xl font-bold">Smart Home</h1>
        <div className="card p-4 text-center text-charcoal-400 dark:text-charcoal-500">
          <p className="text-3xl mb-2">💡</p>
          <p>No devices found. Connect Home Assistant in <strong>Admin → Smart Home</strong>.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto p-4 space-y-4">
      <span className="flex items-center gap-2"><h1 className="text-2xl font-bold">Smart Home</h1><HelpButton section="home" /></span>

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-sm text-white shadow-lg
          ${toast.ok ? 'bg-green-600' : 'bg-red-600'}`}>
          {toast.msg}
        </div>
      )}

      {/* Domain tabs */}
      <div className="flex gap-1 overflow-x-auto pb-1">
        {DOMAIN_TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors
              ${tab === t.id
                ? 'bg-orange-500 text-white'
                : 'bg-charcoal-100 dark:bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-200 dark:hover:bg-charcoal-700'
              }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Entity grid */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {filtered.map(e => (
            <EntityTile
              key={e.entity_id}
              entity={e}
              isFav={favourites.includes(e.entity_id)}
              onToggleFav={toggleFav}
              onCall={handleCall}
            />
          ))}
        </div>
      ) : (
        <p className="text-charcoal-400 dark:text-charcoal-500 text-sm">No devices in this category.</p>
      )}

      {/* Scenes */}
      <ScenesPanel scenes={scenes} onActivate={handleActivateScene} />

      {/* HA Automations */}
      <AutomationsPanel automations={haAutomations} onTrigger={handleTriggerAutomation} />
    </div>
  )
}
