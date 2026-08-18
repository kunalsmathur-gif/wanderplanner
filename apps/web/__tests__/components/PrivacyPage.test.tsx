import * as React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import PrivacyPage from '@/app/privacy/page'

vi.mock('next/link', () => ({
  default: React.forwardRef<HTMLAnchorElement, React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }>(
    ({ href, children, ...props }, ref) => (
      <a ref={ref} href={href} {...props}>
        {children}
      </a>
    )
  ),
}))

describe('PrivacyPage — back navigation CTAs', () => {
  it('renders the privacy policy heading', () => {
    render(<PrivacyPage />)

    expect(screen.getByRole('heading', { name: /privacy policy/i })).toBeInTheDocument()
  })

  it('renders a "Back to profile" link pointing to /account', () => {
    render(<PrivacyPage />)

    const link = screen.getByRole('link', { name: /back to profile/i })
    expect(link).toHaveAttribute('href', '/account')
  })

  it('renders a "Back to home" link pointing to /', () => {
    render(<PrivacyPage />)

    const link = screen.getByRole('link', { name: /back to home/i })
    expect(link).toHaveAttribute('href', '/')
  })
})
