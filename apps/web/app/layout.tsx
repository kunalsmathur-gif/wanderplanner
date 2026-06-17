import type { Metadata, Viewport } from 'next'
import { Fraunces, Inter, JetBrains_Mono } from 'next/font/google'
import { MobileWarningBanner } from '@/components/common/MobileWarningBanner'
import './globals.css'

// Display face for headers and Anya's name
const fraunces = Fraunces({ 
  subsets: ['latin'], 
  variable: '--font-fraunces',
  axes: ['opsz', 'SOFT', 'WONK'], // Enable variable axes for personality
})

// Body face with tighter tracking
const inter = Inter({ 
  subsets: ['latin'], 
  variable: '--font-inter',
})

// Monospace for timestamps and data
const jetbrainsMono = JetBrains_Mono({ 
  subsets: ['latin'], 
  variable: '--font-jetbrains',
})

export const viewport: Viewport = { themeColor: '#1A3A52' } // Updated to Passport Navy

export const metadata: Metadata = {
  title: 'WanderPlan — AI Travel Advisor',
  description: 'Plan group trips with AI-powered, personalised itineraries. No sign-up required.',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${fraunces.variable} ${inter.variable} ${jetbrainsMono.variable} h-full`}>
      <body className="h-full min-w-[320px] bg-white text-slate-900 antialiased">
        <MobileWarningBanner />
        {children}
      </body>
    </html>
  )
}
