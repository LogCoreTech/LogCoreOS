import { useEffect, useState } from 'react'
import { admin as adminApi } from '../../../lib/api'
import MenuRow from '../../../components/settings/MenuRow'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const ROLE_COLORS = {
  admin:  'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  member: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  guest:  'bg-charcoal-100 text-charcoal-600 dark:bg-charcoal-800 dark:text-charcoal-400',
}

function initials(name) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

export default function Users() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminApi.listUsers()
      .then(d => setUsers(d.users || d))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Users & Roles" backTo="/settings/admin" backLabel="Admin Settings" />

      <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
        <MenuRow icon="➕" label="Add User" subtitle="Create a new account" to="/settings/admin/users/new" />
        <MenuRow icon="🎭" label="Role Definitions" subtitle="Custom feature roles & module access" to="/settings/admin/users/roles" />
      </div>

      <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
        {loading ? (
          <p className="text-sm text-charcoal-400 p-4">Loading…</p>
        ) : users.length === 0 ? (
          <p className="text-sm text-charcoal-400 p-4">No users yet.</p>
        ) : (
          users.map(u => (
            <MenuRow
              key={u.id}
              icon={
                <span className="w-7 h-7 rounded-full bg-orange-500 text-white flex items-center justify-center text-xs font-semibold">
                  {initials(u.name)}
                </span>
              }
              label={u.name}
              subtitle={u.email}
              to={`/settings/admin/users/${u.id}`}
              trailing={
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${ROLE_COLORS[u.role] || ROLE_COLORS.member}`}>
                  {u.role}
                </span>
              }
            />
          ))
        )}
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
