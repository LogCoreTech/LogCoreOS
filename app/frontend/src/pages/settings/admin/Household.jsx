import { useEffect, useState } from 'react'
import { priorities as prioritiesApi } from '../../../lib/api'
import PriorityList from '../../../components/settings/PriorityList'
import PoolBankConnections from '../../../components/settings/PoolBankConnections'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const POOL_DEFAULT_HOUSEHOLD = ['Cleaning', 'Maintenance', 'Shopping', 'Cooking', 'Yard Work']

export default function Household() {
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

      <PoolBankConnections pool="household" accountLabel="joint family" />

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
