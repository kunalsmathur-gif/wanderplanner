import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UserMenu } from '@/components/common/UserMenu'
import { useAuthStore } from '@/store/authStore'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('next/link', () => ({
  default: React.forwardRef<HTMLAnchorElement, React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }>(
    ({ href, children, ...props }, ref) => (
      <a ref={ref} href={href} {...props}>
        {children}
      </a>
    )
  ),
}))

const initialState = useAuthStore.getState()

describe('UserMenu', () => {
  beforeEach(() => {
    push.mockReset()
    useAuthStore.setState({
      ...initialState,
      status: 'authenticated',
      user: {
        id: 'user-1',
        email: 'ada@example.com',
        display_name: 'Ada',
        is_admin: false,
        auth_provider: 'password',
      },
    })
  })

  afterEach(() => {
    useAuthStore.setState(initialState)
  })

  it('moves focus into the menu and supports arrow-key navigation', async () => {
    const user = userEvent.setup()
    render(<UserMenu />)

    const trigger = screen.getByRole('button', { name: /Signed in as Ada/i })
    await user.click(trigger)

    const accountItem = screen.getByRole('menuitem', { name: /Account settings/i })
    const logoutItem = screen.getByRole('menuitem', { name: /Log out/i })

    expect(accountItem).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(logoutItem).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(accountItem).toHaveFocus()

    await user.keyboard('{ArrowUp}')
    expect(logoutItem).toHaveFocus()
  })

  it('closes on Escape and restores focus to the trigger, including after outside clicks', async () => {
    const user = userEvent.setup()
    render(<UserMenu />)

    const trigger = screen.getByRole('button', { name: /Signed in as Ada/i })

    await user.click(trigger)
    expect(screen.getByRole('menuitem', { name: /Account settings/i })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    await user.click(trigger)
    expect(screen.getByRole('menuitem', { name: /Account settings/i })).toHaveFocus()

    await user.pointer([{ target: document.body, keys: '[MouseLeft]' }])
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
})
