import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import LoginPage from '@/app/login/page'
import SignupPage from '@/app/signup/page'

const push = vi.fn()
let searchParams = new URLSearchParams()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
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

vi.mock('@/lib/authApi', () => ({
  // Google SSO is hidden unless the backend confirms it is configured; keeping
  // it off here isolates these tests to the layout under test.
  fetchAuthConfig: vi.fn().mockResolvedValue({ google_sso_enabled: false }),
  authErrorMessage: (err: unknown) => String(err),
}))

function switcher() {
  return screen.getByRole('navigation', { name: /sign up or log in/i })
}

describe('auth pages', () => {
  beforeEach(() => {
    push.mockReset()
    searchParams = new URLSearchParams()
  })

  describe.each([
    { name: '/signup', Page: SignupPage, active: 'Sign up', sibling: 'Log in', heading: /create your free account/i },
    { name: '/login', Page: LoginPage, active: 'Log in', sibling: 'Sign up', heading: /welcome back/i },
  ])('$name', ({ Page, active, sibling, heading }) => {
    it('renders the switcher with the current route marked', () => {
      render(<Page />)

      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
      expect(within(switcher()).getByRole('link', { name: active })).toHaveAttribute('aria-current', 'page')
      expect(within(switcher()).getByRole('link', { name: sibling })).toBeInTheDocument()
    })

    // Prominence is the point of the change: the sibling route used to sit in a
    // muted line below the card, after the whole form. Assert it now precedes
    // the form in document order rather than trailing it.
    it('places the switcher ahead of the form', () => {
      const { container } = render(<Page />)

      const nav = switcher()
      const form = container.querySelector('form')!
      expect(nav.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    it('does not repeat the route link in a footer below the card', () => {
      render(<Page />)

      expect(screen.queryByText(/already have an account/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/don't have an account/i)).not.toBeInTheDocument()
      expect(within(switcher()).getAllByRole('link', { name: sibling })).toHaveLength(1)
    })
  })

  // Mirrors the real gates: LLMWizard and ChatPanel push /signup?returnTo=…,
  // /account and /admin push /login?returnTo=…. Flipping tabs must preserve it.
  describe.each([
    { from: '/signup', Page: SignupPage, returnTo: '/', sibling: 'Log in', target: '/login' },
    { from: '/signup', Page: SignupPage, returnTo: '/t/goa-5-days', sibling: 'Log in', target: '/login' },
    { from: '/login', Page: LoginPage, returnTo: '/account', sibling: 'Sign up', target: '/signup' },
    { from: '/login', Page: LoginPage, returnTo: '/admin', sibling: 'Sign up', target: '/signup' },
  ])('$from deep-linked with returnTo=$returnTo', ({ Page, returnTo, sibling, target }) => {
    it(`hands returnTo to ${target}`, () => {
      searchParams = new URLSearchParams({ returnTo })
      render(<Page />)

      expect(within(switcher()).getByRole('link', { name: sibling })).toHaveAttribute(
        'href',
        `${target}?returnTo=${encodeURIComponent(returnTo)}`
      )
    })
  })

  it('defaults returnTo to / when the gate did not supply one', () => {
    render(<SignupPage />)

    expect(within(switcher()).getByRole('link', { name: 'Log in' })).toHaveAttribute(
      'href',
      `/login?returnTo=${encodeURIComponent('/')}`
    )
  })

  it('keeps the forgot-password link pointed at the same returnTo', () => {
    searchParams = new URLSearchParams({ returnTo: '/account' })
    render(<LoginPage />)

    expect(screen.getByRole('link', { name: /forgot password/i })).toHaveAttribute(
      'href',
      `/forgot-password?returnTo=${encodeURIComponent('/account')}`
    )
  })
})
