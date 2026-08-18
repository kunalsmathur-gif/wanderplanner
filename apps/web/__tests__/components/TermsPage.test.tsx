import * as React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TermsPage from '@/app/terms/page'

vi.mock('next/link', () => ({
  default: React.forwardRef<HTMLAnchorElement, React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }>(
    ({ href, children, ...props }, ref) => (
      <a ref={ref} href={href} {...props}>
        {children}
      </a>
    )
  ),
}))

describe('TermsPage — back navigation CTAs', () => {
  it('renders the terms of service heading', () => {
    render(<TermsPage />)

    expect(screen.getByRole('heading', { name: /terms of service/i })).toBeInTheDocument()
  })

  it('renders a "Back to profile" link pointing to /account', () => {
    render(<TermsPage />)

    const link = screen.getByRole('link', { name: /back to profile/i })
    expect(link).toHaveAttribute('href', '/account')
  })

  it('renders a "Back to home" link pointing to /', () => {
    render(<TermsPage />)

    const link = screen.getByRole('link', { name: /back to home/i })
    expect(link).toHaveAttribute('href', '/')
  })
})
