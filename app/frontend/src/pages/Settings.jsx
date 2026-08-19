import { useAuth } from '../lib/auth'
import MenuRow from '../components/settings/MenuRow'

export default function Settings() {
  const { user } = useAuth()

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
        <MenuRow icon="👤" label="Profile" subtitle="Your details, priorities, and values" to="/profile" />
        <MenuRow icon="🎨" label="Appearance" subtitle="Dark mode, accent color, background, density" to="/settings/appearance" />
        <MenuRow icon="🔔" label="Notifications" subtitle="ntfy, push notifications, proactive suggestions" to="/settings/notifications" />
        <MenuRow icon="⭐" label="Shortcuts" subtitle="Pin modules to the mobile bottom bar and the desktop sidebar" to="/settings/shortcuts" />
        <MenuRow icon="🗂" label="Account" subtitle="Timezone, your Brain, export data" to="/settings/account" />
      </div>

      {user?.role === 'admin' && (
        <div className="card">
          <MenuRow icon="🛡" label="Admin Settings" subtitle="Users, AI, hosting, and instance-wide settings" to="/settings/admin" />
        </div>
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
