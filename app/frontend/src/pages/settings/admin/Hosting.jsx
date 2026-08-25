import { useEffect, useState } from 'react'
import { admin as adminApi, infisical as infisicalApi, assets as assetsApi } from '../../../lib/api'
import { home as homeApi } from '../../../module_packages/home_assistant/frontend/api'
import { automations as automationsApi } from '../../../module_packages/automations/frontend/api'
import { useAuth } from '../../../lib/auth'
import { isPackageModule } from '../../../lib/moduleRegistry'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

function HostingSection() {
  const [form, setForm]         = useState({ mode: 'local', domain_url: '', tunnel_token: '' })
  const [tokenSaved, setTokenSaved] = useState(false)
  const [saving, setSaving]     = useState(false)
  const [applying, setApplying] = useState(false)
  const [msg, setMsg]           = useState(null)

  useEffect(() => {
    adminApi.getHostingSettings().then(s => {
      let mode = 'local'
      if (s.proxy_type === 'cloudflare' || s.proxy_type === 'nginx') {
        mode = s.proxy_type
      } else if (s.cookie_secure || s.trust_proxy_headers) {
        mode = 'cloudflare'
      }
      setForm({ mode, domain_url: s.domain_url || '', tunnel_token: '' })
      setTokenSaved(s.tunnel_token_set || false)
    }).catch(() => {})
  }, [])

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    const isHttps = form.mode !== 'local'
    const payload = {
      proxy_type: form.mode === 'local' ? '' : form.mode,
      cookie_secure: isHttps,
      trust_proxy_headers: isHttps,
      domain_url: isHttps ? form.domain_url.trim() : '',
    }
    if (form.tunnel_token) payload.tunnel_token = form.tunnel_token
    try {
      const updated = await adminApi.updateHostingSettings(payload)
      setTokenSaved(updated.tunnel_token_set || false)
      setForm(f => ({ ...f, tunnel_token: '' }))
      setMsg({ ok: true, text: 'Saved.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  async function applyTunnel() {
    setApplying(true)
    setMsg(null)
    try {
      await adminApi.applyHostingSettings()
      setMsg({ ok: true, text: 'Tunnel restarted. Your domain should be live in a few seconds.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Restart failed. Check container logs.' })
    } finally {
      setApplying(false)
      setTimeout(() => setMsg(null), 8000)
    }
  }

  const isHttps = form.mode !== 'local'
  const needsDomain = isHttps && !form.domain_url.trim()

  const nginxConfig = (() => {
    if (!form.domain_url) return ''
    try {
      const { hostname } = new URL(form.domain_url)
      return `server {
    listen 443 ssl;
    server_name ${hostname};

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}`
    } catch { return '' }
  })()

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Hosting</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Configure how this app is accessed. Changes take effect immediately.
      </p>

      <form onSubmit={save} className="space-y-4">
        <div className="space-y-2">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="radio" name="mode" value="local" checked={form.mode === 'local'}
              onChange={() => setForm(f => ({ ...f, mode: 'local', domain_url: '', tunnel_token: '' }))}
              className="accent-orange-500" />
            <span className="text-sm">
              <span className="font-medium">Local only</span>
              <span className="text-charcoal-500 dark:text-charcoal-400"> — http://localhost:8000</span>
            </span>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="radio" name="mode" value="cloudflare" checked={form.mode === 'cloudflare'}
              onChange={() => setForm(f => ({ ...f, mode: 'cloudflare' }))}
              className="accent-orange-500" />
            <span className="text-sm font-medium">Cloudflare Tunnel</span>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="radio" name="mode" value="nginx" checked={form.mode === 'nginx'}
              onChange={() => setForm(f => ({ ...f, mode: 'nginx' }))}
              className="accent-orange-500" />
            <span className="text-sm font-medium">nginx / Caddy / Reverse Proxy</span>
          </label>
        </div>

        {isHttps && (
          <div>
            <label className="block text-sm font-medium mb-1">Domain URL</label>
            <input
              type="url"
              value={form.domain_url}
              onChange={e => setForm(f => ({ ...f, domain_url: e.target.value }))}
              placeholder="https://logcore.yourdomain.com"
              className="input"
              autoComplete="off"
              required
            />
            {form.mode === 'cloudflare' && (
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
                Set this as the public hostname in Cloudflare Zero Trust → Networks → Tunnels → your tunnel → Configure.
              </p>
            )}
            {form.mode === 'nginx' && (
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
                Your reverse proxy must forward to <span className="font-mono">http://localhost:8000</span>.
              </p>
            )}
          </div>
        )}

        {form.mode === 'cloudflare' && (
          <div>
            <label className="block text-sm font-medium mb-1">Tunnel Token</label>
            <input
              type="password"
              value={form.tunnel_token}
              onChange={e => setForm(f => ({ ...f, tunnel_token: e.target.value }))}
              placeholder={tokenSaved ? '••••••••••••• (saved — paste to replace)' : 'Paste token from Cloudflare dashboard'}
              className="input font-mono"
              autoComplete="new-password"
            />
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
              Find your token in Cloudflare Zero Trust → Networks → Tunnels → your tunnel → Configure.
            </p>
          </div>
        )}

        {form.mode === 'nginx' && nginxConfig && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium">nginx Config</label>
              <button type="button" onClick={() => navigator.clipboard.writeText(nginxConfig)}
                className="text-xs text-orange-500 hover:underline">Copy</button>
            </div>
            <pre className="bg-charcoal-900 text-charcoal-100 text-xs rounded p-3 overflow-x-auto whitespace-pre">{nginxConfig}</pre>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-1">
              Paste into your nginx config, then run <span className="font-mono">nginx -t && systemctl reload nginx</span>.
            </p>
          </div>
        )}

        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}

        <button type="submit" disabled={saving || needsDomain} className="btn-primary w-full disabled:opacity-50">
          {saving ? 'Saving…' : 'Save Hosting Settings'}
        </button>

        {form.mode === 'cloudflare' && tokenSaved && (
          <button
            type="button"
            onClick={applyTunnel}
            disabled={applying}
            className="btn-ghost w-full border border-orange-500 text-orange-500 hover:bg-orange-500 hover:text-white disabled:opacity-50"
          >
            {applying ? 'Restarting tunnel…' : 'Apply & Restart Tunnel'}
          </button>
        )}

        {isHttps && form.domain_url && !needsDomain && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 flex items-start gap-1">
            <span>✓</span>
            <span>
              App will be accessible at{' '}
              <a href={form.domain_url} target="_blank" rel="noopener noreferrer" className="text-orange-500 underline">
                {form.domain_url}
              </a>
              . Make sure your tunnel or proxy passes the <span className="font-mono">X-Forwarded-For</span> header.
            </span>
          </p>
        )}
      </form>
    </div>
  )
}

