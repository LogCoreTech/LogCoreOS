import { useEffect, useState } from 'react'
import { auth as authApi } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { getShortcutsForUser, ALL_MODULES, QUICK_CREATE_ACTIONS } from '../../lib/constants'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

export default function Shortcuts() {
  const { user, updateUserField } = useAuth()

  function cleanShortcuts(ws, rawUser) {
    return getShortcutsForUser(rawUser, ws).filter(id => {
      const mod = ALL_MODULES.find(m => m.id === id)
      return mod && !(rawUser?.disabledModules || []).includes(id) && (!mod.workspace || mod.workspace === ws)
    })
  }

  const [personalShortcutIds, setPersonalShortcutIds] = useState(() => cleanShortcuts('personal', user))
  const [businessShortcutIds, setBusinessShortcutIds] = useState(() => cleanShortcuts('business', user))
  const [personalDragIdx, setPersonalDragIdx] = useState(null)
  const [businessDragIdx, setBusinessDragIdx] = useState(null)
  const [saved, setSaved] = useState(false)

  // Item #3, 2026-09-04 UX Polish Batch — command palette quick-create actions.
  const [paletteEnabled, setPaletteEnabled] = useState(user?.commandPaletteEnabled !== false)
  const [paletteActions, setPaletteActions] = useState(user?.commandPaletteActions || [])
  const [paletteSaved, setPaletteSaved] = useState(false)
  // Never a static list — a module the user has disabled (or that becomes
  // disabled later) drops out of both the picker and any already-saved
  // selection, so a stale action can never linger.
  const availableQuickActions = QUICK_CREATE_ACTIONS.filter(
    a => !(user?.disabledModules || []).includes(a.module)
  )

  useEffect(() => {
    setPaletteEnabled(user?.commandPaletteEnabled !== false)
    setPaletteActions((user?.commandPaletteActions || []).filter(
      id => !(user?.disabledModules || []).includes(id)
    ))
  }, [user?.commandPaletteEnabled, user?.commandPaletteActions, user?.disabledModules])

  function toggleQuickAction(moduleId) {
    setPaletteActions(ids => ids.includes(moduleId) ? ids.filter(id => id !== moduleId) : [...ids, moduleId])
  }

  async function savePaletteSettings() {
    try {
      await authApi.updateMe({ command_palette_enabled: paletteEnabled, command_palette_actions: paletteActions })
      updateUserField('commandPaletteEnabled', paletteEnabled)
      updateUserField('commandPaletteActions', paletteActions)
      setPaletteSaved(true)
      setTimeout(() => setPaletteSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save command palette settings:', e)
    }
  }

  // Keyed on user?.shortcuts specifically, not the whole user object, so this
  // doesn't re-run on every unrelated profile field update.
  useEffect(() => {
    setPersonalShortcutIds(cleanShortcuts('personal', user))
    setBusinessShortcutIds(cleanShortcuts('business', user))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.shortcuts])

  function toggleShortcut(ws, id) {
    const [ids, setIds] = ws === 'personal'
      ? [personalShortcutIds, setPersonalShortcutIds]
      : [businessShortcutIds, setBusinessShortcutIds]
    if (ids.includes(id)) {
      setIds(ids.filter(s => s !== id))
    } else if (ids.length < 4) {
      setIds([...ids, id])
    }
  }

  function onShortcutDragStart(ws, i) {
    if (ws === 'personal') setPersonalDragIdx(i)
    else setBusinessDragIdx(i)
  }
  function onShortcutDragOver(e, ws, i) {
    e.preventDefault()
    const [ids, setIds, dragIdx, setDragIdx] = ws === 'personal'
      ? [personalShortcutIds, setPersonalShortcutIds, personalDragIdx, setPersonalDragIdx]
      : [businessShortcutIds, setBusinessShortcutIds, businessDragIdx, setBusinessDragIdx]
    if (dragIdx === null || dragIdx === i) return
    const next = [...ids]
    const [m] = next.splice(dragIdx, 1)
    next.splice(i, 0, m)
    setIds(next)
    setDragIdx(i)
  }
  function onShortcutDragEnd(ws) {
    if (ws === 'personal') setPersonalDragIdx(null)
    else setBusinessDragIdx(null)
  }

  async function saveShortcutsHandler() {
    const newShortcuts = {
      ...(user?.shortcuts || {}),
      personal: personalShortcutIds.slice(0, 4),
      ...(user?.workspaces?.includes('business') && { business: businessShortcutIds.slice(0, 4) }),
    }
    try {
      await authApi.updateMe({ shortcuts: newShortcuts })
      updateUserField('shortcuts', newShortcuts)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save shortcuts:', e)
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Shortcuts" backTo="/settings" backLabel="Settings" />

      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Shortcuts</h2>
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Pin up to 4 modules per workspace — shown in the mobile bottom bar and the desktop sidebar&apos;s Pinned section. Drag to reorder.
        </p>

        {[
          { ws: 'personal', label: 'Personal', ids: personalShortcutIds, dragIdx: personalDragIdx },
          ...(user?.workspaces?.includes('business') ? [{ ws: 'business', label: 'Business', ids: businessShortcutIds, dragIdx: businessDragIdx }] : []),
        ].map(({ ws, label, ids, dragIdx }) => (
          <div key={ws} className="mb-5 last:mb-0">
            <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 uppercase tracking-wide mb-2">{label}</p>

            <ul className="space-y-2 mb-3">
              {ids.map((id, i) => {
                const mod = ALL_MODULES.find(m => m.id === id)
                if (!mod || user?.disabledModules?.includes(id) || (mod.workspace && mod.workspace !== ws)) return null
                return (
                  <li
                    key={id}
                    draggable
                    onDragStart={() => onShortcutDragStart(ws, i)}
                    onDragOver={e => onShortcutDragOver(e, ws, i)}
                    onDragEnd={() => onShortcutDragEnd(ws)}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                      dragIdx === i
                        ? 'border-orange-500 bg-orange-500/10'
                        : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                    }`}
                  >
                    <span className="text-base leading-none">{mod.icon}</span>
                    <span className="flex-1 text-sm">{mod.label}</span>
                    <button
                      onClick={() => toggleShortcut(ws, id)}
                      aria-label="Remove shortcut"
                      className="text-charcoal-400 hover:text-red-500 text-xs"
                    >✕</button>
                    <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
                  </li>
                )
              })}
            </ul>

            {ids.length < 4 && (
              <div className="mb-2">
                <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mb-2">
                  Add ({4 - ids.length} slot{4 - ids.length !== 1 ? 's' : ''} left):
                </p>
                <div className="flex flex-wrap gap-2">
                  {ALL_MODULES.filter(m =>
                    m.nav !== false &&
                    m.to &&
                    !ids.includes(m.id) &&
                    !user?.disabledModules?.includes(m.id) &&
                    (!m.workspace || m.workspace === ws)
                  ).map(mod => (
                    <button
                      key={mod.id}
                      onClick={() => toggleShortcut(ws, mod.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-charcoal-300 dark:border-charcoal-600 text-xs text-charcoal-500 dark:text-charcoal-400 hover:border-orange-500 hover:text-orange-500 transition-colors"
                    >
                      <span>{mod.icon}</span>
                      {mod.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {user?.workspaces?.includes('business') && ws === 'personal' && (
              <div className="border-t border-charcoal-100 dark:border-charcoal-700 mt-4" />
            )}
          </div>
        ))}

        <button onClick={saveShortcutsHandler} className="btn-primary w-full mt-2">
          Save Shortcuts
        </button>
      </div>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-semibold">Command Palette</h2>
          {paletteSaved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
          Press Ctrl/Cmd+K (or tap the search icon) to search — and, when enabled below, jump
          straight to creating something new.
        </p>

        <label className="flex items-center gap-2 text-sm cursor-pointer mb-4">
          <input
            type="checkbox"
            checked={paletteEnabled}
            onChange={e => setPaletteEnabled(e.target.checked)}
          />
          Show quick-create actions in search
        </label>

        {paletteEnabled && (
          <div className="mb-2">
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500 mb-2">
              Choose which actions appear:
            </p>
            <div className="flex flex-wrap gap-2">
              {availableQuickActions.map(action => (
                <button
                  key={action.module}
                  type="button"
                  onClick={() => toggleQuickAction(action.module)}
                  className={`px-3 py-1.5 rounded-lg border text-xs transition-colors ${
                    paletteActions.includes(action.module)
                      ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                      : 'border-dashed border-charcoal-300 dark:border-charcoal-600 text-charcoal-500 dark:text-charcoal-400 hover:border-orange-500 hover:text-orange-500'
                  }`}
                >
                  {action.label}
                </button>
              ))}
              {availableQuickActions.length === 0 && (
                <p className="text-xs text-charcoal-400">No modules with a quick-create action are enabled for you.</p>
              )}
            </div>
          </div>
        )}

        <button onClick={savePaletteSettings} className="btn-primary w-full mt-4">
          Save Command Palette Settings
        </button>
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
