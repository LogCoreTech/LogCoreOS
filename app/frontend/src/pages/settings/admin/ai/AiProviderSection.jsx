import { useEffect, useState } from 'react'
import { admin as adminApi } from '../../../../lib/api'
import ModelPicker from './ModelPicker'

// Azure OpenAI's API version isn't discoverable from any endpoint this app can
// call — it's a value Microsoft documents, not something a model/provider list
// exposes. Seeded with recent known-good strings; unverified against Microsoft's
// current docs, confirm before shipping. Always paired with "Other" below.
const AZURE_API_VERSIONS = ['2024-10-21', '2024-08-01-preview', '2024-06-01', '2024-02-15-preview']
const AZURE_OTHER = '__other__'

const EMPTY_FORM = {
  ai_provider: 'anthropic',
  ai_api_key: '',
  ai_base_url: '',
  ai_model: '',
  azure_endpoint: '',
  azure_deployment: '',
  azure_api_version: '',
  ai_allow_model_fetch: false,
}

// Old pre-overhaul saves used the generic "openai" id + a real base_url for
// anything OpenAI-compatible (Groq, Gemini, Ollama, ...) — the picker itself
// didn't exist yet, so there was no specific id to save. A non-empty base_url
// under "openai" is the tell that a record predates this overhaul: search the
// catalog for a provider whose known default_base_url matches it, and re-point
// the picker there. No match -> Custom, with the URL kept exactly as saved.
function reconcileProvider(providers, storedProvider, storedBaseUrl) {
  const byId = Object.fromEntries(providers.map(p => [p.id, p]))

  if (storedProvider === 'openai' && storedBaseUrl) {
    const match = providers.find(p => p.default_base_url && p.default_base_url === storedBaseUrl)
    return match
      ? { providerId: match.id, baseUrl: storedBaseUrl }
      : { providerId: 'custom', baseUrl: storedBaseUrl }
  }

  if (byId[storedProvider]) {
    return { providerId: storedProvider, baseUrl: storedBaseUrl }
  }

  return { providerId: 'custom', baseUrl: storedBaseUrl }
}

