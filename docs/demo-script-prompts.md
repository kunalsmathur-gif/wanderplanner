# Demo Script — Prompts to Type/Click

Companion to `docs/demo-script-validation.md`. Every line below was verified
live against **production** (`wanderplanner.org`) on 2026-08-07 via a fresh
test account and real API calls — not read from code.

---

## Beat ① — Reach the feasibility gate (4 turns, TC-1)

Type these exactly, in order:

1. `6-day Bali trip, 2 adults, 20000 rupees`
2. `It's a leisure beach and temples holiday, 10 to 15 September 2026`
3. `Moderate pace`
4. Click **`Just generate it!`** on the checkpoint — leave "Add departure
   city" / "Pure veg food" chips alone, don't click them.

**Narration tip:** don't quote the exact rupee shortfall — the LLM estimate
varies ±17% run to run (documented, not a bug). Say "she puts the realistic
minimum near a lakh and a half against a twenty-thousand budget" and read
the actual number off-screen live.

## Beat ① — The gate itself (TC-2)

Nothing to type — it fires automatically after step 4 above.

Click **`Set budget to ₹[whatever the card shows]`** to demo the recovery
path (re-runs the gate, then auto-generates after ~1.2s).

## Beat ③ — Pin a real place mid-refinement (TC-3, after the itinerary exists)

```
we're really into iconic Balinese temples and sunset views
```

This is the single best shot in the demo — pins **Tanah Lot Temple** and
**Uluwatu Temple** (both real OSM coordinates, will render on the map) and
honestly lists unverifiable candidates in the same reply. Auto-regenerates,
no confirm click needed.

🔴 Do **not** use `must include Tanah Lot` or `I really want to see Tanah
Lot` during setup — neither pins anything (pinning is driven by named
interests, not bare place names).

## Beat ③ — A refinement that recalculates the total (TC-4)

```
cut my budget to 1,20,000 rupees
```

Then click the confirm chip that appears → triggers regenerate +
"✅ Here's what changed" diff.

## Beat ③ — Per-day cost edit (bonus beat — fixed since the last validation pass)

```
make day 3 cheaper
```

Auto-regenerates immediately, no confirm needed — pins stay put.

## Beat ④ — Live honesty refusal (fixed since the last validation pass)

1. Set destination to Goa (via wizard or `preloaded_destination`).
2. In refinement chat:

```
I'm a huge Harry Potter fan — anything for that here?
```

She now explicitly says she couldn't verify anything and pins nothing —
"better honest than invented."

## Beat ⑤/⑦ — nothing to type

Handoff/SLA and the logout-security fix are shown via the admin dashboard
or a code walkthrough, not chat input.

---

## Things to avoid saying/typing on camera

Still broken as of the last full validation pass (`docs/demo-script-validation.md`):

- ❌ `must include Tanah Lot` / `I really want to see Tanah Lot` during
  setup — neither pins anything.
- ❌ Narrating "eight categories" for the cost breakdown — Bali/Goa both
  render 7 (visa row hidden when it's ₹0).
- ❌ "Two handoff triggers" — only one exists (`escalated`/`reassured` are
  states of that same trigger, not a second one).
- ❌ "TTS is off" — it's live in production (`TTS_PROVIDER=google`); Anya
  can speak if you want to demo it.
