import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import { applyAccentColor, applyDarkMode, applyBackground, getSystemDarkPreference } from './lib/theme.js'

// Apply stored theme before React renders to prevent FOUC
;(function initTheme() {
  let accentColor = null, darkMode = 'system', background = null
  try {
    const cached = JSON.parse(localStorage.getItem('lc_user'))
    if (cached) {
      accentColor = cached.accentColor || null
      darkMode    = cached.darkMode    || 'system'
      background  = cached.background  || null
    }
  } catch {}
  applyAccentColor(accentColor)
  applyDarkMode(darkMode, getSystemDarkPreference())
  applyBackground(background)
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
