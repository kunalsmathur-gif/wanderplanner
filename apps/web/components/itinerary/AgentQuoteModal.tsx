'use client'

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * The quotation form, moved off the itinerary page into a modal (v10.56.0).
 *
 * The card used to render an email field, a 100-word notes textarea and a word
 * counter inline — on a phone that pushed the actual CTA most of a screen down
 * and made a single "talk to an expert" offer look like a form to fill in. The
 * card now carries the pitch and one button; everything that needs typing
 * happens here, after the user has opted in.
 *
 * Accessibility follows the v10.48.0 audit: labelled dialog, focus moved in on
 * open and restored on close, Escape to dismiss, Tab trapped inside, and the
 * background locked from scrolling underneath.
 */
export function AgentQuoteModal({
  open,
  onClose,
  children,
  titleId,
}: {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  titleId: string
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)

  // Held in a ref so the effect below can depend on `open` alone. Callers pass
  // an inline arrow, so a direct `onClose` dependency re-runs the whole effect
  // on every render of the parent: the keydown listener is torn down and
  // re-added, the scroll lock is re-applied, and — the one that actually
  // matters — the focus-restore target is re-captured from whatever is
  // focused *now*, which by then is a field inside the dialog rather than the
  // element that opened it.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return

    restoreFocusRef.current = document.activeElement as HTMLElement | null

    // Prefer the first form field over the first focusable: the close button
    // precedes the fields in DOM order, so a plain FOCUSABLE query lands the
    // user on "dismiss" — the one control they did not open this to press.
    const panel = panelRef.current
    const target =
      panel?.querySelector<HTMLElement>('input, textarea, select') ??
      panel?.querySelector<HTMLElement>(FOCUSABLE)
    target?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return

      const items = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
      if (!items.length) return

      const firstItem = items[0]
      const lastItem = items[items.length - 1]
      if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault()
        lastItem.focus()
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault()
        firstItem.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      restoreFocusRef.current?.focus()
    }
  }, [open])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        // Bottom sheet on phones, centred dialog from `sm` up — a centred box
        // on a small screen puts the fields under the keyboard.
        className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-[var(--_border)] bg-[var(--_card)] p-5 shadow-xl sm:max-w-md sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3
            id={titleId}
            className="text-base font-bold text-[var(--_fg)] [font-family:var(--font-display)]"
          >
            Request your quotation
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[var(--_muted-fg)] transition-colors hover:bg-[var(--_muted)] hover:text-[var(--_fg)]"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {children}
      </div>
    </div>
  )
}