function InfisicalSection() {
  const [status, setStatus]   = useState(null)
  const [token, setToken]     = useState('')
  const [saving, setSaving]   = useState(false)
  const [clearing, setClearing] = useState(false)
  const [msg, setMsg]         = useState(null)

  useEffect(() => {
    infisicalApi.getStatus()
      .then(s => setStatus(s))
      .catch(() => setStatus({ configured: false }))
  }, [])

  // Hidden entirely when not configured — self-hosters never see this
  if (!status || !status.configured) return null

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 5000)
  }

  async function save(e) {
    e.preventDefault()
    if (!token.trim()) return
    setSaving(true)
    setMsg(null)
    try {
      const res = await infisicalApi.setToken(token.trim())
      setStatus(res)
      setToken('')
      flash(true, res.message || 'Token saved. New secrets will load on next restart.')
    } catch (err) {
      flash(false, err.message || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  async function clear() {
    if (!confirm('Clear the saved Infisical token? The app will revert to local .env on next restart.')) return
    setClearing(true)
    setMsg(null)
    try {
      await infisicalApi.clearToken()
      setStatus({ configured: false, source: null })
      flash(true, 'Token cleared.')
    } catch (err) {
      flash(false, err.message || 'Clear failed.')
    } finally {
      setClearing(false)
    }
  }

  const sourceLabel = status.source === 'env'
    ? 'environment variable (set at deploy time)'
    : 'admin panel'

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Managed Hosting</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Secrets are pulled from Infisical at startup. Rotate the token here — new secrets apply on next restart.
      </p>

      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2 h-2 rounded-full ${status.connected ? 'bg-green-500' : 'bg-red-400'}`} />
        <span className="text-sm">
          {status.connected ? 'Connected to Infisical' : 'Infisical unreachable (running from cache)'}
        </span>
      </div>

      <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mb-4">
        Token source: {sourceLabel}
        {status.last_fetched && (
          <span className="ml-2">· Last fetched: {new Date(status.last_fetched).toLocaleString()}</span>
        )}
      </p>

      <form onSubmit={save} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">Rotate Token</label>
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="Paste new Infisical token to rotate"
            className="input font-mono"
            autoComplete="new-password"
          />
        </div>
        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={saving || !token.trim()}
          className="btn-primary w-full disabled:opacity-50"
        >
          {saving ? 'Validating & saving…' : 'Save new token'}
        </button>
      </form>

      {status.source === 'file' && (
        <button
          onClick={clear}
          disabled={clearing}
          className="mt-3 w-full text-sm text-red-500 hover:text-red-600 disabled:opacity-50 text-center"
        >
          {clearing ? 'Clearing…' : 'Clear token (revert to self-hosted .env mode)'}
        </button>
      )}
    </div>
  )
}

function AutomationTokenRow() {
  const [token, setToken] = useState(null) // null = hidden
  const [busy, setBusy] = useState(false)

  async function reveal() {
    setBusy(true)
    try {
      const res = await assetsApi.automationToken()
      setToken(res.token)
    } catch { /* admin-only; ignore */ } finally {
      setBusy(false)
    }
  }

  async function rotate() {
    if (!confirm('Rotate the automation API token? Existing n8n workflows using it will stop working until updated.')) return
    setBusy(true)
    try {
      const res = await assetsApi.rotateAutomationToken()
      setToken(res.token)
    } catch { /* ignore */ } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 pt-3 border-t border-charcoal-100 dark:border-charcoal-800">
      <p className="text-sm font-medium mb-1">Automation API token</p>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-2">
        Lets n8n workflows read and write LogCore data (e.g. assets) via the
        <code className="mx-1">X-Automation-Token</code> header.
      </p>
      {token ? (
        <p className="text-xs font-mono break-all bg-charcoal-50 dark:bg-charcoal-800 rounded p-2 mb-2 select-all">{token}</p>
      ) : null}
      <div className="flex gap-2">
        <button type="button" onClick={reveal} disabled={busy} className="btn-ghost text-xs px-3 py-1.5 disabled:opacity-50">
          {token ? 'Refresh' : 'Reveal token'}
        </button>
        <button type="button" onClick={rotate} disabled={busy} className="text-xs px-3 py-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50">
          Rotate
        </button>
      </div>
    </div>
  )
}

function N8nSection() {
  const [url, setUrl]               = useState('http://n8n:5678')
  const [apiKey, setApiKey]         = useState('')
  const [forceOn, setForceOn]       = useState(false)
  const [testing, setTesting]       = useState(false)
  const [saving, setSaving]         = useState(false)
  const [syncing, setSyncing]       = useState(false)
  const [syncingWf, setSyncingWf]   = useState(false)
  const [msg, setMsg]               = useState(null)

  function flash(ok, text) {
    setMsg({ ok, text })
    setTimeout(() => setMsg(null), 5000)
  }

  async function testConn() {
    setTesting(true)
    setMsg(null)
    try {
      const res = await automationsApi.n8nStatus()
      flash(res.ok, res.ok ? `Connected to ${res.url}` : `Cannot reach ${res.url}${res.error ? ': ' + res.error : ''}`)
    } catch (err) {
      flash(false, err.message || 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  async function saveCfg(e) {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    try {
      await automationsApi.saveN8nConfig({ url: url.trim(), api_key: apiKey.trim(), force_on: forceOn })
      flash(true, 'n8n configuration saved.')
    } catch (err) {
      flash(false, err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function syncSecrets() {
    if (!confirm('Write Infisical secrets to n8n.env and restart n8n?')) return
    setSyncing(true)
    setMsg(null)
    try {
      const res = await automationsApi.syncSecrets()
      flash(true, res.message || 'Secrets synced.')
    } catch (err) {
      flash(false, err.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">n8n Automation</h2>
      <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
        Configure the bundled n8n instance or point to an external one.
      </p>

      <form onSubmit={saveCfg} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">n8n URL</label>
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="http://n8n:5678"
            className="input"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="n8n API key"
            className="input"
            autoComplete="new-password"
          />
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
        <label className="flex items-center gap-2 text-xs text-charcoal-500 dark:text-charcoal-400 mt-2">
          <input type="checkbox" checked={forceOn} onChange={e => setForceOn(e.target.checked)} />
          Keep the bundled n8n running even with no workflows (it otherwise auto-stops when idle,
          and stops entirely when an external instance is attached).
        </label>
      </form>

      <div className="mt-3 flex gap-2">
        <button
          onClick={syncSecrets}
          disabled={syncing}
          className="flex-1 text-sm text-charcoal-500 hover:text-orange-500 transition-colors disabled:opacity-50"
        >
          {syncing ? 'Syncing…' : '↺ Sync Infisical → n8n'}
        </button>
        <button
          onClick={async () => {
            setSyncingWf(true)
            setMsg(null)
            try {
              const res = await automationsApi.syncWorkflows()
              const { created = 0, updated = 0, deleted = 0, skipped = 0, errors = [] } = res
              const summary = `Workflows synced — ${created} created, ${updated} updated, ${deleted} deleted, ${skipped} unchanged`
              flash(errors.length === 0, errors.length ? `${summary}. Errors: ${errors.join('; ')}` : summary)
            } catch (err) {
              flash(false, err.message || 'Sync failed')
            } finally {
              setSyncingWf(false)
            }
          }}
          disabled={syncingWf}
          className="flex-1 text-sm text-charcoal-500 hover:text-orange-500 transition-colors disabled:opacity-50"
        >
          {syncingWf ? 'Syncing…' : '⚡ Sync Workflows Now'}
        </button>
      </div>

      <AutomationTokenRow />
    </div>
  )
}

function HomeAssistantSection() {
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
        <h2 className="font-semibold">Home Assistant</h2>
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
          Connect a Home Assistant instance. Members can control devices, scenes, and automations
          from the Home Assistant page.
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

function HomeAssistantNotInstalled() {
  return (
    <div className="card p-5 space-y-1">
      <h2 className="font-semibold">Home Assistant</h2>
      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        Home Assistant isn&apos;t installed — install it from Admin → Mod Store to connect it.
      </p>
    </div>
  )
}

function N8nNotInstalled() {
  return (
    <div className="card p-5 space-y-1">
      <h2 className="font-semibold">n8n Automation</h2>
      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        n8n Automation isn&apos;t installed — install it from Admin → Mod Store to connect it.
      </p>
    </div>
  )
}

export default function Hosting() {
  const { user, activeModuleIds } = useAuth()
  // Home Assistant's and n8n Automation's own admin config forms both live
  // here, not on a dedicated admin page each — see docs/MEMORY.md — so both
  // need the same installed+active stacked gate ModuleRoute applies to a
  // converted module's own route, just for a section instead of a whole page.
  const homeInstalled = !user?.disabledModules?.includes('home_assistant')
    && (!isPackageModule('home_assistant') || activeModuleIds.includes('home_assistant'))
  const automationsInstalled = !user?.disabledModules?.includes('automations')
    && (!isPackageModule('automations') || activeModuleIds.includes('automations'))

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Hosting" backTo="/settings/admin" backLabel="Admin Settings" />
      <HostingSection />
      <InfisicalSection />
      {automationsInstalled ? <N8nSection /> : <N8nNotInstalled />}
      {homeInstalled ? <HomeAssistantSection /> : <HomeAssistantNotInstalled />}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
