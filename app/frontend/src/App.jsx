import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Tasks from './pages/Tasks'
import Chat from './pages/Chat'
import Brain from './pages/Brain'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Calendar from './pages/Calendar'
import Goals from './pages/Goals'
import Household from './pages/Household'
import Login from './pages/Login'
import Setup from './pages/Setup'

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
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/setup" element={<Protected><Setup /></Protected>} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route path="/"         element={<Dashboard />} />
              <Route path="/tasks"     element={<ModuleRoute moduleId="tasks"><Tasks /></ModuleRoute>} />
              <Route path="/calendar"  element={<ModuleRoute moduleId="calendar"><Calendar /></ModuleRoute>} />
              <Route path="/goals"     element={<ModuleRoute moduleId="goals"><Goals /></ModuleRoute>} />
              <Route path="/household" element={<ModuleRoute moduleId="household"><Household /></ModuleRoute>} />
              <Route path="/chat"      element={<ModuleRoute moduleId="chat"><Chat /></ModuleRoute>} />
              <Route path="/brain"     element={<ModuleRoute moduleId="brain"><Brain /></ModuleRoute>} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/admin"    element={<AdminOnly><Admin /></AdminOnly>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </AuthProvider>
  )
}
