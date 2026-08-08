// Single app-wide display formatters (UI/UX audit §2.4): Indian digit
// grouping for money everywhere, human day-dates instead of raw ISO.

export function formatCurrency(amount: number, currency: string = 'INR'): string {
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    // Unknown/invalid currency code from upstream — degrade to a plain label.
    return `${currency} ${amount.toLocaleString('en-IN')}`
  }
}

/**
 * "priya.sharma@gmail.com" → "pr•••@gm•••.com".
 *
 * Display-only masking for the admin lead queue, so the dashboard can be
 * screen-recorded without putting a real traveler's address on camera. The
 * full address still arrives from the API — an admin has to be able to
 * actually reply to these people — so this is a recording safeguard, not an
 * access control. Treat it as such: it protects against a shoulder-surfer or
 * a video, not against anyone with the network tab open.
 *
 * Enough of the head survives that an admin working the queue can still tell
 * two leads apart at a glance; the TLD is kept because it leaks nothing.
 */
export function maskEmail(email: string): string {
  const at = email.lastIndexOf('@')
  // Not an address shape we recognise — mask the whole thing rather than
  // risk echoing something unexpected straight to the screen.
  if (at <= 0 || at === email.length - 1) return '•••'

  const local = email.slice(0, at)
  const domain = email.slice(at + 1)
  const dot = domain.lastIndexOf('.')
  const domainName = dot > 0 ? domain.slice(0, dot) : domain
  const tld = dot > 0 ? domain.slice(dot) : ''

  const head = (value: string) => (value.length <= 2 ? value : value.slice(0, 2))
  return `${head(local)}•••@${head(domainName)}•••${tld}`
}

/** "2026-11-14" → "Fri, 14 Nov". Non-ISO input is returned unchanged. */
export function formatDayDate(isoDate: string): string {
  if (!isoDate) return ''
  const date = new Date(`${isoDate}T00:00:00`)
  if (Number.isNaN(date.getTime())) return isoDate
  const weekday = date.toLocaleDateString('en-GB', { weekday: 'short' })
  const dayMonth = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return `${weekday}, ${dayMonth}`
}
