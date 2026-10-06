// Reuses the same interest/theme vocabulary already used by the wizard's
// theme chips (see THEME_CHIP_KEYWORDS in components/wizard/LLMWizard.tsx)
// so a user's mental model of "interests" stays consistent across surfaces.
// Shared between both Leave Planner discovery modes (state/long-weekend
// anchored, and the stateless "browse events for a weekend" mode) so the
// chip vocabulary never drifts between them.
//
// "Music" added 2026-10-06 — the backend's india_events corpus already
// tags a dedicated "music" interest_category (see
// apps/api/scrapers/india_events.py's `InterestCategory` literal and the
// District.in scraper tier), it just wasn't exposed as a filter option yet.
export const LEAVE_PLANNER_INTERESTS = [
  'Culture', 'Nature', 'Food', 'Adventure', 'Shopping', 'Photography',
  'Nightlife', 'Music', 'Sports', 'Wellness', 'Religious',
] as const