export default function AiProviderSection() {
  const [providers, setProviders] = useState([])
  const [form, setForm]           = useState(EMPTY_FORM)
  const [keySet, setKeySet]       = useState(false)
  const [loaded, setLoaded]       = useState(false)
  const [saving, setSaving]       = useState(false)
  const [saveMsg, setSaveMsg]     = useState(null)
  const [azureVersionOther, setAzureVersionOther] = useState(false)

  useEffect(() => {
    Promise.all([adminApi.getAiProviderCatalog(), adminApi.getAiSettings()])
      .then(([catalog, s]) => {
        const list = catalog.providers || []
        setProviders(list)
        const { providerId, baseUrl } = reconcileProvider(list, s.ai_provider || 'anthropic', s.ai_base_url || '')
        setForm({
          ai_provider: providerId,
          ai_api_key: '',
          ai_base_url: baseUrl,
          ai_model: s.ai_model || '',
          azure_endpoint: s.azure_endpoint || '',
          azure_deployment: s.azure_deployment || '',
          azure_api_version: s.azure_api_version || '',
          ai_allow_model_fetch: s.ai_allow_model_fetch || false,
        })
        setKeySet(s.ai_api_key_set || false)
        setAzureVersionOther(
          Boolean(s.azure_api_version) && !AZURE_API_VERSIONS.includes(s.azure_api_version)
        )
      })
      .catch(() => {})
      .finally(() => setLoaded(true))
  }, [])

  const spec = providers.find(p => p.id === form.ai_provider)
  const isAzure = form.ai_provider === 'azure_openai'
  const showBaseUrl = !isAzure && spec && !spec.default_base_url
  const showApiKey = !spec || spec.needs_api_key !== false

  function selectProvider(providerId) {
    const nextSpec = providers.find(p => p.id === providerId)
    setForm(f => ({
      ...f,
      ai_provider: providerId,
      ai_model: '', // don't silently carry a model id from one provider to another
      ai_base_url: nextSpec && nextSpec.default_base_url ? nextSpec.default_base_url : '',
    }))
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setSaveMsg(null)
    try {
      const updated = await adminApi.updateAiSettings(form)
      setKeySet(updated.ai_api_key_set || false)
      setForm(f => ({ ...f, ai_api_key: '', ai_base_url: updated.ai_base_url || f.ai_base_url }))
      setSaveMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setSaveMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(null), 4000)
    }
  }

  if (!loaded) {
    return (
      <div className="card p-5">
        <h2 className="font-semibold mb-1">AI Provider</h2>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">Loading…</p>
      </div>
    )
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
            onChange={e => selectProvider(e.target.value)}
            className="input"
          >
            {providers.map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
          {spec && spec.docs_verified === false && (
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5">
              Endpoint not pre-filled for this provider — enter its base URL below.
            </p>
          )}
        </div>

        {isAzure && (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">Resource Endpoint</label>
              <input
                type="text"
                value={form.azure_endpoint}
                onChange={e => setForm(f => ({ ...f, azure_endpoint: e.target.value }))}
                placeholder="https://your-resource.openai.azure.com"
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Deployment Name</label>
              <input
                type="text"
                value={form.azure_deployment}
                onChange={e => setForm(f => ({ ...f, azure_deployment: e.target.value }))}
                placeholder="my-gpt4o-deployment"
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">API Version</label>
              <select
                value={azureVersionOther ? AZURE_OTHER : form.azure_api_version || ''}
                onChange={e => {
                  if (e.target.value === AZURE_OTHER) {
                    setAzureVersionOther(true)
                    setForm(f => ({ ...f, azure_api_version: '' }))
                  } else {
                    setAzureVersionOther(false)
                    setForm(f => ({ ...f, azure_api_version: e.target.value }))
                  }
                }}
                className="input"
              >
                <option value="" disabled>Select an API version…</option>
                {AZURE_API_VERSIONS.map(v => <option key={v} value={v}>{v}</option>)}
                <option value={AZURE_OTHER}>Other (type manually)</option>
              </select>
              {azureVersionOther && (
                <input
                  type="text"
                  value={form.azure_api_version}
                  onChange={e => setForm(f => ({ ...f, azure_api_version: e.target.value }))}
                  placeholder="2024-06-01"
                  className="input mt-2"
                />
              )}
            </div>
          </>
        )}

        {showBaseUrl && (
          <div>
            <label className="block text-sm font-medium mb-1">Base URL</label>
            <input
              type="text"
              value={form.ai_base_url}
              onChange={e => setForm(f => ({ ...f, ai_base_url: e.target.value }))}
              placeholder="https://your-endpoint/v1"
              className="input"
            />
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mt-0.5">
              Leave blank for OpenAI&apos;s default endpoint.
            </p>
          </div>
        )}

        {!isAzure && (
          <ModelPicker
            providerId={form.ai_provider}
            key={form.ai_provider /* remount on provider switch: a stale fetched list from
                                       the previous provider must never linger under a new one */}
            staticModels={spec ? spec.static_models : []}
            allowFetch={form.ai_allow_model_fetch}
            formSnapshot={form}
            value={form.ai_model}
            onChange={m => setForm(f => ({ ...f, ai_model: m }))}
          />
        )}

        {showApiKey && (
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
        )}

        <label className="flex items-center gap-2 text-xs text-charcoal-500 dark:text-charcoal-400 mt-2">
          <input
            type="checkbox"
            checked={form.ai_allow_model_fetch}
            onChange={e => setForm(f => ({ ...f, ai_allow_model_fetch: e.target.checked }))}
          />
          Allow pulling live model lists from providers (&quot;Load Models&quot;). Off by default — nothing
          fetches automatically, only on an explicit click, and never for Azure.
        </label>

        {saveMsg && (
          <p className={`text-sm ${saveMsg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {saveMsg.text}
          </p>
        )}

        <button type="submit" disabled={saving} className="btn-primary w-full">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}
