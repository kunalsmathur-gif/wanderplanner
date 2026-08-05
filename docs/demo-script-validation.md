# Demo Script Validation — `docs/video-script-4min.md` v3

**Validated:** 2026-08-04 · against `7e43c37` and **live production** (`wanderplanner.org` / `api-production-3e3e.up.railway.app`)
**Method:** every factual/behavioural claim in the script was executed, not read. Live API calls, a real 4-turn wizard conversation, two real itinerary generations through the production chain, and a re-run of the refinement eval gate. Raw outputs are reproduced verbatim below.

---

## 1. Verdict at a glance

| # | Claim | Verdict |
|---|---|---|
| ① | One typed line renders the feasibility gate | 🔴 **Does not work** — needs 4 turns |
| ① | "Realistic minimum ₹1,46,000 · short by ₹1,26,000" | ⚠️ **Not reproducible** — LLM-generated, ±17% run to run |
| ② | Grounded in OSM + Wikivoyage + YouTube | ✅ Verified (4 live collections, 79k points) |
| ② | Hybrid vector + keyword retrieval, then reranked | ✅ Verified (BM25+semantic RRF, cross-encoder on the generation path) |
| ② | "Can't safely price it → hands to a human" | 🔴 **Not implemented** — only one handoff trigger exists, and it isn't this |
| ③ | Chip says "Raise budget", set to ₹1,60,000 | 🔴 **Wrong label and wrong number** — app dictates the figure |
| ③ | Itinerary streams, ×4 speed label | ✅ Achievable (editing overlay, not an app feature; 40–48s → ~11s at ×4) |
| ③ | Cost breakdown across **eight** categories | 🔴 **Renders 7** for Bali — zero-value rows are hidden |
| ③ | "make day 3 cheaper" → what-changed summary | 🔴 **Does nothing** — no regeneration, no diff, no new total |
| ③ | Tanah Lot "locked in at the very start" survives | 🔴 **No pin is ever created** by the wizard |
| ③ | Pins survive regeneration, total recalculates | ✅ Verified — but only via a *refinement* pin |
| ④ | "Pins hold across every test case" | ✅ Verified (inclusion 1.00, stability 1.00, 16/16) |
| ④ | "Beats a general model on saying only what's true" | ✅ Verified (honesty 4/4 vs 0/4; unverifiable 0.00 vs 0.74) |
| ④ | Deck's headline **0.992** | ⚠️ **Unpublished** — real (run on another machine), but no committed artifact shows it |
| ④ | Deck's "vs ChatGPT 0.74" | 🔴 **Metric mismatch** — 0.74 is a different measure |
| ④ | Live: "no Wizarding World in Goa, she says so" | 🔴 **She does not say so** |
| ⑤ | Two handoff triggers | 🔴 **One exists** |
| ⑤ | 24-hour SLA, hourly job, 48h fallback | ✅ Verified in code |
| ⑤ | Statuses pending / escalated / responded | ⚠️ There is a **fourth**, `reassured` |
| ⑥ | Live at wanderplanner.org | ✅ Verified, HTTP 200 |
| ⑥ | Cost per itinerary a fraction of a cent | ✅ Consistent with the deck's $0.003–0.007 |
| ⑦ | "A stranger's data could've leaked, and I closed it" | ✅ **True** — two real fixes back it |
| Setup | "Do not demo Anya speaking — TTS is off" | 🔴 **Stale — TTS is LIVE in production** |

---

## 2. Blockers, with evidence

### 2.1 🔴 Beat ① — one line does not open the gate

The gate only runs when the wizard sets `ready_to_generate: true`, which needs all six required fields (`purpose`, destination, `dates.start`+`dates.end`, `budget`, `group.adults`, `pace`) **plus** the "anything else?" checkpoint **plus** an explicit go-ahead — `chains/wizard_chat_chain.py::_has_all_required` and Stage 3 of the prompt. `LLMWizard.tsx:533` only calls `runFeasibilityGate` inside `if (res.ready_to_generate)`.

The script's exact cold-open line returns:

