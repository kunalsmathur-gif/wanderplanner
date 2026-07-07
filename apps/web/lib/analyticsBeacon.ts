/** Best-effort client-side analytics beacon — posts to the FastAPI
 * `/analytics/client-event` endpoint for events that originate purely in the
 * browser/Next.js server (session start, YouTube thumbnail lookups) rather
 * than in a FastAPI request that already has a DB session to log against.
 *
 * Never throws — a failed beacon must never affect the feature it's
 * attached to.
 */
export function logClientEvent(eventType: string, metadata?: Record<string, unknown>): void {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
  fetch(`${baseUrl}/api/analytics/client-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ event_type: eventType, metadata }),
  }).catch(() => {
    /* analytics beacon is best-effort — never block/break the app */
  })
}
