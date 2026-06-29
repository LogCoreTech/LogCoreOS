import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { WorkspaceProvider } from './lib/workspace'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Tasks from './pages/Tasks'
import Chat from './pages/Chat'
import Brain from './pages/Brain'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Calendar from './pages/Calendar'
import Household from './pages/Household'
import Team from './pages/Team'
import Notes from './pages/Notes'
import Journal from './pages/Journal'
import Login from './pages/Login'
import Setup from './pages/Setup'
import Profile from './pages/Profile'
import Automations from './pages/Automations'
import Home from './pages/Home'

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
  const { user } = useAuth()
  if (user?.disabledModules?.includes(moduleId)) return <Navigate to="/" replace />
  return children
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
                <Route path="/tasks"     element={<ModuleRoute moduleId="tasks"><Tasks /></ModuleRoute>} />
                <Route path="/calendar"  element={<ModuleRoute moduleId="calendar"><Calendar /></ModuleRoute>} />
                <Route path="/household" element={<ModuleRoute moduleId="household"><Household /></ModuleRoute>} />
                <Route path="/team"      element={<ModuleRoute moduleId="team"><Team /></ModuleRoute>} />
                <Route path="/notes"     element={<ModuleRoute moduleId="notes"><Notes /></ModuleRoute>} />
                <Route path="/journal"   element={<ModuleRoute moduleId="journal"><Journal /></ModuleRoute>} />
                <Route path="/chat"      element={<ModuleRoute moduleId="chat"><Chat /></ModuleRoute>} />
                <Route path="/automations" element={<ModuleRoute moduleId="automations"><Automations /></ModuleRoute>} />
                <Route path="/home"        element={<ModuleRoute moduleId="home"><Home /></ModuleRoute>} />
                <Route path="/brain"     element={<Brain />} />
                <Route path="/profile"   element={<Profile />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/admin"    element={<AdminOnly><Admin /></AdminOnly>} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ErrorBoundary>
      </WorkspaceProvider>
    </AuthProvider>
  )
}