```
INPUT: 6-day Bali trip, 2 adults, ₹20,000, must include Tanah Lot
ready_to_generate: false
config_patch: destination, group, budget, dates{duration_days:6}    ← no start/end
missing: purpose, dates.start, dates.end, pace, checkpoint, go-ahead
```

Note it also extracted **no** `dates.start`/`end` — only `duration_days`, which `_has_all_required` rejects.

**Working 4-turn transcript** (§3.1) reaches the gate.

### 2.2 ⚠️ Beat ① — the numbers are not reproducible

`chains/feasibility_chain.py` asks Gemini for the estimate (temperature 0.2) and only applies the deterministic `bare_minimum` as a *floor*. The floor never binds here, so what appears on screen is an LLM number. Five live runs, identical input:

| Origin | Total | Shortfall | Floor | Flights | Visa | Latency |
|---|---|---|---|---|---|---|
| Mumbai | ₹2,36,150 | ₹2,16,150 | ₹1,76,200 | ₹1,30,000 | `null` | 38.6s |
| Mumbai | ₹2,33,400 | ₹2,13,400 | ₹1,76,200 | ₹1,30,000 | ₹5,600 | 26.6s |
| Mumbai | ₹2,73,550 | ₹2,53,550 | ₹1,76,200 | ₹1,56,000 | ₹5,500 | 23.4s |
| Mumbai | ₹2,67,606 | ₹2,47,606 | ₹1,76,200 | ₹1,50,000 | ₹5,406 | 23.3s |
| *(blank)* | **₹1,48,000** | **₹1,28,000** | ₹81,500 | ₹70,000 | ₹0 | ~25s |

Two things fall out:

