import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// The app's own confirmation dialog and "done" message, in place of the
// browser's window.confirm() and alert() (T-137).
//
//   const { confirm, notify } = useDialogs()
//   const ok = await confirm({
//     title: 'Delete this interview?',
//     message: '…',
//     confirmLabel: 'Delete',
//     danger: true,
//     // Optional: runs while the dialog shows "Deleting…"; a thrown error is
//     // shown in the dialog, which stays open so the user can retry or cancel.
//     onConfirm: async () => api(…),
//   })
//   if (ok) notify('Interview deleted')

const DialogContext = createContext(null)

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
const NOTICE_MS = 3500

export function DialogProvider({ children }) {
  const [request, setRequest] = useState(null)
  const [notice, setNotice] = useState(null)

  const confirm = useCallback((options) => new Promise((resolve) => setRequest({ ...options, resolve })), [])
  const notify = useCallback((text) => setNotice({ text, at: Date.now() }), [])

  useEffect(() => {
    if (!notice) return undefined
    const t = setTimeout(() => setNotice(null), NOTICE_MS)
    return () => clearTimeout(t)
  }, [notice])

  function close(result) {
    request?.resolve(result)
    setRequest(null)
  }

  return (
    <DialogContext.Provider value={{ confirm, notify }}>
      {children}
      {request && <ConfirmDialog {...request} onClose={close} />}
      {createPortal(
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4"
        >
          {notice && (
            <p
              key={notice.at}
              className="rounded-full bg-tooltip px-5 py-2.5 text-sm font-semibold text-white shadow-lg"
            >
              <span aria-hidden="true">✓ </span>
              {notice.text}
            </p>
          )}
        </div>,
        document.body,
      )}
    </DialogContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDialogs() {
  const value = useContext(DialogContext)
  if (!value) throw new Error('useDialogs needs a <DialogProvider> above it')
  return value
}

function ConfirmDialog({
  title,
  message,
  confirmLabel = 'OK',
  busyLabel,
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onClose,
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const box = useRef(null)
  const cancel = useRef(null)
  const titleId = useId()
  const messageId = useId()

  // Cancel has focus first; focus goes back where it was when the dialog closes.
  useEffect(() => {
    const before = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    cancel.current?.focus()
    return () => {
      document.body.style.overflow = overflow
      if (before && typeof before.focus === 'function') before.focus()
    }
  }, [])

  function dismiss() {
    if (!busy) onClose(false)
  }

  async function accept() {
    if (!onConfirm) return onClose(true)
    setError('')
    setBusy(true)
    try {
      await onConfirm()
      onClose(true)
    } catch (err) {
      setError(err.message || 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  // Esc cancels; Tab and Shift+Tab stay inside the dialog.
  function onKeyDown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      dismiss()
      return
    }
    if (e.key !== 'Tab') return
    const items = [...box.current.querySelectorAll(FOCUSABLE)]
    if (!items.length) return
    const first = items[0]
    const last = items[items.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) dismiss()
      }}
    >
      <div
        ref={box}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        aria-busy={busy}
        onKeyDown={onKeyDown}
        className="card w-full max-w-md p-6"
      >
        <h2 id={titleId} className="text-lg font-bold text-ink">
          {title}
        </h2>
        <p id={messageId} className="mt-2 text-sm text-slate-600">
          {message}
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm font-medium text-red-700">
            {error}
          </p>
        )}
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button ref={cancel} type="button" className="btn-secondary" onClick={dismiss} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={accept}
            disabled={busy}
            className={
              danger
                ? 'inline-flex items-center justify-center gap-2 rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:cursor-not-allowed disabled:opacity-60'
                : 'btn-primary py-2 text-sm'
            }
          >
            {busy && (
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
              />
            )}
            {busy ? (busyLabel ?? `${confirmLabel}…`) : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
