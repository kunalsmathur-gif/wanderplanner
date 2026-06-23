import type { Metadata, Viewport } from 'next'
import { Space_Grotesk, DM_Sans, JetBrains_Mono } from 'next/font/google'
import { MobileWarningBanner } from '@/components/common/MobileWarningBanner'
import './globals.css'

// Skill: Space Grotesk for display/headings — tech-forward, bold, editorial
const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space-grotesk',
})

// Skill: DM Sans for body — premium, modern, clean
const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-dm-sans',
})

// Monospace for timestamps and data labels
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains',
})

export const viewport: Viewport = { themeColor: '#0EA5E9' }

export const metadata: Metadata = {
  title: 'Wanderplan',
  description: 'Plan group trips with AI-powered, personalised itineraries. No sign-up required.',
}

// Blocking script: reads localStorage before first paint to prevent dark-mode flash
const themeScript = `
(function() {
  try {
    var t = localStorage.getItem('wp-theme');
    if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    }
  } catch(e) {}
})();
`

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${dmSans.variable} ${jetbrainsMono.variable} h-full`}
      suppressHydrationWarning
    >
      <head>
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: theme script must run synchronously before paint */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="h-full min-w-[320px] antialiased">
        <MobileWarningBanner />
        {children}
      </body>
    </html>
  )
}
