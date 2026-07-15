import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Sign up',
  description: 'Create your free Wanderplanner account — no credit card required.',
}

export default function SignupLayout({ children }: { children: React.ReactNode }) {
  return children
}
