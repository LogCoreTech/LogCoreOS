import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { WorkspaceProvider } from './lib/workspace'
import { MODULE_PACKAGES, isPackageModule } from './lib/moduleRegistry'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Goals from './module_packages/tasks/frontend/Goals'
import Chat from './pages/Chat'
import Brain from './pages/Brain'
import Settings from './pages/Settings'
import SettingsAppearance from './pages/settings/Appearance'
import SettingsNotifications from './pages/settings/Notifications'
import SettingsShortcuts from './pages/settings/Shortcuts'
import SettingsAccount from './pages/settings/Account'
import AdminMenu from './pages/settings/AdminMenu'
import AdminUsers from './pages/settings/admin/Users'
import AdminNewUser from './pages/settings/admin/NewUser'
import AdminUserDetail from './pages/settings/admin/UserDetail'
import AdminUserDeletionReview from './pages/settings/admin/UserDeletionReview'
import AdminRoleDefinitions from './pages/settings/admin/RoleDefinitions'
import AdminContactFields from './pages/settings/admin/ContactFields'
import AdminAi from './pages/settings/admin/Ai'
import AdminGeneral from './pages/settings/admin/General'
import AdminTeam from './pages/settings/admin/Team'
import AdminHousehold from './pages/settings/admin/Household'
import AdminHosting from './pages/settings/admin/Hosting'
import AdminModStore from './pages/settings/admin/ModStore'
import Notes from './pages/Notes'
import Login from './pages/Login'
import Setup from './pages/Setup'
import Profile from './pages/Profile'
import Assets from './pages/Assets'
import Finance from './pages/Finance'
import Contacts from './pages/Contacts'
import Help from './pages/Help'

function Protected({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AdminOnly({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/" replace />
  return children
}

function ModuleRoute({ moduleId, children }) {
  const { user, activeModuleIds } = useAuth()
  if (user?.disabledModules?.includes(moduleId)) return <Navigate to="/" replace />
  // A converted module's route also needs to be genuinely live in the
  // CURRENT backend process, not just "installed" (the marker file, which
  // disabledModules already reflects) — between an admin clicking Install
  // and clicking Restart Now, the marker says active but the router isn't
  // registered yet and would 404. Core modules skip this check entirely
  // (they're never in activeModuleIds, which only ever lists module_packages
  // ids — they're always live by definition).
  if (isPackageModule(moduleId) && !activeModuleIds.includes(moduleId)) {
    return <Navigate to="/" replace />
  }
  return children
}

function PageSkeleton() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <ErrorBoundary>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/setup" element={<Protected><Setup /></Protected>} />
              <Route element={<Protected><Layout /></Protected>}>
                <Route path="/"         element={<Dashboard />} />
                <Route path="/goals"     element={<ModuleRoute moduleId="tasks"><Goals /></ModuleRoute>} />
                <Route path="/notes"     element={<ModuleRoute moduleId="notes"><Notes /></ModuleRoute>} />
                <Route path="/chat"      element={<ModuleRoute moduleId="chat"><Chat /></ModuleRoute>} />
                <Route path="/assets"      element={<ModuleRoute moduleId="assets"><Assets /></ModuleRoute>} />
                <Route path="/finance"     element={<ModuleRoute moduleId="finance"><Finance /></ModuleRoute>} />
                <Route path="/contacts"    element={<ModuleRoute moduleId="contacts"><Contacts /></ModuleRoute>} />
                {MODULE_PACKAGES.map(pkg => {
                  const Page = lazy(pkg.loadPage)
                  return (
                    <Route
                      key={pkg.id}
                      path={pkg.to}
                      element={
                        <ModuleRoute moduleId={pkg.id}>
                          <Suspense fallback={<PageSkeleton />}><Page /></Suspense>
                        </ModuleRoute>
                      }
                    />
                  )
                })}
                <Route path="/brain"     element={<Brain />} />
                <Route path="/profile"   element={<Profile />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/settings/appearance" element={<SettingsAppearance />} />
                <Route path="/settings/notifications" element={<SettingsNotifications />} />
                <Route path="/settings/shortcuts" element={<SettingsShortcuts />} />
                <Route path="/settings/account" element={<SettingsAccount />} />
                <Route path="/settings/admin" element={<AdminOnly><AdminMenu /></AdminOnly>} />
                <Route path="/settings/admin/users" element={<AdminOnly><AdminUsers /></AdminOnly>} />
                <Route path="/settings/admin/users/new" element={<AdminOnly><AdminNewUser /></AdminOnly>} />
                <Route path="/settings/admin/users/roles" element={<AdminOnly><AdminRoleDefinitions /></AdminOnly>} />
                <Route path="/settings/admin/users/:userId" element={<AdminOnly><AdminUserDetail /></AdminOnly>} />
                <Route path="/settings/admin/users/:userId/delete" element={<AdminOnly><AdminUserDeletionReview /></AdminOnly>} />
                <Route path="/settings/admin/contact-fields" element={<AdminOnly><AdminContactFields /></AdminOnly>} />
                <Route path="/settings/admin/ai" element={<AdminOnly><AdminAi /></AdminOnly>} />
                <Route path="/settings/admin/general" element={<AdminOnly><AdminGeneral /></AdminOnly>} />
                <Route path="/settings/admin/team" element={<AdminOnly><AdminTeam /></AdminOnly>} />
                <Route path="/settings/admin/household" element={<AdminOnly><AdminHousehold /></AdminOnly>} />
                <Route path="/settings/admin/hosting" element={<AdminOnly><AdminHosting /></AdminOnly>} />
                <Route path="/settings/admin/mod-store" element={<AdminOnly><AdminModStore /></AdminOnly>} />
                <Route path="/help"     element={<Help />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ErrorBoundary>
      </WorkspaceProvider>
    </AuthProvider>
  )
}
