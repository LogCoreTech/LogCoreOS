import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { admin as adminApi, features as featuresApi } from '../../../lib/api'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const BLANK_NEW_USER = { email: '', name: '', password: '', role: 'member', feature_role: 'guest', workspaces: ['personal'] }

export default function NewUser() {
  const navigate = useNavigate()
  const [roles, setRoles] = useState(['member', 'guest'])
  const [newUser, setNewUser] = useState(BLANK_NEW_USER)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    featuresApi.get().then(fd => setRoles(Object.keys(fd.roles || { member: {} }))).catch(() => {})
  }, [])

  async function submitCreate(e) {
    e.preventDefault()
    setCreating(true)
    setError('')
    try {
      const created = await adminApi.createUser({
        ...newUser,
        feature_role: newUser.feature_role || 'guest',
      })
      navigate(`/settings/admin/users/${created.id}`)
    } catch (err) {
      setError(err.message || 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Add User" backTo="/settings/admin/users" backLabel="Users & Roles" />

      <form onSubmit={submitCreate} className="card p-5 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">Full name</label>
            <input
              type="text"
              required
              value={newUser.name}
              onChange={e => setNewUser(u => ({ ...u, name: e.target.value }))}
              placeholder="Jane Smith"
              className="input text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Role</label>
            <select
              value={newUser.role}
              onChange={e => setNewUser(u => ({ ...u, role: e.target.value }))}
              className="input text-sm"
            >
              <option value="admin">admin</option>
              <option value="member">member</option>
              <option value="guest">guest</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">Feature Access Role</label>
          <select
            value={newUser.feature_role || 'guest'}
            onChange={e => setNewUser(u => ({ ...u, feature_role: e.target.value }))}
            className="input text-sm"
          >
            {roles.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <p className="text-xs text-charcoal-400 mt-1">Controls which app features this user can see.</p>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">Workspace Access</label>
          <div className="flex items-center gap-4">
            {['personal', 'business'].map(ws => (
              <label key={ws} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(newUser.workspaces || ['personal']).includes(ws)}
                  onChange={() => {
                    const cur = newUser.workspaces || ['personal']
                    const next = cur.includes(ws) ? cur.filter(w => w !== ws) : [...cur, ws]
                    if (next.length > 0) setNewUser(u => ({ ...u, workspaces: next }))
                  }}
                  className="accent-orange-500 w-4 h-4"
                />
                <span className="text-sm capitalize">{ws}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">Email</label>
          <input
            type="email"
            required
            value={newUser.email}
            onChange={e => setNewUser(u => ({ ...u, email: e.target.value }))}
            placeholder="jane@example.com"
            className="input text-sm"
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">Password</label>
          <input
            type="password"
            required
            minLength={8}
            value={newUser.password}
            onChange={e => setNewUser(u => ({ ...u, password: e.target.value }))}
            placeholder="Min 8 characters"
            className="input text-sm"
            autoComplete="new-password"
          />
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <button type="submit" disabled={creating} className="btn-primary w-full text-sm">
          {creating ? 'Creating…' : 'Create User'}
        </button>
      </form>
    </div>
  )
}
