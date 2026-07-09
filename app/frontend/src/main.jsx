import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import { applyAccentColor, applyDarkMode, applyBackground, applyDensity, applyCornerStyle, getSystemDarkPreference } from './lib/theme.js'

// Surface any uncaught client error with its stack — the on-screen ErrorBoundary
// message is minified, so this makes crashes actually diagnosable from the console.
window.addEventListener('error', e => {
  console.error('[global error]', e.message, e.error?.stack || e.error || '')
})
window.addEventListener('unhandledrejection', e => {
  console.error('[unhandled rejection]', e.reason?.message || e.reason, e.reason?.stack || '')
})

// Apply stored theme before React renders to prevent FOUC
;(function initTheme() {
  const isAuthPage = window.location.pathname === '/login' || window.location.pathname === '/setup'
  let accentColor = null, darkMode = 'system', background = null, density = 'comfortable', cornerStyle = 'rounded'
  try {
    const cached = JSON.parse(localStorage.getItem('lc_user'))
    if (cached) {
      accentColor = cached.accentColor  || null
      darkMode    = cached.darkMode     || 'system'
      background  = cached.background   || null
      density     = cached.density      || 'comfortable'
      cornerStyle = cached.cornerStyle  || 'rounded'
    }
  } catch {}
  // Skip accent color on auth pages so the brand orange always matches the logo
  if (!isAuthPage) applyAccentColor(accentColor)
  applyDarkMode(darkMode, getSystemDarkPreference())
  if (!isAuthPage) applyBackground(background)
  applyDensity(density)
  applyCornerStyle(cornerStyle)
})()

// Keep dark mode in sync with OS when user has chosen "system"
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
  try {
    const mode = JSON.parse(localStorage.getItem('lc_user'))?.darkMode || 'system'
    if (mode === 'system') applyDarkMode('system', e.matches)
  } catch {
    applyDarkMode('system', e.matches)
  }
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