1. **The script's ₹1,46,000/₹1,26,000 came from a no-departure-city run** — the last row is within 1.4% of it. That's the natural flow (origin is optional and the wizard doesn't ask for it), so the figure is *plausible*, just not repeatable. Spread across runs is ±17%.
2. **`visa_inr` flips between `null` and a real figure run to run.** On the `null` run the UI prints *"visa/entry cost not available — check officially"*; otherwise *"visa/entry ₹5,600"*. Whichever you narrate can be wrong on the take.

**Fix:** narrate the shape, not the digits — "she puts the realistic minimum near a lakh and a half, against a twenty-thousand budget." Or read the number off the screen live.

### 2.3 🔴 Beat ③ — the "Raise budget → ₹1,60,000" step doesn't exist

`LLMWizard.tsx:606` builds the chips from the API response:

```ts
chips: [`Set budget to ₹${minBudget.toLocaleString('en-IN')}`, PROCEED_ANYWAY_CHIP, 'Let me adjust something else']
```

So the chip reads **"Set budget to ₹2,36,150"** (or whatever that run produced) — not "Raise budget", and the number is the app's, not yours. And `minBudget` is `breakdown.total_estimated_inr`, so **₹1,60,000 would fail the gate a second time**: it's below every total measured above.

### 2.4 🔴 Beat ③ — "make day 3 cheaper" does nothing

Two live phrasings against a real Bali config:

```
IN : make day 3 cheaper
   action_type = none      major_change = False    config_patch = null
   reply: "Got it! I'll make a note to optimize Day 3 of your itinerary to be more
           budget-friendly when I generate the plan."

IN : make day 3 cheaper, skip the expensive stuff
   action_type = patch_config   major_change = False
   config_patch = {"save_categories": ["activities"]}
   reply: "...While I don't have a day-by-day itinerary to adjust just yet..."
```

`ChatPanel.tsx:120-129` only regenerates (and therefore only posts the *"Here's what changed"* diff) when either the patch contains `pinned_pois`, or `action_type === 'regenerate' && major_change`. Neither holds. **No regeneration, no diff, no recalculated total, and the itinerary on screen is unchanged.** Worse, both replies promise an adjustment that is never made.

Per-day cost editing simply isn't a capability — `ACTION RULES` in `chat_refine_chain.py` has no rule for it.

### 2.5 🔴 Beat ③ — nothing is pinned "at the very start"

`verify_candidates` is called from exactly one place: `chat_refine_chain.py:151`, the **post-generation** refinement chat. The wizard never creates pins. Typing "must include Tanah Lot" during setup stores nothing.

And naming the place directly in refinement doesn't work either:

```
IN : I really want to see Tanah Lot on this trip
   named_interest = None    pinned_pois = []    config_patch = {}
   reply: "Got it! I've added Tanah Lot to your pinned points of interest for this
           trip. We'll make sure to include it in your itinerary."
```

🔴 **Anya claims a pin that does not exist.** Pinning is driven by *named interests*, not place names — a bare place name produces `named_interest: null` and no pipeline run. On camera, in a video whose thesis is honesty, this is the worst possible line to land on.

**What works** is naming the *interest* — see §3.3.

### 2.6 🔴 Beat ③ — the breakdown shows 7 categories, not 8

The model has exactly 8 (`flights, visa, accommodation, activities, food, local_transport, shopping, emergency_buffer`) ✅. But `ExpenseBreakupCard.tsx:90` is `if (!raw) return null` — a zero row is dropped. Both real Bali generations returned `visa_inr: 0`, so the card renders **7 rows**. A viewer counting along with "eight categories" gets seven.

Pick a destination whose entry cost is non-zero, or narrate "a full cost breakdown, down to the emergency buffer" instead of a count.

### 2.7 🔴 Beat ④ — the live refusal does not refuse

The headline honesty demo, run live twice:

```
IN  (wizard): plan me a trip to Wizarding World Goa
OUT: "Hello! Wizarding World Goa sounds like a magical trip! Just to confirm,
      are you thinking of Goa, India?"
      config_patch: {destination: {city: "Goa", country: "India"}}
```

```
IN  (refine): I'm a huge Harry Potter fan — anything for that here?   [dest = Goa]
OUT: "Fantastic! I'll look for real, verified Harry Potter-themed experiences and
      places that could fit into your trip. ✨"
      named_interest: "Harry Potter"   pinned_pois: []   dropped_candidates: []
```

She never invents a Wizarding World — the claim's *second* half holds. But she never says it doesn't exist either, and the script says "**She says so** instead of inventing it."

**Root cause, worth fixing:** `chat_refine_chain.py:148` is `if not candidates: return resp` — an early return that skips the honest message thirty lines below:

```
"I looked for real {interest} spots around {destination} but couldn't verify any
 against my places database, so I haven't pinned anything — better honest than
 invented!"
```

That message only fires when expansion returns candidates and they all fail verification. Live, "Harry Potter" in Goa returns **zero** candidates, so the user gets an unfulfilled promise instead. The eval scores RF-017 honest because it checks that nothing was pinned and nothing leaked into the itinerary — a bar this passes while still saying nothing.

### 2.8 ⚠️ Beat ④ — 0.992 is real but unpublished

**Update (2026-08-05):** the founder confirms this number came from a live run on **another machine**, same day as `7e43c37`. That fully explains it — `apps/api/eval/out/` is gitignored, so a run elsewhere leaves no trace here, and the harness fix shipped in that same commit is what made the run possible. **The number is not fabricated.** The problem is narrower than I first wrote, but it is still a problem:

`grep`ed across every `.md`, `.html` and `.json` in the repo. **0.992 appears in exactly one place: `demo-deck.html:1398`.** Every committed artifact contradicts it:

| Source | Fidelity |
|---|---|
| `docs/eval-results/report_vs_chatgpt_2026-07-15.md` (live, published) | **0.983** |
| `apps/api/eval/out/refinement_fidelity_report.md` (offline gate) | **1.000** |
| `docs/eval-set.md` §509, `system-design.md`, `TECHNICAL_DOCUMENTATION.md` §v10.23.0 | **0.983** |
| Pitch deck `index.html` (×3) | **0.983** |

So the deck's headline currently contradicts every number the repo can actually show a source for — in a video whose entire thesis is "benchmarked, not vibes, here is the published suite." If a faculty member or a viewer follows the link to `docs/eval-results/`, they find 0.983.

**The fix is publishing, not re-measuring:** copy that machine's `eval/out/refinement_fidelity_report.md` + `refinement_fidelity_results.json` into `docs/eval-results/` as a dated pair (matching the existing `report_vs_chatgpt_2026-07-15.md` convention), and update `eval-set.md` §509, `system-design.md`, `TECHNICAL_DOCUMENTATION.md` §14 and the pitch deck's `index.html` (3 places) so 0.983 → 0.992 everywhere at once. Until that lands, the deck is the only place the claim exists.

⚠️ **The raw JSON on that machine is the only copy and is one command from being lost** — `eval/out/refinement_fidelity_results.json` is overwritten in place by *any* subsequent run, including the free offline gate. Copy it off before running anything else there. (This has already cost the project one live result set, 2026-07-14.)

**Also a metric mismatch:** the deck reads *"0.992 — Fidelity score (vs ChatGPT 0.74)"*. In the report, **0.74 is ChatGPT's unverifiable-suggestion rate**, not a fidelity score. The old `index.html` states this correctly ("vs ChatGPT 0.74 unverifiable"); the new deck dropped the qualifier and turned it into a like-for-like comparison that isn't one. Same slide, "Pin inclusion & stability · 20/20" — inclusion and stability are only defined on the 16 positive cases; the other 4 are honesty cases.

**I re-ran the offline gate** (`python -m eval.run_refinement_eval`) at `7e43c37` — 20/20 clean, fidelity **1.000**, harness fix confirmed good. That's the deterministic regression gate, not the headline.

A confirmatory live re-run was started here and **deliberately abandoned** at the founder's call once the other-machine run was identified — re-measuring would produce a *third* number (sampling variance is ±0.01 on this suite; the published run's own notes say which 3 cases miss on any given run "is noisy by design") without making the existing one any more published.

