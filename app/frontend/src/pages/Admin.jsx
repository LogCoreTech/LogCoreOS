import { useEffect, useState } from 'react'
import { admin as adminApi } from '../lib/api'

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

export default function Admin() {
  const [form, setForm] = useState({
    ai_provider: 'anthropic',
    ai_api_key: '',
    ai_base_url: '',
    ai_model: '',
  })
  const [keySet, setKeySet] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null) // { ok, text }
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
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Admin</h1>

      <div className="card p-5">
        <h2 className="font-semibold mb-1">AI Provider</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Model must support tool / function calling. Changes take effect immediately.
        </p>

        <form onSubmit={save} className="space-y-3">
          {/* Provider select */}
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

          {/* Base URL — only for openai */}
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

          {/* Model */}
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

          {/* API key */}
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

        {/* Quick setup guides */}
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
    </div>
  )
}
