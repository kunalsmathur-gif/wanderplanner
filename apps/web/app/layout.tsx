import type { Metadata, Viewport } from 'next'
import { Space_Grotesk, DM_Sans, JetBrains_Mono } from 'next/font/google'
import { AuthHydrator } from '@/components/common/AuthHydrator'
import './globals.css'

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space-grotesk',
})

const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-dm-sans',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains',
})

// `width`/`initialScale` are required — without them Next emits no
// `<meta name="viewport">` tag at all (see metadata.js::createViewportElements),
// so mobile browsers fall back to a ~980px desktop-emulation viewport and
// scale the page down, leaving real blank canvas to the right that pinch-zoom
// or horizontal scroll can reveal.
//
// `userScalable: false` locks the layout to the device's actual size —
// deliberately overriding the WCAG 1.4.4 "always allow zoom" default. Capping
// `maximumScale` alone isn't enough: pinch-zoom operates on the browser's
// visual viewport (a compositor-level zoom/pan) which is independent of the
// CSS overflow model, so even `overflow-x: hidden` can't stop panning into
// blank canvas once a user has manually zoomed. Disabling user-scalable is
// the only way to prevent both the zoomed-out blank canvas and the
// post-zoom pan-right, matching this being an app-like mobile experience
// with its own bottom-nav rather than a long-form reading page.
export const viewport: Viewport = {
  themeColor: '#0EA5E9',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
}

const SITE_URL = 'https://wanderplanner.app'
const SITE_TITLE = 'Wanderplanner — Free AI Travel Planner & Itinerary Generator'
const SITE_DESCRIPTION =
  'Wanderplanner is a free AI travel planner. Tell Anya — our AI concierge — your destination, budget, and group. Get a personalised day-by-day itinerary for Bali, Europe, Rajasthan, Dubai, and 190+ countries. Free sign-up, no credit card required.'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: '%s | Wanderplanner AI Travel Planner',
  },
  description: SITE_DESCRIPTION,
  keywords: [
    'AI travel planner',
    'free trip planner',
    'AI itinerary generator',
    'travel itinerary',
    'trip planning India',
    'Bali trip planner',
    'Europe trip itinerary',
    'Rajasthan travel guide',
    'Dubai trip planner',
    'group travel planner',
    'day by day itinerary',
    'free travel planner',
    'AI vacation planner',
    'Wanderplanner',
    'Gemini travel AI',
    'personalized travel itinerary',
    'budget travel planner',
    'family trip planner',
    'honeymoon itinerary planner',
    'solo trip planner',
  ],
  authors: [{ name: 'Wanderplanner', url: SITE_URL }],
  creator: 'Wanderplanner',
  publisher: 'Wanderplanner',
  category: 'travel',
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, 'max-snippet': -1, 'max-image-preview': 'large' },
  },
  alternates: { canonical: SITE_URL },
  openGraph: {
    type: 'website',
    locale: 'en_IN',
    url: SITE_URL,
    siteName: 'Wanderplanner',
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [
      {
        url: '/og-image.png',
        width: 1200,
        height: 630,
        alt: 'Wanderplanner — AI Travel Planner',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: ['/og-image.png'],
    creator: '@wanderplannerapp',
  },
  verification: {
    google: 'YOUR_GOOGLE_SEARCH_CONSOLE_TOKEN',
  },
}

// JSON-LD structured data for Google rich results
const jsonLd = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': `${SITE_URL}/#organization`,
      name: 'Wanderplanner',
      url: SITE_URL,
      description: 'Free AI-powered travel planning and itinerary generation',
    },
    {
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      url: SITE_URL,
      name: 'Wanderplanner',
      description: SITE_DESCRIPTION,
      publisher: { '@id': `${SITE_URL}/#organization` },
      potentialAction: {
        '@type': 'SearchAction',
        target: { '@type': 'EntryPoint', urlTemplate: `${SITE_URL}/?q={search_term_string}` },
        'query-input': 'required name=search_term_string',
      },
    },
    {
      '@type': 'WebApplication',
      '@id': `${SITE_URL}/#app`,
      name: 'Wanderplanner AI Travel Planner',
      url: SITE_URL,
      applicationCategory: 'TravelApplication',
      operatingSystem: 'Web browser',
      description:
        'Free AI travel planner that generates personalized day-by-day itineraries for any destination worldwide. Covers budgeting, group planning, activities, and local tips.',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      featureList: [
        'AI-generated day-by-day itineraries',
        'Budget-aware travel planning',
        'Group and family trip planning',
        'Real-time weather and travel tips',
        'Destination comparison tool',
      ],
    },
    {
      '@type': 'FAQPage',
      mainEntity: [
        {
          '@type': 'Question',
          name: 'Is Wanderplanner free to use?',
          acceptedAnswer: {
            '@type': 'Answer',
            text: 'Yes. Wanderplanner is completely free. Just a free sign-up — no credit card required.',
          },
        },
        {
          '@type': 'Question',
          name: 'How does Wanderplanner generate itineraries?',
          acceptedAnswer: {
            '@type': 'Answer',
            text: 'Wanderplanner uses Google Gemini AI along with real traveller data from Reddit, Wikivoyage, and live weather to build personalised day-by-day travel plans.',
          },
        },
        {
          '@type': 'Question',
          name: 'Which destinations does Wanderplanner support?',
          acceptedAnswer: {
            '@type': 'Answer',
            text: 'Wanderplanner supports 190+ countries and thousands of cities including Bali, Paris, Dubai, Tokyo, Rajasthan, New York, and more.',
          },
        },
        {
          '@type': 'Question',
          name: 'Can Wanderplanner plan group or family trips?',
          acceptedAnswer: {
            '@type': 'Answer',
            text: 'Yes. Wanderplanner handles solo trips, couples, families with children, and large groups. Just tell Anya who is travelling and she tailors the itinerary accordingly.',
          },
        },
      ],
    },
  ],
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
        <script
          type="application/ld+json"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: structured data JSON-LD
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="h-full min-w-[320px] overflow-x-hidden antialiased">
        <AuthHydrator />
        {children}
      </body>
    </html>
  )
}
