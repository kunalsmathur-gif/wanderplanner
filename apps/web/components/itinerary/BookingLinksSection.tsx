'use client'

import { useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'

type TabId = 'flights' | 'stays' | 'activities'

interface BookingLink {
  name: string
  logo: string
  url: string
}

function buildLinks(
  origin: string,
  destination: string,
  checkin: string,
  checkout: string,
  adults: number,
): Record<TabId, BookingLink[]> {
  const enc = encodeURIComponent
  const d = destination
  const ci = checkin   // YYYY-MM-DD
  const co = checkout

  // Compact date for Skyscanner: YYYYMMDD → YYMMDD
  const skyFmt = (d: string) => d.replace(/-/g, '').slice(2) // 260801

  // MakeMyTrip format: DD/MM/YYYY
  const mmtFmt = (d: string) => {
    if (!d) return ''
    const [y, m, day] = d.split('-')
    return `${day}/${m}/${y}`
  }

  return {
    flights: [
      {
        name: 'Google Flights',
        logo: '🔍',
        url: `https://www.google.com/flights?hl=en#search;f=${enc(origin)};t=${enc(destination)};d=${ci};r=${co};px=${adults}`,
      },
      {
        name: 'Skyscanner',
        logo: '✈️',
        url: `https://www.skyscanner.com/transport/flights/${enc(origin)}/${enc(destination)}/${skyFmt(ci)}/${skyFmt(co)}/?adults=${adults}&cabinclass=economy`,
      },
      {
        name: 'MakeMyTrip',
        logo: '🇮🇳',
        url: `https://www.makemytrip.com/flight/search?tripType=R&itinerary=${enc(origin)}-${enc(destination)}-${mmtFmt(ci)}-${enc(destination)}-${enc(origin)}-${mmtFmt(co)}&paxType=A-${adults}_C-0_I-0&intl=true`,
      },
    ],
    stays: [
      {
        name: 'Airbnb',
        logo: '🏠',
        url: `https://www.airbnb.com/s/${enc(d)}/homes?checkin=${ci}&checkout=${co}&adults=${adults}`,
      },
      {
        name: 'Booking.com',
        logo: '🏨',
        url: `https://www.booking.com/searchresults.html?ss=${enc(d)}&checkin=${ci}&checkout=${co}&group_adults=${adults}&no_rooms=1`,
      },
      {
        name: 'Hotels.com',
        logo: '🛎️',
        url: `https://www.hotels.com/search.do?q-destination=${enc(d)}&q-check-in=${ci}&q-check-out=${co}&q-rooms=1&q-room-0-adults=${adults}`,
      },
    ],
    activities: [
      {
        name: 'Klook',
        logo: '🎡',
        url: `https://www.klook.com/en-IN/search/?query=${enc(d)}`,
      },
      {
        name: 'GetYourGuide',
        logo: '🎟️',
        url: `https://www.getyourguide.com/s/?q=${enc(d)}&date_from=${ci}&date_to=${co}&travelers=${adults}`,
      },
      {
        name: 'Viator',
        logo: '🗺️',
        url: `https://www.viator.com/search/${enc(d)}?startDate=${ci}&endDate=${co}&adults=${adults}`,
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
  const origin = config.origin.iata || config.origin.city
  const checkin = config.dates.start ?? ''
  const checkout = config.dates.end ?? ''
  const adults = Math.max(1, config.group.adults + config.group.seniors)

  if (!dest || !checkin) return null

  const links = buildLinks(origin, dest, checkin, checkout, adults)

  const nightCount = (() => {
    if (!checkin || !checkout) return null
    try {
      const diff = (new Date(checkout).getTime() - new Date(checkin).getTime()) / 86400000
      return diff > 0 ? diff : null
    } catch { return null }
  })()

  return (
    <div className="border-t border-slate-200 pt-4 space-y-3">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        🔗 Book This Trip
      </h3>

      {/* Pre-fill summary */}
      <p className="text-xs text-slate-400 leading-relaxed">
        {origin} → <span className="font-medium text-slate-600">{dest}</span>
        {checkin && ` · ${checkin}`}
        {nightCount && ` (${nightCount}n)`}
        {` · ${adults} adult${adults > 1 ? 's' : ''}`}
      </p>

      {/* Tabs */}
      <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={[
              'flex-1 py-1.5 font-medium transition-colors flex items-center justify-center gap-1',
              activeTab === t.id
                ? 'bg-[#1E40AF] text-white'
                : 'text-slate-500 hover:bg-slate-50',
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
            className="flex items-center justify-between w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-white hover:border-[#1E40AF] hover:bg-blue-50 transition-all group"
          >
            <div className="flex items-center gap-2">
              <span className="text-base">{link.logo}</span>
              <span className="text-sm font-medium text-slate-700 group-hover:text-[#1E40AF]">
                {link.name}
              </span>
            </div>
            <svg
              width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              className="text-slate-400 group-hover:text-[#1E40AF] shrink-0"
            >
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        ))}
      </div>

      <p className="text-xs text-slate-400">
        Links open pre-filled with your trip details.
      </p>
    </div>
  )
}