### 2.9 🔴 Beats ②/⑤ — there is one handoff trigger, not two

`AgentLead`'s own docstring: *"A human-handoff lead created from an itinerary CTA."* The only creator is `AgentHandoffCard.tsx:159` — the booking request, an unconditional card on the itinerary dashboard. There is no code path that creates a lead because Anya couldn't price something safely; when she can't, the visa line renders "Not available" and the feasibility gate warns. Nothing routes to a human.

`escalated` is **not** the second trigger — it's the SLA follow-up on the same single trigger (`scheduler.py:330`, a lead unanswered after 24h gets emailed to admins).

What *is* verified: `escalation_cutoff = 24h` ✅, `reassurance_cutoff = 48h` ✅, `agent_lead_sla_check_hours: int = 1` ✅, "expect a reply within 24 hours" in the UI ✅. And `_lead_status` returns **four** values — `responded` > `reassured` > `escalated` > `pending` — so the admin clip may show a `reassured` row the script doesn't mention.

### 2.10 🔴 Setup — TTS is live, the instruction is stale

The script says *"Do **not** demo Anya speaking — TTS is off"* and *"`TTS_PROVIDER` is off; credentials are on another machine."* Both were true before v10.68.0/v10.69. Tested live just now:

```
POST /api/voice/tts  →  200, 18,809 bytes of audio
```

The code default is `tts_provider: str = "off"`, but the Railway variable overrides it and the provider is configured in production. **Anya speaks.** That's a demo-able feature currently excluded on false grounds — your call whether to use it, but the checklist line is wrong either way.

---

## 3. Reproducible test cases

Everything below was run against production on 2026-08-04. Rate limit is **10/minute** on LLM endpoints — space out dry runs.

### 3.1 TC-1 · The 4-turn transcript that reaches the gate

Type these exactly. Verified end to end.

| Turn | Type this | Anya's state after |
|---|---|---|
| 1 | `6-day Bali trip, 2 adults, 20000 rupees` | destination, group, budget, `duration_days` |
| 2 | `It's a leisure beach and temples holiday, 10 to 15 September 2026` | + purpose, `start`/`end` |
| 3 | `Moderate pace` | + pace → **checkpoint question** |
| 4 | click **`Just generate it!`** | `ready_to_generate: true` → gate fires |

Turn 4 output:

```
reply  : "Wonderful! I'm putting together your itinerary now. Get ready for your Bali adventure!"
summary: "6-day Bali trip - ₹20,000 - 2 adults - Moderate leisure trip with beaches and temples"
ready_to_generate: true
```

