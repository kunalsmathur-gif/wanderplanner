import * as React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { AuthSwitch } from '@/components/common/AuthSwitch'

vi.mock('next/link', () => ({
  default: React.forwardRef<HTMLAnchorElement, React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }>(
    ({ href, children, ...props }, ref) => (
      <a ref={ref} href={href} {...props}>
        {children}
      </a>
    )
  ),
}))

function switcher() {
  return screen.getByRole('navigation', { name: /sign up or log in/i })
}

describe('AuthSwitch', () => {
  it('offers both routes so a returning user never has to hunt for log in', () => {
    render(<AuthSwitch active="signup" returnTo="/" />)

    const links = within(switcher()).getAllByRole('link')
    expect(links.map((a) => a.textContent)).toEqual(['Sign up', 'Log in'])
  })

  it('marks only the current route with aria-current', () => {
    const { rerender } = render(<AuthSwitch active="signup" returnTo="/" />)

    expect(within(switcher()).getByRole('link', { name: 'Sign up' })).toHaveAttribute('aria-current', 'page')
    expect(within(switcher()).getByRole('link', { name: 'Log in' })).not.toHaveAttribute('aria-current')

    rerender(<AuthSwitch active="login" returnTo="/" />)

    expect(within(switcher()).getByRole('link', { name: 'Log in' })).toHaveAttribute('aria-current', 'page')
    expect(within(switcher()).getByRole('link', { name: 'Sign up' })).not.toHaveAttribute('aria-current')
  })

  // The wizard, chat panel, /account and /admin all deep-link into auth with a
  // returnTo. Switching tabs must not drop it, or the user lands on the home
  // page after logging in instead of back where the gate stopped them.
  it('carries returnTo, url-encoded, into both routes', () => {
    render(<AuthSwitch active="signup" returnTo="/trips/goa?day=2" />)

    const encoded = encodeURIComponent('/trips/goa?day=2')
    expect(within(switcher()).getByRole('link', { name: 'Sign up' })).toHaveAttribute(
      'href',
      `/signup?returnTo=${encoded}`
    )
    expect(within(switcher()).getByRole('link', { name: 'Log in' })).toHaveAttribute(
      'href',
      `/login?returnTo=${encoded}`
    )
  })
})
