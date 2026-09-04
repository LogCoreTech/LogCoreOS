import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// Shared toast/snackbar system (item #26 of the 2026-09-04 UX Polish Batch).
// Success toasts auto-dismiss after ~4s; errors persist until the user
// manually dismisses them. Multiple toasts stack (all visible at once, not
// replace-newest). Portals to document.body and sits above the mobile bottom
// nav bar (Layout.jsx's z-40/z-50 fixed bars, plus env(safe-area-inset-bottom))
// — see docs/MEMORY.md's backdrop-filter/portal precedent for why a portal is
// the safe default for anything meant to float above all app chrome.

const ToastCtx = createContext({ show: () => {}, success: () => {}, error: () => {} })

const AUTO_DISMISS_MS = 4000

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback(id => {
    setToasts(ts => ts.filter(t => t.id !== id))
  }, [])

  const show = useCallback(
    (message, { type = 'success' } = {}) => {
      const id = ++idRef.current
      setToasts(ts => [...ts, { id, message, type }])
      if (type !== 'error') {
        setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
      }
      return id
    },
    [dismiss]
  )

  const success = useCallback(message => show(message, { type: 'success' }), [show])
  const error = useCallback(message => show(message, { type: 'error' }), [show])

  return (
    <ToastCtx.Provider value={{ show, success, error, dismiss }}>
      {children}
      {createPortal(
        <div
          className="fixed inset-x-0 bottom-20 md:bottom-6 md:inset-x-auto md:right-6 z-[60] flex flex-col-reverse items-center md:items-end gap-2 px-4 md:px-0 pointer-events-none"
          style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
        >
          {toasts.map(t => (
            <div
              key={t.id}
              role={t.type === 'error' ? 'alert' : 'status'}
              aria-live={t.type === 'error' ? 'assertive' : 'polite'}
              className={`pointer-events-auto w-full md:w-auto max-w-sm flex items-start gap-2 rounded-lg shadow-lg px-4 py-3 text-sm text-white ${
                t.type === 'error' ? 'bg-red-600' : 'bg-charcoal-800 dark:bg-charcoal-700'
              }`}
            >
              <span className="flex-1">{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
                className="shrink-0 min-w-[24px] min-h-[24px] leading-none opacity-70 hover:opacity-100"
              >
                ✕
              </button>
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
