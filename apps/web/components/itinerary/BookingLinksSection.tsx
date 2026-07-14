'use client'

import { useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { cityToIata, isIndianCode } from '@/lib/cityCodes'

type TabId = 'flights' | 'stays' | 'activities'

interface BookingLink {
  name: string
  logo: string
  url: string
  prefilled: boolean
}

function buildLinks(
  origin: string,
  originIata: string,
  destination: string,
  checkin: string,
  checkout: string,
  adults: number,
): Record<TabId, BookingLink[]> {
  const enc = encodeURIComponent
  const d = destination
  const ci = checkin   // YYYY-MM-DD
  const co = checkout

  // Skyscanner path dates: YYYY-MM-DD → YYMMDD
  const skyFmt = (d: string) => d.replace(/-/g, '').slice(2) // 260801

  // MakeMyTrip format: DD/MM/YYYY
  const mmtFmt = (d: string) => {
    if (!d) return ''
    const [y, m, day] = d.split('-')
    return `${day}/${m}/${y}`
  }

  // Skyscanner and MakeMyTrip only accept IATA city codes, not city names —
  // build precise deep-links when both ends resolve, otherwise fall back to
  // their search pages (and say so via `prefilled`).
  const oCode = originIata || cityToIata(origin)
  const dCode = cityToIata(destination)
  const haveCodes = Boolean(oCode && dCode && ci && co)

  // Google Flights' natural-language query pre-fills from city names.
  const gfFrom = origin ? ` from ${origin}` : ''
  const gfQuery =
    ci && co
      ? `Flights${gfFrom} to ${destination} on ${ci} through ${co}`
      : `Flights${gfFrom} to ${destination}`

  return {
    flights: [
      {
        name: 'Google Flights',
        logo: '🔍',
        url: `https://www.google.com/travel/flights?hl=en&q=${enc(gfQuery)}`,
        prefilled: true,
      },
      {
        name: 'Skyscanner',
        logo: '✈️',
        url: haveCodes
          ? `https://www.skyscanner.com/transport/flights/${oCode!.toLowerCase()}/${dCode!.toLowerCase()}/${skyFmt(ci)}/${skyFmt(co)}/?adults=${adults}&cabinclass=economy`
          : 'https://www.skyscanner.com/',
        prefilled: haveCodes,
      },
      {
        name: 'MakeMyTrip',
        logo: '🇮🇳',
        url: haveCodes
          ? `https://www.makemytrip.com/flight/search?tripType=R&itinerary=${oCode}-${dCode}-${mmtFmt(ci)}_${dCode}-${oCode}-${mmtFmt(co)}&paxType=A-${adults}_C-0_I-0&intl=${isIndianCode(oCode!) && isIndianCode(dCode!) ? 'false' : 'true'}`
          : 'https://www.makemytrip.com/flights/',
        prefilled: haveCodes,
      },
    ],
    stays: [
      {
        name: 'Airbnb',
        logo: '🏠',
        url: `https://www.airbnb.com/s/${enc(d)}/homes?checkin=${ci}&checkout=${co}&adults=${adults}`,
        prefilled: true,
      },
      {
        name: 'Booking.com',
        logo: '🏨',
        url: `https://www.booking.com/searchresults.html?ss=${enc(d)}&checkin=${ci}&checkout=${co}&group_adults=${adults}&no_rooms=1`,
        prefilled: true,
      },
      {
        name: 'Hotels.com',
        logo: '🛎️',
        url: `https://www.hotels.com/search.do?q-destination=${enc(d)}&q-check-in=${ci}&q-check-out=${co}&q-rooms=1&q-room-0-adults=${adults}`,
        prefilled: true,
      },
    ],
    activities: [
      {
        name: 'Klook',
        logo: '🎡',
        url: `https://www.klook.com/en-IN/search/?query=${enc(d)}`,
        prefilled: true,
      },
      {
        name: 'GetYourGuide',
        logo: '🎟️',
        url: `https://www.getyourguide.com/s/?q=${enc(d)}&date_from=${ci}&date_to=${co}&travelers=${adults}`,
        prefilled: true,
      },
      {
        name: 'Viator',
        logo: '🗺️',
        url: `https://www.viator.com/search/${enc(d)}?startDate=${ci}&endDate=${co}&adults=${adults}`,
        prefilled: true,
      },
    ],
  }
}

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'flights',    label: 'Flights',    icon: '✈️'  },
  { id: 'stays',      label: 'Stays',      icon: '🏨'  },
  { id: 'activities', label: 'Activities', icon: '🎟️' },
]

export function BookingLinksSection() {
  const config = useTripConfigStore((s) => s.config)
  const days = useItineraryStore((s) => s.days)
  const [activeTab, setActiveTab] = useState<TabId>('flights')

  const dest = config.destination?.city
  const origin = config.origin.city
  const originIata = config.origin.iata
  const checkin = config.dates.start ?? ''
  const checkout = config.dates.end ?? ''
  const adults = Math.max(1, config.group.adults + config.group.seniors)

  if (!dest) return null

  const links = buildLinks(origin, originIata, dest, checkin, checkout, adults)
  const allPrefilled = links[activeTab].every((l) => l.prefilled)

  const nightCount = (() => {
    if (!checkin || !checkout) return null
    try {
      const diff = (new Date(checkout).getTime() - new Date(checkin).getTime()) / 86400000
      return diff > 0 ? diff : null
    } catch { return null }
  })()

  return (
    <div className="border-t border-[var(--_border)] pt-4 space-y-3">
      <h3 className="text-xs font-semibold text-[var(--_muted-fg)] uppercase tracking-wide">
        🔗 Book This Trip
      </h3>

      {/* Pre-fill summary */}
      <p className="text-xs text-[var(--_muted-fg)] leading-relaxed">
        {origin} → <span className="font-medium text-[var(--_fg)]">{dest}</span>
        {checkin && ` · ${checkin}`}
        {nightCount && ` (${nightCount}n)`}
        {` · ${adults} adult${adults > 1 ? 's' : ''}`}
      </p>

      {/* Tabs */}
      <div className="flex rounded-lg border border-[var(--_border)] overflow-hidden text-xs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            aria-label={t.label}
            className={[
              'flex-1 py-1.5 font-medium transition-colors flex items-center justify-center gap-1',
              activeTab === t.id
                ? 'bg-[var(--_primary)] text-[var(--_on-primary)]'
                : 'text-[var(--_muted-fg)] hover:bg-[var(--_muted)]',
            ].join(' ')}
          >
            <span>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* Links */}
      <div className="space-y-2">
        {links[activeTab].map((link) => (
          <a
            key={link.name}
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between w-full px-3 py-2.5 rounded-lg border border-[var(--_border)] bg-[var(--_card)] hover:border-[var(--_primary)] hover:bg-[var(--_muted)] transition-all group"
          >
            <div className="flex items-center gap-2">
              <span className="text-base">{link.logo}</span>
              <span className="text-sm font-medium text-[var(--_fg)] group-hover:text-[var(--_primary)]">
                {link.name}
              </span>
            </div>
            <svg
              width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              className="text-[var(--_muted-fg)] group-hover:text-[var(--_primary)] shrink-0"
            >
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        ))}
      </div>

      <p className="text-xs text-[var(--_muted-fg)]">
        {allPrefilled
          ? 'Links open pre-filled with your trip details.'
          : 'Some links open as a search page — pre-fill isn’t available for this route yet.'}
      </p>
    </div>
  )
}
