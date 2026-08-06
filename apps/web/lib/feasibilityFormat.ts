import type { FeasibilityResponse } from '@/types'

/** Human-readable cost breakdown line shared by every surface that shows a
 * feasibility verdict (initial-generation wizard, in-chat regeneration).
 * Kept in one place so the three-state visa handling (null = not looked up,
 * 0 = genuinely free, >0 = real figure — see CostBreakdown.visa_inr) can't
 * drift between call sites. */
export function formatFeasibilityBreakdown(result: FeasibilityResponse): string {
  const b = result.breakdown
  return [
    b.flights_inr > 0 ? `flights ₹${b.flights_inr.toLocaleString('en-IN')}` : null,
    b.visa_inr == null
      ? 'visa/entry cost not available — check officially'
      : b.visa_inr > 0
        ? `visa/entry ₹${b.visa_inr.toLocaleString('en-IN')}`
        : 'no visa/entry fee',
    b.accommodation_inr > 0 ? `stay ₹${b.accommodation_inr.toLocaleString('en-IN')}` : null,
    b.daily_expenses_inr > 0 ? `food/local transport ₹${b.daily_expenses_inr.toLocaleString('en-IN')}` : null,
  ].filter(Boolean).join(', ')
}

/** Line-by-line breakdown (one bullet per category, with amount and % of
 * total) for the "Show budget breakdown" chip — the compact comma-joined
 * `formatFeasibilityBreakdown` line is fine for a verdict message, but
 * doesn't give the user enough to decide *what* to actually cut. Each line
 * is deliberately actionable: it names the category so the user can reply
 * "cut accommodation" / "fewer days" / etc. with something concrete to
 * point at. */
export function formatFeasibilityBreakdownDetailed(result: FeasibilityResponse): string {
  const b = result.breakdown
  const total = b.total_estimated_inr || 1 // guard divide-by-zero; total is never legitimately 0
  const pct = (n: number) => `${Math.round((n / total) * 100)}%`
  const lines: string[] = []
  if (b.flights_inr > 0) {
    lines.push(`✈️ Flights: ₹${b.flights_inr.toLocaleString('en-IN')} (${pct(b.flights_inr)})`)
  }
  if (b.visa_inr == null) {
    lines.push('🛂 Visa/entry: not available — check officially')
  } else if (b.visa_inr > 0) {
    lines.push(`🛂 Visa/entry: ₹${b.visa_inr.toLocaleString('en-IN')} (${pct(b.visa_inr)})`)
  } else {
    lines.push('🛂 Visa/entry: free')
  }
  if (b.accommodation_inr > 0) {
    lines.push(`🏨 Accommodation: ₹${b.accommodation_inr.toLocaleString('en-IN')} (${pct(b.accommodation_inr)})`)
  }
  if (b.daily_expenses_inr > 0) {
    lines.push(`🍽️ Food & local transport: ₹${b.daily_expenses_inr.toLocaleString('en-IN')} (${pct(b.daily_expenses_inr)})`)
  }
  lines.push(`— Total (bare minimum): ₹${b.total_estimated_inr.toLocaleString('en-IN')}`)
  lines.push(`— Your budget: ₹${result.budget_inr.toLocaleString('en-IN')}`)
  lines.push(`— Shortfall: ₹${result.shortfall_inr.toLocaleString('en-IN')}`)
  return lines.join('\n')
}

/** Same figure the verdict/shortfall was computed against
 * (breakdown.total_estimated_inr, which already folds in the deterministic
 * floor when it's the binding constraint — see
 * chains/feasibility_chain.py::_build_response). Do NOT use
 * bare_minimum_inr: it's a separate, often-lower reference figure that can
 * disagree with the verdict. */
export function suggestedFeasibleBudget(result: FeasibilityResponse): number {
  return result.breakdown.total_estimated_inr
}
