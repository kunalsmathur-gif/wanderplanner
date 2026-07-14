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

/** "2026-11-14" → "Fri, 14 Nov". Non-ISO input is returned unchanged. */
export function formatDayDate(isoDate: string): string {
  if (!isoDate) return ''
  const date = new Date(`${isoDate}T00:00:00`)
  if (Number.isNaN(date.getTime())) return isoDate
  const weekday = date.toLocaleDateString('en-GB', { weekday: 'short' })
  const dayMonth = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return `${weekday}, ${dayMonth}`
}
