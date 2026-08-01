import * as React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentQuoteModal } from '@/components/itinerary/AgentQuoteModal'

/**
 * The quote form moved into a modal in v10.56.0 and shipped without tests.
 * These pin the accessibility contract from the v10.48.0 audit — the parts
 * that fail silently rather than visibly, which is why they need a test
 * rather than a look.
 */

function Fixture({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      <button type="button">opener</button>
      <AgentQuoteModal open={open} onClose={onClose} titleId="quote-title">
        <form>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" />
          <label htmlFor="notes">Notes</label>
          <textarea id="notes" name="notes" />
          <button type="submit">Send request</button>
        </form>
      </AgentQuoteModal>
    </>
  )
}

afterEach(() => {
  document.body.style.overflow = ''
})

describe('AgentQuoteModal', () => {
  it('renders nothing while closed', () => {
    render(<Fixture open={false} onClose={vi.fn()} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('is a labelled modal dialog', () => {
    render(<Fixture open onClose={vi.fn()} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'quote-title')
    expect(screen.getByText('Request your quotation')).toHaveAttribute('id', 'quote-title')
  })

  it('focuses the first form field, not the close button', () => {
    // The close button precedes the fields in DOM order, so a naive
    // "focus first focusable" lands the user on dismiss — the one control
    // they did not open the dialog to press.
    render(<Fixture open onClose={vi.fn()} />)
    expect(screen.getByLabelText('Email')).toHaveFocus()
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    render(<Fixture open onClose={onClose} />)

    await userEvent.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes when the backdrop is clicked but not the panel', async () => {
    const onClose = vi.fn()
    render(<Fixture open onClose={onClose} />)

    await userEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()

    // The backdrop is the dialog's parent; clicking it must dismiss.
    await userEvent.click(screen.getByRole('dialog').parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('traps Tab inside the dialog', async () => {
    render(<Fixture open onClose={vi.fn()} />)

    const submit = screen.getByRole('button', { name: 'Send request' })
    const close = screen.getByRole('button', { name: 'Close' })

    submit.focus()
    await userEvent.tab()
    expect(close).toHaveFocus()

    await userEvent.tab({ shift: true })
    expect(submit).toHaveFocus()
  })

  it('locks background scrolling while open and restores it on close', () => {
    const { rerender } = render(<Fixture open onClose={vi.fn()} />)
    expect(document.body.style.overflow).toBe('hidden')

    rerender(<Fixture open={false} onClose={vi.fn()} />)
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('restores focus to the element that opened it', () => {
    const { rerender } = render(<Fixture open={false} onClose={vi.fn()} />)
    const opener = screen.getByRole('button', { name: 'opener' })
    opener.focus()

    rerender(<Fixture open onClose={vi.fn()} />)
    expect(opener).not.toHaveFocus()

    rerender(<Fixture open={false} onClose={vi.fn()} />)
    expect(opener).toHaveFocus()
  })

  it('keeps the focus-restore target across parent re-renders', () => {
    // Callers pass an inline arrow for onClose. If the effect depended on it
    // directly it would re-run on every parent render and re-capture the
    // restore target from whatever is focused *then* — a field inside the
    // dialog — silently losing the opener. Hence the ref indirection.
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()

    const { rerender } = render(
      <AgentQuoteModal open onClose={() => {}} titleId="t">
        <input aria-label="Email" />
      </AgentQuoteModal>,
    )

    rerender(
      <AgentQuoteModal open onClose={() => {}} titleId="t">
        <input aria-label="Email" />
      </AgentQuoteModal>,
    )

    rerender(
      <AgentQuoteModal open={false} onClose={() => {}} titleId="t">
        <input aria-label="Email" />
      </AgentQuoteModal>,
    )

    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})
