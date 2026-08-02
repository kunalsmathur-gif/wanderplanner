import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FloatingAnyaButton } from '@/components/common/FloatingAnyaButton'
import { useAppStore } from '@/store/appStore'
import { useChatStore } from '@/store/chatStore'

vi.mock('@/components/voice/ListeningOrb', () => ({
  ListeningOrb: () => <div data-testid="orb" />,
}))

describe('FloatingAnyaButton', () => {
  beforeEach(() => {
    useAppStore.setState({ wizardOpen: false } as never)
    useChatStore.setState({ isOpen: false } as never)
  })

  // The orb is ~98px of permanently-floating chrome. On a phone it ate scarce
  // vertical real estate and sat on top of whatever scrolled beneath it —
  // it was covering the "Get Quotation" CTA and winning the tap.
  it('is hidden on mobile and shown from lg up', () => {
    const { container } = render(<FloatingAnyaButton />)
    const wrapper = container.firstElementChild

    expect(wrapper).toHaveClass('hidden', 'lg:block')
  })

  it('no longer offsets itself above a mobile tab bar', () => {
    // `bottom-24 lg:bottom-6` existed only to clear the mobile tab bar. Now
    // that it never renders on mobile, the single desktop offset is correct.
    const { container } = render(<FloatingAnyaButton />)
    const wrapper = container.firstElementChild

    expect(wrapper).toHaveClass('bottom-6')
    expect(wrapper).not.toHaveClass('bottom-24')
  })

  it('opens the persistent chat, not the wizard', () => {
    // ⚠️ This is the only trigger for ChatPanel on desktop. "Edit Trip" reaches
    // Anya too, but through openWizard() — a different surface that replaces
    // the dashboard and fires the 'back' feedback prompt.
    render(<FloatingAnyaButton />)

    return userEvent.click(screen.getByRole('button', { name: /Open Anya/i })).then(() => {
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
