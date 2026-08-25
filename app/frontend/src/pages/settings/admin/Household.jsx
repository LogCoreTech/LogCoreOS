import { useEffect, useState } from 'react'
import { priorities as prioritiesApi } from '../../../lib/api'
import { home as homeApi } from '../../../module_packages/home/frontend/api'
import { useAuth } from '../../../lib/auth'
import { isPackageModule } from '../../../lib/moduleRegistry'
import PriorityList from '../../../components/settings/PriorityList'
import PoolBankConnections from '../../../components/settings/PoolBankConnections'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const POOL_DEFAULT_HOUSEHOLD = ['Cleaning', 'Maintenance', 'Shopping', 'Cooking', 'Yard Work']

function SmartHomeSection() {
  const [haUrl, setHaUrl]     = useState('')
  const [token, setToken]     = useState('')
  const [msg, setMsg]         = useState(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving]   = useState(false)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 5000)
  }

  async function testConn() {
    setTesting(true)
    setMsg(null)
    try {
      const res = await homeApi.status()
      flash(res.ok, res.ok ? `Connected to ${res.url}` : (res.error || 'Connection failed'))
    } catch (e) {
      flash(false, e.message || 'Connection failed')
    } finally {
      setTesting(false)
    }
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      await homeApi.saveConfig({ url: haUrl.trim(), token: token.trim() })
      flash(true, 'Config saved')
    } catch (e) {
      flash(false, e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-5 space-y-3">
      <div>
        <h2 className="font-semibold">Smart Home</h2>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
          Connect a Home Assistant instance. Members can control devices, scenes, and automations
          from the Smart Home page.
        </p>
      </div>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Home Assistant URL</label>
          <input
            type="url"
            value={haUrl}
            onChange={e => setHaUrl(e.target.value)}
            placeholder="http://homeassistant.local:8123"
            className="input"
            autoComplete="off"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Long-Lived Access Token</label>
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="HA long-lived access token"
            className="input"
            autoComplete="new-password"
          />
          <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-1">
            Generate in HA → Profile → Long-Lived Access Tokens
          </p>
        </div>

        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={testConn}
            disabled={testing}
            className="btn-ghost text-sm flex-1 disabled:opacity-50"
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
          <button type="submit" disabled={saving} className="btn-primary text-sm flex-1 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save Config'}
          </button>
        </div>
      </form>
    </div>
  )
}

function SmartHomeNotInstalled() {
  return (
    <div className="card p-5 space-y-1">
      <h2 className="font-semibold">Smart Home</h2>
      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        Smart Home isn&apos;t installed — install it from Admin → Mod Store to connect Home Assistant.
      </p>
    </div>
  )
}

export default function Household() {
  const { user, activeModuleIds } = useAuth()
  // Home's own admin config form lives on this page (not a dedicated Home
  // admin page — see docs/MEMORY.md 2026-08-24), so it needs the same
  // installed+active stacked gate ModuleRoute applies to Home's own /home
  // route, just for a section instead of a whole page.
  const homeInstalled = !user?.disabledModules?.includes('home')
    && (!isPackageModule('home') || activeModuleIds.includes('home'))
  const [household, setHousehold] = useState([])
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)
  const [msg, setMsg]             = useState(null)
  const [newVal, setNewVal]       = useState('')
  const [dragState, setDragState] = useState(null)

  useEffect(() => {
    prioritiesApi.getPool()
      .then(d => setHousehold(d.household?.length ? d.household : [...POOL_DEFAULT_HOUSEHOLD]))
      .catch(() => setHousehold([...POOL_DEFAULT_HOUSEHOLD]))
      .finally(() => setLoading(false))
  }, [])

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 3000)
  }

  async function save() {
    setSaving(true)
    setMsg(null)
    try {
      await prioritiesApi.setPool({ household })
      flash(true, 'Saved')
    } catch (e) {
      flash(false, e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  function onDragStart(pool, idx) { setDragState({ pool, idx }) }
  function onDragOver(e, pool, idx, setter) {
    e.preventDefault()
    if (!dragState || dragState.idx === idx) return
    const next = [...pool]
    const [m] = next.splice(dragState.idx, 1)
    next.splice(idx, 0, m)
    setter(next)
    setDragState({ pool: dragState.pool, idx })
  }
  function onDragEnd() { setDragState(null) }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Household" backTo="/settings/admin" backLabel="Admin Settings" />

      <div className="card p-5 space-y-4">
        <div>
          <h2 className="font-semibold">Pool Priorities</h2>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
            Category order used to score and rank tasks in the Household shared pool. Drag to
            reorder. Applies to all personal-workspace members.
          </p>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map(i => <div key={i} className="h-8 bg-charcoal-100 dark:bg-charcoal-800 rounded animate-pulse" />)}
          </div>
        ) : (
          <PriorityList label="Household" pool={household} setter={setHousehold} newVal={newVal} setNewVal={setNewVal} dragState={dragState} onDragStart={onDragStart} onDragOver={onDragOver} onDragEnd={onDragEnd} />
        )}

        {msg && <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</p>}

        <button onClick={save} disabled={saving || loading} className="btn-primary text-sm disabled:opacity-50">
          {saving ? 'Saving…' : 'Save Pool Priorities'}
        </button>
      </div>

      {homeInstalled ? <SmartHomeSection /> : <SmartHomeNotInstalled />}

      <PoolBankConnections pool="household" accountLabel="joint family" />

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
