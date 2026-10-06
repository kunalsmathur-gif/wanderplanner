import type { DestinationCandidate } from '@/types'

interface Props {
  destinations: DestinationCandidate[]
}

/** Flattened, de-duplicated events across all candidate destinations —
 * accessible/fallback representation of the same event markers shown on
 * WorkationMapWrapper. */
export function EventsAroundYou({ destinations }: Props) {
  const events = destinations.flatMap((d) => d.matching_events)

  if (events.length === 0) {
    return (
      <p className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4 text-sm text-[var(--_muted-fg)]">
        Nothing found for your interests around this window yet.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-2.5">
      {events.map((event, idx) => (
        <li
          key={`${event.name}-${idx}`}
          className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4"
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-semibold text-[var(--_fg)]">{event.name}</p>
            <span className="shrink-0 rounded-full bg-[var(--_primary)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--_primary)]">
              {event.interest_category}
            </span>
          </div>
          <p className="mt-1 text-xs text-[var(--_muted-fg)]">
            {event.location} · {event.start_date} – {event.end_date}
          </p>
          <p className="mt-1 text-[11px] text-[var(--_muted-fg)]">Source: {event.source_citation}</p>
          {event.deep_link && (
            <a
              href={event.deep_link}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-xs font-medium text-[var(--_primary)] hover:underline"
            >
              View event →
            </a>
          )}
        </li>
      ))}
    </ul>
  )
}
