/**
 * Deterministic "start over" intent detection for the wizard chat.
 *
 * Bug fix (live-observed): `tripConfigStore` persists across page
 * refreshes/reopens (sessionStorage, by design — see that store's
 * docstring, it's what lets a mid-wizard refresh not lose progress). But
 * re-opening the wizard from the home page never cleared it, so a user who
 * already had a completed trip and simply typed "I want to start from
 * scratch" got every subsequent turn answered against their OLD,
 * fully-collected config — `wizard_chat_chain.py` has no "wipe everything"
 * instruction, so it just kept trying to patch/confirm the existing trip,
 * which read to the user as "it won't let me start fresh".
 *
 * The actual reset (`LLMWizard.tsx`'s `handleStartOver`) already existed
 * for the feasibility-block "Start over" chip — it just had no free-text
 * trigger. This module is that trigger, factored out so the matching rule
 * is unit-testable without mounting the whole wizard component.
 */

// Not anchored to the start of the message (people phrase this as "I want
// to start from scratch", "can we start over?", etc.) — instead gated by
// the caller on a short message length so it doesn't fire on an unrelated
// sentence that happens to contain e.g. "new trip" as one clause among
// several the wizard still needs to hear (see MAX_LEN below).
const START_OVER_INTENT_RE =
  /\b(start|begin)(?:ing)?\s+(over|again|fresh|from\s+scratch)\b|\b(scrap|forget|discard|reset)\s+(this|the current|everything)\b|\b(plan|planning)\s+a\s+(completely\s+)?(new|different)\s+trip\b/i

export const START_OVER_INTENT_MAX_LEN = 80

export function isStartOverIntent(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed || trimmed.length > START_OVER_INTENT_MAX_LEN) return false
  return START_OVER_INTENT_RE.test(trimmed)
}
