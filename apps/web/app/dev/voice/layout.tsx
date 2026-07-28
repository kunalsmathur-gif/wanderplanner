import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Voice capability check',
  description: 'On-device diagnostic for the Web Speech API.',
  // A developer tool, not a product page.
  robots: { index: false, follow: false },
}

export default function VoiceCheckLayout({ children }: { children: React.ReactNode }) {
  return children
}
