import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FloatingAnyaButton } from '@/components/common/FloatingAnyaButton'
import { useAppStore } from '@/store/appStore'
import { useChatStore } from '@/store/chatStore'

vi.mock('@/components/voice/ListeningOrb', () => ({
  ListeningOrb: ({ svgClassName }: { svgClassName?: string }) => (
    <div data-testid="orb" data-svg-class={svgClassName} />
  ),
}))

describe('FloatingAnyaButton', () => {
  beforeEach(() => {
    useAppStore.setState({ wizardOpen: false } as never)
    useChatStore.setState({ isOpen: false } as never)
  })

  // v10.58 pulled the orb off mobile because it was ~98px of permanently
  // floating chrome; v10.60 brings it back smaller instead, since removing it
  // left the entry point looking worse than the footprint it saved.
  it('renders at every breakpoint', () => {
    const { container } = render(<FloatingAnyaButton />)

    expect(container.firstElementChild).not.toHaveClass('hidden')
  })

  it('shrinks to a 44px touch target on mobile and the full 72px from lg up', () => {
    render(<FloatingAnyaButton />)

    expect(screen.getByTestId('orb')).toHaveAttribute(
      'data-svg-class',
      'h-11 w-11 lg:h-[72px] lg:w-[72px]'
    )
  })

  it('carries no text label, at any width', () => {
    // The label added height for no affordance and, being wider than the orb,
    // overlapped whatever sat beside it. The name survives in the tooltip and
    // the aria-label.
    render(<FloatingAnyaButton />)

    expect(screen.queryByText('Anya')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Ask Anya/i })).toBeInTheDocument()
  })

  it('names the job, not just the persona', () => {
    // ⚠️ "Chat with Anya" said nothing about how this differs from "Edit
    // Trip", which reaches the same assistant through the guided wizard. Both
    // are Anya and both change the trip, so the entry points are the only
    // place a user can tell them apart *before* committing to one.
    render(<FloatingAnyaButton />)

    expect(screen.getByRole('button', { name: /Ask Anya/i })).toBeInTheDocument()
    expect(screen.getByText(/Ask Anya/i)).toBeInTheDocument()
    expect(screen.queryByText(/Chat with Anya/i)).not.toBeInTheDocument()
  })

  it('sits above the frozen tab bar on mobile, and at the corner from lg up', () => {
    // Expressed as the bar's height plus the home-indicator inset rather than
    // a magic `bottom-24`, so it tracks the bar instead of drifting from it.
    const { container } = render(<FloatingAnyaButton />)
    const wrapper = container.firstElementChild

    expect(wrapper).toHaveClass('bottom-[calc(3.5rem+env(safe-area-inset-bottom))]')
    expect(wrapper).toHaveClass('lg:bottom-6')
  })

  it('opens the persistent chat, not the wizard', () => {
    // ⚠️ This is the only trigger for ChatPanel on desktop. "Edit Trip" reaches
    // Anya too, but through openWizard() — a different surface that replaces
    // the dashboard and fires the 'back' feedback prompt.
    render(<FloatingAnyaButton />)

    return userEvent.click(screen.getByRole('button', { name: /Ask Anya/i })).then(() => {
      expect(useChatStore.getState().isOpen).toBe(true)
      expect(useAppStore.getState().wizardOpen).toBe(false)
    })
  })

  it('gets out of the way while the wizard or chat is open', () => {
    useAppStore.setState({ wizardOpen: true } as never)
    const { container, rerender } = render(<FloatingAnyaButton />)
    expect(container).toBeEmptyDOMElement()

    useAppStore.setState({ wizardOpen: false } as never)
    useChatStore.setState({ isOpen: true } as never)
    rerender(<FloatingAnyaButton />)
    expect(container).toBeEmptyDOMElement()
  })
})