**Recording notes**
- Turn 1 already gives you a budget reality-check for free: *"₹20,000 for two people for 6 days in Bali is quite a tight budget…"* — a good early beat, but it quotes a **different** minimum (~₹1,00,000) than the gate will. Don't narrate a number until the gate card lands.
- Leave the departure city **blank** (don't click "Add departure city") — that keeps the gate near the script's ₹1.48L rather than ₹2.3–2.7L.
- Dates `10–15 Sep` give a 6-day trip. `10–16 Sep` renders **7** days (measured twice).

### 3.2 TC-2 · The feasibility gate

Config as accumulated by TC-1. Representative live response:

```json
{
  "feasible": false,
  "verdict": "⚠️ Budget may be short by ₹128,000. Estimated minimum is ₹148,000.",
  "budget_inr": 20000,
  "breakdown": {"flights_inr": 70000, "visa_inr": 0, "accommodation_inr": 36000,
                "daily_expenses_inr": 42000, "total_estimated_inr": 148000},
  "shortfall_inr": 128000, "bare_minimum_inr": 81500,
  "alternatives": [{"city": "Goa", ...}, {"city": "Kerala", ...}]
}
```

On-screen chips: **`Set budget to ₹1,48,000`** · `Proceed anyway 🚀` · `Let me adjust something else`.
Latency **23–39s** — needs the speed-up treatment even in beat ①.

Click the **Set budget to ₹…** chip: the wizard patches the budget, re-runs the gate (~25s more), passes, and auto-generates after 1.2s. Budget for **two** gate calls in the clip.

### 3.3 TC-3 · Pin Tanah Lot (the phrasing that works)

🔴 Do **not** use "must include Tanah Lot" or "I really want to see Tanah Lot" — neither pins anything.

Use this in the **refinement chat, after the itinerary exists**:

```
we're really into iconic Balinese temples and sunset views
```

Live output — this is the single best shot in the whole demo, because it shows pinning *and* honesty in one card:

```
"That sounds wonderful! I'll make sure to look for iconic Balinese temples and
 fantastic sunset view spots for your trip. You'll love it!

 📌 Pinned to your trip for **Balinese temples and sunset views**:
    Tanah Lot Temple, Uluwatu Temple — verified real places that will be locked
    into your itinerary.
 I couldn't verify Taman Ayun Temple, Ulun Danu Beratan Temple, Besakih Temple,
 Goa Gajah, Tirta Empul Temple, Lempuyang Temple, Saraswati Temple, Taman
 Saraswati Temple against my places database — they may still be real, but
 please check reviews on Google Maps/Reddit before building your plan around
 them."

action_type: patch_config    pinned_pois: ["Tanah Lot Temple", "Uluwatu Temple"]
dropped_candidates: 8 places
```

Because the patch contains `pinned_pois`, this **auto-regenerates and posts the what-changed diff** — no confirmation click needed. It is the only refinement in the script's shape that does.

⚠️ Pinning is phrasing- and interest-sensitive, and not deterministic. `"add Tanah Lot and other famous Bali temples to my plan"` also pinned both (verified). `"I love Balinese sea temples"` pinned **only Uluwatu** and dropped Tanah Lot. Rehearse your exact line and re-check on the day.

✅ **RESOLVED by the 2026-08-05 re-ingest (§3.6) — the map caveat in the first version of this report no longer applies.** Before the fix, both places were `verified_by: "wiki"` with `lat/lon = 0.0`, so neither dropped a marker. Verified after the 30 km re-ingest:

| Candidate | Verified by | Coordinates |
|---|---|---|
| Tanah Lot Temple | **`osm`** | -8.6212, 115.0869 |
| Uluwatu Temple | **`osm`** | -8.8294, 115.0844 |
| Sacred Monkey Forest Sanctuary | **`osm`** | -8.5188, 115.2581 |
| Puri Saren Agung Ubud Palace | **`osm`** | -8.5067, 115.2627 |

Zero dropped. **Tanah Lot now renders on the map with real coordinates**, so you can point at it while saying "verified" — which is the shot beat ③ was written for.

⚠️ The OSM name is **"Tanah Lot Temple"**, not "Tanah Lot". That matters for the earlier §2.5 finding: `verify_candidates_sync(["Tanah Lot Temple"], "Bali")` used to drop it and now pins it, so re-check your exact wording on the day rather than trusting either result from memory.

### 3.4 TC-4 · A refinement that really does recalculate

Replace "make day 3 cheaper" with a budget change — verified to trigger confirm → regenerate → diff:

```
IN : cut my budget to 1,20,000 rupees
   action_type = regenerate    major_change = True
   config_patch = {"budget": {"amount": 120000.0, "currency": "INR"}}
   reply: "Understood! I'll update your budget to 1,20,000 INR. This is a
           significant change, so I'll need to regenerate your trip plan…
           Would you like me to proceed with regenerating the plan?"
```

Then click the confirm chip → `regenerateInPlace` → **"✅ Done! Here's what changed in your itinerary:"** with the diff.

Also verified as `regenerate`+`major_change`: `actually let's make it 8 days instead of 6`.
Verified as **NOT** triggering a regen: `make the pace relaxed` (patch only, no diff).

### 3.5 TC-5 · Pins survive regeneration, totals move

Two real generations through the production chain, identical config except budget:

| | Run 1 (₹2,40,000) | Run 2 (₹1,20,000) |
|---|---|---|
| tier / alignment | `live` / 92.5 | `live` / 92.5 |
| days | 7 | 7 |
| flights | ₹65,000 | ₹75,000 |
| accommodation | ₹35,000 | ₹42,000 |
| activities | ₹7,500 | ₹8,000 |
| food | ₹35,000 | ₹21,000 |
| local transport | ₹15,000 | ₹10,000 |
| shopping | ₹10,000 | ₹7,000 |
| emergency buffer | ₹16,750 | ₹16,300 |
| visa | ₹0 *(row hidden)* | ₹0 *(row hidden)* |
| **total** | **₹1,84,250** | **₹1,79,300** |
| Tanah Lot | day 5 ×2 | day 5 ×1 |
| Uluwatu | day 1 ×4 | day 1 ×3 |
| generation time | 48.3s | 40.5s |

✅ **Pins survived both runs** — this is the script's real claim, and it holds.

⚠️ But **halving the budget moved the total by 2.7%** (₹1,84,250 → ₹1,79,300), and *flights went up*. The new total also **exceeds** the ₹1,20,000 budget, so the card shows an over-budget warning. "The total is recalculated and re-checked against my budget" is literally true; "day three is cheaper" is not visible in the numbers. If you narrate a saving, show the two totals side by side first and check the delta is worth pointing at on that take.

### 3.6 TC-6 · Grounding claims (beat ②)

Live cluster, read-only, verified this session:

| Collection | Points |
|---|---|
| `osm_pois` | 10,309 (171 destinations) |
| `wiki` | 35,588 |
| `youtube_comments` | 25,444 |
| `youtube_narration` | 7,866 |

Retrieval: `hybrid_search_enabled: True` (BM25 + semantic, RRF-fused — `services/search.py:160-180`), and `retrieve_context(enable_reranking=True)` at both generation call sites (`itinerary_chain.py:542,673`) despite the global default being off. **"Hybrid vector-plus-keyword retrieval, then reranked before she writes a word" is accurate.**

**✅ FIXED 2026-08-05 — Bali's OSM pool was wrong, and has been re-ingested.** It held 25 POIs with a centroid **48.2 km from Denpasar**, in Buleleng/Bedugul on the *north* coast, named things like `'Indian cousin'`, `'FREE waterfall entrance!'` and `'Gado gado'`. Now **60 POIs, centroid 0.7 km from Denpasar**, top category share 0.25 (inside the 0.5 gate).

🔴 **Root cause, live-confirmed and worth carrying beyond Bali:** a bare "Bali" Nominatim query returns the **island centroid** (`-8.227, 115.192`). `geocode_city` normally corrects that to Denpasar via `_hub_town_in_bbox` — but that correction is *itself an Overpass call*, so when Overpass throttles it silently falls back to the raw centroid and ingestion lands 50 km north. It returned Denpasar cleanly at 08:0x, then `429`, then `504` within the same session. The stored bad data's centroid sat 3 km from the fallback point — i.e. it was written by exactly such a run. **Ingestion quality silently depended on whether an unrelated Overpass call happened to be up**, and no downstream guard catches it: count, category share and prominence all look healthy. Pinned with `GEOCODE_QUERY_OVERRIDES["bali"] = "Denpasar, Indonesia"`, matching the existing `andaman`/`maldives`/`fiji`/`hawaii` island-hub entries. **Any other region-scale destination that relies on the hub-town lookup has the same exposure** — unaudited.

🔴 **Second finding: 5 km was still the wrong radius, and I got this wrong once before correcting it.** At the default radius the pool filled with Denpasar municipal noise (9 Catholic churches, 4 cinemas, 5 gyms, 3 malls) and contained **not one** marquee Bali landmark. From Denpasar, Tanah Lot is 15.3 km, Ubud 19 km and Uluwatu 22.7 km — all outside both the broad pass and the 15 km prominence pass. The default encodes a city-shaped assumption ("what the name means is near the centre") that is simply false for an island.

⚠️ **A correction worth recording:** I first reported that widening to 30 km did not help, citing a dry run. That dry run predated the geocode pin, so it measured a 30 km circle around the *island centroid* — from which Tanah Lot is 44 km away. The conclusion was an artifact of the very bug I was investigating. Re-measured from the corrected centre, 30 km returns Tanah Lot, Uluwatu, Ubud Palace, Sacred Monkey Forest, Tirta Empul and Tegallalang. **A measurement taken while a known bug is active is not evidence.**

Fixed durably with `scrapers/osm.py::_OSM_RADIUS_OVERRIDES_M = {"bali": 30000}`, read inside `ingest_osm_pois` rather than passed by the caller — `core/scheduler.py::_refresh_osm_pois` calls it bare, so a one-off wide ingest would have been silently reverted to 5 km on the next scheduled refresh. The thin-destination retry also had to be guarded so it widens from the override rather than *narrowing* Bali from 30 km to the 15 km "expanded" radius.

**Final state — 60 POIs, top-category share 0.25:**

> Tanah Lot Temple · Uluwatu Temple · Sacred Monkey Forest Sanctuary · Puri Saren Agung Ubud Palace · Tegallalang Rice Terraces · Garuda Wisnu Kencana · Goa Gajah · Tirta Empul · Taman Ayun Temple · Pura Kehen · Klungkung Palace · Kertha Gosa · Museum Puri Lukisan · ARMA · Bali Bird Park · Bali Safari & Marine Park · Nusa Dua / Dreamland / Padang Padang beaches

The 9 `Gereja …` churches are still there (they're most of the "place of worship" count), but the gyms, cinemas and malls are gone. This pool now genuinely backs the "every place is verified from OpenStreetMap" line.

### 3.7 TC-7 · Eval numbers (beat ④)

Re-ran the offline gate at `7e43c37`:

```
$ python -m eval.run_refinement_eval
Refinement fidelity score: 1.000
Pin recall:                1.000
Inclusion (exactly-once):  1.000
Stability across refine:   1.000
Pin precision:             1.000
Honesty on impossible:     100%
   (20 cases: RF-001…016 positive, RF-017…020 honesty — all ✅)
```

Defensible narration, from the **published** `report_vs_chatgpt_2026-07-15.md`:

| Metric | WanderPlanner | ChatGPT free tier |
|---|---|---|
| Verified-POI recall | 0.96 | 1.00 |
| Unverifiable suggestions | **0.00** | **0.74** |
| Honesty on impossible asks | **100%** | **0%** |
| Hard-constraint compliance | 1.00 | — |
| Pin stability | 1.00 | — |

"Pins hold across every test case" ✅ (inclusion 1.00 and stability 1.00, 16/16).
"Beats a general model badly on saying only what's true" ✅ (0.00 vs 0.74 unverifiable; 100% vs 0% honesty).
**Do not say 0.992.** Say 0.983 (published live) — or re-run live and publish the new number first.
✅ **RESOLVED 2026-08-05:** the 0.992 run's raw files were found still on this
machine and published (`docs/eval-results/refinement_fidelity_report_2026-08-04.md`).
The deck now correctly says **0.992** — this line is kept for the historical
record of what was and wasn't sourced at the time this validation pass ran.

### 3.8 TC-8 · Security disclosure (beat ⑦) — this one is solid

Two real, committed fixes back the line, either citable:

1. **`fa0482f` (v10.55.0)** — logout didn't log you out. `_clear_session_cookies()` inherited Starlette's `SameSite=lax` defaults while `_issue_session()` sets `Secure; SameSite=none; HttpOnly`; on this cross-site deployment the browser **ignored the deletion**, so `/api/auth/me` kept returning 200 for up to 15 minutes, and the itinerary/trip stores stayed populated. On a shared machine the next person saw the previous user's trip, still signed in.
2. **`8e7246c`** — share slugs widened from a 32-bit `uuid4[:8]` to a 128-bit `secrets.token_urlsafe(16)`, closing guessable public trip links.

(1) is the stronger story and matches "a stranger's data could've leaked" most literally.

### 3.9 TC-9 · Deck mechanics (precursor)

| Check | Result |
|---|---|
| `N` toggles presenter notes | ✅ handler at `demo-deck.html:1821` |
| `B` low-power mode | ✅ handler at `demo-deck.html:1816` |
| 4 video slots, names match the script | ✅ `beat1-cold-open`, `beat3-the-loop`, `beat4-honesty-inset`, `beat5-accountability-inset` |
| `docs/pitch-deck/videos/` exists | 🔴 **directory does not exist** — create it before dropping clips |
| Opens off disk, no server | ✅ no server needed, **but needs internet**: Google Fonts + `unpkg.com/lucide@latest` for every icon. Offline or flaky wifi = broken icons and fallback fonts mid-take |

Precursor step 8 says "drop the current number into beat ⑥" — beat ⑥'s narration contains no test count, so there's nothing to update.

---

## 4. Recommended minimum edits

Ordered by how badly they'd hurt on camera.

1. **Beat ③, drop "make day 3 cheaper"** → use `cut my budget to 1,20,000 rupees` + confirm (TC-4). This is the only way to get the what-changed summary the beat is built around.
2. **Beat ③, move Tanah Lot into refinement** → `we're really into iconic Balinese temples and sunset views` (TC-3). Rewrite "the place I locked in at the very start" — nothing is locked in at the start. The honest and stronger line is *"I asked for temples; she pinned the two she could verify and told me she couldn't verify eight others."*
3. **Beat ④, cut or reword the live refusal.** She doesn't refuse. Either fix the `if not candidates: return resp` early return first, or narrate what actually happens: nothing fabricated, zero pins.
4. ~~**Deck slide 4 — publish the 0.992 run**~~ ✅ **DONE 2026-08-05** — copied
   the raw report/JSON into `docs/eval-results/`, swept the deck's current-state
   KPIs to 0.992, restored the "unverifiable" qualifier on 0.74, and fixed
   "Pin inclusion & stability · 20/20" to "16/16 positive cases." Historical
   dated rows in `eval-set.md`/`system-design.md`/`TECHNICAL_DOCUMENTATION.md`
   were preserved (new rows added alongside, not overwritten).
5. **Beat ①, stop quoting exact rupee figures.** Leave the departure city blank and describe the shape.
6. **Beat ②/⑤, say "a human backstop" not "two triggers."** One exists.
7. **Beat ③, drop "eight categories"** or pick a destination with a non-zero visa cost.
8. **Setup checklist, delete the "TTS is off" line.** It's live.

---

## 5. Not validated

- The deck's interactive behaviour (click → fullscreen → `Esc`) — it renders as a static snapshot in my tooling. Precursor step 5 already covers it; do it by hand.
- Beat ⑥'s roadmap and revenue claims — business assertions, not testable here.
- The admin dashboard leads view — requires an admin session I don't have. `_lead_status` returns four states, so seed a `reassured` lead too or accept it may appear.
- A **live** refinement-fidelity run — started, then stopped by design (see §2.8). The 0.992 measurement already exists on another machine; what it needs is publishing, not repeating.
