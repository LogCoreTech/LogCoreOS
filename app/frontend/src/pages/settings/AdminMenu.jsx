import MenuRow from '../../components/settings/MenuRow'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

export default function AdminMenu() {
  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Admin Settings" backTo="/settings" backLabel="Settings" />

      <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
        <MenuRow icon="👥" label="Users & Roles" subtitle="Accounts, access, and feature roles" to="/settings/admin/users" />
        <MenuRow icon="🗂️" label="Contact Fields" subtitle="Custom fields, scoped to person or company" to="/settings/admin/contact-fields" />
        <MenuRow icon="🤖" label="AI" subtitle="Provider, usage & limits, web search" to="/settings/admin/ai" />
        <MenuRow icon="⚙️" label="General" subtitle="Registration, workspaces, session length, updates" to="/settings/admin/general" />
        <MenuRow icon="🏢" label="Team" subtitle="Business pool priorities & bank connections" to="/settings/admin/team" />
        <MenuRow icon="🏠" label="Household" subtitle="Household priorities, bank connections" to="/settings/admin/household" />
        <MenuRow icon="🌐" label="Hosting" subtitle="Domain, managed hosting, n8n, Home Assistant" to="/settings/admin/hosting" />
        <MenuRow icon="🧩" label="Mod Store" subtitle="Install first-party modules" to="/settings/admin/mod-store" />
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
