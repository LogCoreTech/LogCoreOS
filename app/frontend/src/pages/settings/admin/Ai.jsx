import { useEffect, useState } from 'react'
import { admin as adminApi, aiUsage as aiUsageApi } from '../../../lib/api'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const QUICK_GUIDES = [
  {
    label: 'Ollama (local)',
    provider: 'openai',
    base_url: 'http://localhost:11434/v1',
    api_key: 'ollama',
    model: 'llama3.2',
  },
  {
    label: 'Groq',
    provider: 'openai',
    base_url: '',
    api_key: '<your groq key>',
    model: 'llama-3.3-70b-versatile',
  },
  {
    label: 'Gemini',
    provider: 'openai',
    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    api_key: '<your gemini key>',
    model: 'gemini-2.0-flash',
  },
  {
    label: 'OpenAI',
    provider: 'openai',
    base_url: '',
    api_key: '<your openai key>',
    model: 'gpt-4o',
  },
  {
    label: 'Anthropic',
    provider: 'anthropic',
    base_url: '',
    api_key: '<your anthropic key>',
    model: 'claude-sonnet-4-6',
  },
]

function AiProviderSection() {
  const [form, setForm] = useState({ ai_provider: 'anthropic', ai_api_key: '', ai_base_url: '', ai_model: '' })
  const [keySet, setKeySet]         = useState(false)
  const [saving, setSaving]         = useState(false)
  const [saveMsg, setSaveMsg]       = useState(null)
  const [guidesOpen, setGuidesOpen] = useState(false)

  useEffect(() => {
    adminApi.getAiSettings().then(s => {
      setForm(f => ({
        ...f,
        ai_provider: s.ai_provider || 'anthropic',
        ai_base_url: s.ai_base_url || '',
        ai_model: s.ai_model || '',
      }))
      setKeySet(s.ai_api_key_set || false)
    }).catch(() => {})
  }, [])

  function applyGuide(g) {
    setForm(f => ({
      ...f,
      ai_provider: g.provider,
      ai_base_url: g.base_url,
      ai_model: g.model,
      ai_api_key: g.api_key.startsWith('<') ? '' : g.api_key,
    }))
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setSaveMsg(null)
    try {
      const updated = await adminApi.updateAiSettings(form)
      setKeySet(updated.ai_api_key_set || false)
      setForm(f => ({ ...f, ai_api_key: '' }))
      setSaveMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setSaveMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">AI Provider</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Model must support tool / function calling. Changes take effect immediately.
      </p>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Provider</label>
          <select
            value={form.ai_provider}
            onChange={e => setForm(f => ({ ...f, ai_provider: e.target.value }))}
            className="input"
          >
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI / Compatible</option>
          </select>
        </div>

        {form.ai_provider === 'openai' && (
          <div>
            <label className="block text-sm font-medium mb-1">Base URL</label>
            <input
              type="text"
              value={form.ai_base_url}
              onChange={e => setForm(f => ({ ...f, ai_base_url: e.target.value }))}
              placeholder="http://localhost:11434/v1"
              className="input"
            />
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5">
              Leave blank for OpenAI default. Required for Ollama, Groq, Gemini, etc.
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1">Model</label>
          <input
            type="text"
            value={form.ai_model}
            onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
            placeholder={form.ai_provider === 'anthropic' ? 'claude-sonnet-4-6' : 'gpt-4o'}
            className="input"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">API Key</label>
          <input
            type="password"
            value={form.ai_api_key}
            onChange={e => setForm(f => ({ ...f, ai_api_key: e.target.value }))}
            placeholder={keySet ? '••••••••  (leave blank to keep current)' : 'Paste your API key'}
            className="input"
            autoComplete="new-password"
          />
        </div>

        {saveMsg && (
          <p className={`text-sm ${saveMsg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {saveMsg.text}
          </p>
        )}

        <button type="submit" disabled={saving} className="btn-primary w-full">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>

      <div className="mt-4 border-t border-charcoal-100 dark:border-charcoal-800 pt-4">
        <button
          onClick={() => setGuidesOpen(o => !o)}
          className="flex items-center gap-1 text-sm text-charcoal-500 dark:text-charcoal-400 hover:text-orange-500 transition-colors"
        >
          <span>{guidesOpen ? '▾' : '▸'}</span>
          Quick setup guides
        </button>

        {guidesOpen && (
          <div className="mt-3 space-y-2">
            {QUICK_GUIDES.map(g => (
              <div
                key={g.label}
                className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">{g.label}</span>
                  <button
                    type="button"
                    onClick={() => applyGuide(g)}
                    className="text-xs text-orange-500 hover:text-orange-600 font-medium"
                  >
                    Apply
                  </button>
                </div>
                <div className="text-xs text-charcoal-500 dark:text-charcoal-400 space-y-0.5 font-mono">
                  <div>provider: {g.provider}</div>
                  {g.base_url && <div>base_url: {g.base_url}</div>}
                  <div>model: {g.model}</div>
                  <div>api_key: {g.api_key}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function WebSearchSection() {
  const [keySet, setKeySet]   = useState(false)
  const [key, setKey]         = useState('')
  const [saving, setSaving]   = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    adminApi.getSearchSettings().then(s => setKeySet(s.tavily_key_set || false)).catch(() => {})
  }, [])

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      const res = await adminApi.updateSearchSettings({ tavily_api_key: key })
      setKeySet(res.tavily_key_set || false)
      setKey('')
      setMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Web Search</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Enables web search in AI Research mode. Get a free Tavily API key at{' '}
        <span className="font-mono">tavily.com</span> (1 000 searches/month free).
      </p>

      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2 h-2 rounded-full ${keySet ? 'bg-green-500' : 'bg-charcoal-300'}`} />
        <span className="text-sm">{keySet ? 'API key configured' : 'No API key set'}</span>
      </div>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Tavily API Key</label>
          <input
            type="password"
            value={key}
            onChange={e => setKey(e.target.value)}
            placeholder={keySet ? '••••••••  (leave blank to keep current)' : 'tvly-…'}
            className="input"
            autoComplete="new-password"
          />
        </div>
        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}
        <button type="submit" disabled={saving || !key} className="btn-primary w-full disabled:opacity-50">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}

const STATUS_STYLE = {
  ok: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  warn: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  over: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  off: 'bg-charcoal-100 text-charcoal-500 dark:bg-charcoal-700 dark:text-charcoal-400',
}
const PERIODS = ['daily', 'weekly', 'monthly']
const MODES = ['off', 'soft', 'hard']

function fmtNum(n) {
  return (n || 0).toLocaleString()
}
function currentMonth() {
  return new Date().toISOString().slice(0, 7)
}

function StatCard({ label, messages, inputTokens, outputTokens, dimmed }) {
  return (
    <div className={`card p-4 ${dimmed ? 'opacity-50' : ''}`}>
      <p className="text-xs uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 mb-2">{label}</p>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-lg font-semibold">{fmtNum(messages)}</p>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">messages</p>
        </div>
        <div>
          <p className="text-lg font-semibold">{fmtNum(inputTokens)}</p>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">input tok</p>
        </div>
        <div>
          <p className="text-lg font-semibold">{fmtNum(outputTokens)}</p>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">output tok</p>
        </div>
      </div>
    </div>
  )
}

function AiUsageSection() {
  const [month, setMonth] = useState(currentMonth())
  const [overview, setOverview] = useState(null)
  const [rows, setRows] = useState([])
  const [edits, setEdits] = useState({})
  const [defaults, setDefaults] = useState({ period: 'monthly', message_limit: '', token_limit: '', warn_pct: 80 })
  const [businessEnabled, setBusinessEnabled] = useState(true)
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 4000)
  }

  function loadUsage() {
    aiUsageApi.overview(month).then(setOverview).catch(() => {})
    aiUsageApi.users(month).then(rs => {
      const list = Array.isArray(rs) ? rs : []
      setRows(list)
      setEdits(prev => {
        const next = { ...prev }
        for (const r of list) {
          if (!next[r.user_id]) {
            next[r.user_id] = {
              period: r.period,
              mode: r.mode,
              message_limit: r.message_limit ?? '',
              token_limit: r.token_limit ?? '',
            }
          }
        }
        return next
      })
    }).catch(() => {})
  }

  useEffect(loadUsage, [month]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    aiUsageApi.getDefaults().then(d => setDefaults({
      period: d.period || 'monthly',
      message_limit: d.message_limit ?? '',
      token_limit: d.token_limit ?? '',
      warn_pct: d.warn_pct ?? 80,
    })).catch(() => {})
    adminApi.getSettings().then(s => {
      setBusinessEnabled((s.enabled_workspaces || ['personal', 'business']).includes('business'))
    }).catch(() => {})
  }, [])

  async function saveDefaults() {
    setBusy('defaults')
    try {
      await aiUsageApi.updateDefaults({
        period: defaults.period,
        message_limit: defaults.message_limit === '' ? null : Number(defaults.message_limit),
        token_limit: defaults.token_limit === '' ? null : Number(defaults.token_limit),
        warn_pct: Number(defaults.warn_pct) || 80,
      })
      flash(true, 'Defaults saved.')
      loadUsage()
    } catch (err) {
      flash(false, err.message || 'Save failed')
    } finally {
      setBusy(null)
    }
  }

  function updateEdit(userId, field, value) {
    setEdits(prev => ({ ...prev, [userId]: { ...prev[userId], [field]: value } }))
  }

  async function saveUserLimits(userId) {
    const e = edits[userId]
    if (!e) return
    setBusy(userId)
    try {
      await aiUsageApi.updateUserLimits(userId, {
        period: e.period,
        mode: e.mode,
        message_limit: e.message_limit === '' ? null : Number(e.message_limit),
        token_limit: e.token_limit === '' ? null : Number(e.token_limit),
      })
      flash(true, 'Limits saved.')
      loadUsage()
    } catch (err) {
      flash(false, err.message || 'Save failed')
    } finally {
      setBusy(null)
    }
  }

  const months = overview?.available_months?.length ? overview.available_months : [month]

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-semibold text-lg">AI Usage &amp; Limits</h2>
        <select className="input w-auto" value={month} onChange={e => setMonth(e.target.value)}>
          {months.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {msg && (
        <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</p>
      )}

      {overview && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <StatCard label={`Instance total — ${month}`} messages={overview.total.messages} inputTokens={overview.total.input_tokens} outputTokens={overview.total.output_tokens} />
          <StatCard label="Personal" messages={overview.personal.messages} inputTokens={overview.personal.input_tokens} outputTokens={overview.personal.output_tokens} />
          <StatCard label="Business" messages={overview.business.messages} inputTokens={overview.business.input_tokens} outputTokens={overview.business.output_tokens} dimmed={!businessEnabled} />
        </div>
      )}

      <div className="card p-5 space-y-3">
        <h3 className="font-semibold">Defaults</h3>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
          Applied to any user whose own mode is set to soft or hard but who has no limit of their own.
          A user's mode always defaults to <span className="font-medium">off</span> (unlimited) until set below.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div>
            <label className="block text-xs font-medium mb-1">Period</label>
            <select className="input" value={defaults.period} onChange={e => setDefaults(d => ({ ...d, period: e.target.value }))}>
              {PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Message limit</label>
            <input className="input" placeholder="unlimited" inputMode="numeric" value={defaults.message_limit} onChange={e => setDefaults(d => ({ ...d, message_limit: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Token limit</label>
            <input className="input" placeholder="unlimited" inputMode="numeric" value={defaults.token_limit} onChange={e => setDefaults(d => ({ ...d, token_limit: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Warn at %</label>
            <input className="input" inputMode="numeric" value={defaults.warn_pct} onChange={e => setDefaults(d => ({ ...d, warn_pct: e.target.value }))} />
          </div>
        </div>
        <button onClick={saveDefaults} disabled={busy === 'defaults'} className="btn-primary text-sm">
          {busy === 'defaults' ? 'Saving…' : 'Save defaults'}
        </button>
      </div>

      <div className="card p-5 space-y-3">
        <h3 className="font-semibold">Per-user</h3>
        <div className="space-y-3">
          {rows.map(r => {
            const e = edits[r.user_id] || {}
            return (
              <div key={r.user_id} className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium flex-1 min-w-0 truncate">{r.name}</span>
                  <span className={`badge shrink-0 ${STATUS_STYLE[r.status] || ''}`}>{r.status}</span>
                </div>
                <div className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  Personal: {fmtNum(r.personal.messages)} msgs · {fmtNum(r.personal.input_tokens + r.personal.output_tokens)} tok
                  {businessEnabled && (
                    <> — Business: {fmtNum(r.business.messages)} msgs · {fmtNum(r.business.input_tokens + r.business.output_tokens)} tok</>
                  )}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <select className="input" value={e.mode || 'off'} onChange={ev => updateEdit(r.user_id, 'mode', ev.target.value)}>
                    {MODES.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <select className="input" value={e.period || 'monthly'} onChange={ev => updateEdit(r.user_id, 'period', ev.target.value)}>
                    {PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                  <input className="input" placeholder="msg limit" inputMode="numeric" value={e.message_limit ?? ''} onChange={ev => updateEdit(r.user_id, 'message_limit', ev.target.value)} />
                  <input className="input" placeholder="token limit" inputMode="numeric" value={e.token_limit ?? ''} onChange={ev => updateEdit(r.user_id, 'token_limit', ev.target.value)} />
                </div>
                <button onClick={() => saveUserLimits(r.user_id)} disabled={busy === r.user_id} className="btn-ghost text-xs">
                  {busy === r.user_id ? 'Saving…' : 'Save'}
                </button>
              </div>
            )
          })}
          {rows.length === 0 && (
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400">Loading users…</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default function Ai() {
  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <SettingsPageHeader title="AI" backTo="/settings/admin" backLabel="Admin Settings" />
      <AiProviderSection />
      <WebSearchSection />
      <AiUsageSection />

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
