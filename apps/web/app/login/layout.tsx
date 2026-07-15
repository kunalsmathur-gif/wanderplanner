import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Log in',
  description: 'Log in to Wanderplanner to continue planning your trip.',
}

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children
}
