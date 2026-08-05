# WanderPlanner — 4:00 Product Review Video

**Recording script v3.** Agentic AI PRD Cohort 10 · Kunal Mathur

Total ~465 spoken words · target 3:22 spoken, 4:00 wall-clock exactly (the gap is demo silence in beat ③, and it is deliberate — do not fill it).

**v3 changes:** synced timings/word counts to the rebuilt `demo-deck.html` (presenter notes hidden by default, real video-slot playback, click-to-fullscreen), wrote the final trimmed wording for beats ⑤ and ⑥, and added the live-URL call-out to the close so the video explicitly tells people this is deployed — not a localhost demo — and invites them to try it.

**Rule while cutting:** if you run long, take it out of beats ② and ⑤. Never out of ③.

---

## Precursor — dry run before you hit record

Do this once, start to finish, *before* your take. It exists because the deck changed shape recently (single-screen, embedded video slots, a hidden presenter-notes layer) and a few things will silently ruin a take if you skip them.

1. **Open `docs/pitch-deck/demo-deck.html` straight in Chrome** (double-click / `open`) — no local server needed, video loads off disk.
2. **Presenter notes must be OFF before recording.** Press `N` once to preview each slide's notes (beat, timing, screen directions) during rehearsal — then press `N` again to hide them. The commentary/timestamps must never be visible on the recorded slide itself.
3. **Pick low-power mode (`B`) once, before recording, and leave it alone.** Toggling mid-take is visible. Use dynamic (default) unless the recording machine is struggling.
4. **Drop the 4 clips into `docs/pitch-deck/videos/`** named exactly `beat1-cold-open.mp4`, `beat3-the-loop.mp4`, `beat4-honesty-inset.mp4`, `beat5-accountability-inset.mp4`. A slot shows a "Click for fullscreen" hint on hover once it's correctly detected — confirm all 4 do before recording.
   - **Record these clips on desktop, not mobile.** The deck is 16:9 landscape; a portrait phone recording will letterbox or crop badly when it goes fullscreen. Capture at 1920×1080 in a normal desktop browser window (if a responsive/mobile view matters, demo it via the browser's device toolbar rather than an actual phone).
   - **Record silent** — no voiceover, mic off. Your narration is done live, once, over the whole deck; a clip with its own voice track will overlap or clash with your take.
   - Trim each clip to roughly the beat's allotted runtime so it doesn't run long while you're narrating over it.
5. **Click-test every video slot once**, full dry run: click → fullscreen + audio unmutes + plays from 0:00 → press `Esc` → back to the deck at the same slide. Confirm your screen-recorder captures the *whole display*, not just the browser window — fullscreen video will cover the entire screen, outside the browser chrome.
6. **Unmute your system audio before recording.** Clips sit muted until fullscreen is triggered by click; if system audio is muted at the OS level, the unmute-on-click won't produce sound in the recording.
7. Have `wanderplanner.org` reachable (not `localhost`) — you're about to tell viewers this is live; don't let the actual demo run off a local dev server while saying that.
8. Re-run the suite once and drop the current number into beat ⑥ if the corpus/test count changed since this script was last verified.
9. Practise beat ③ twice, start to finish, with no pauses to think — it's the one continuous take with the hard "never cut from here" rule.

---

## Setup before you hit record

- [ ] Signed in, on a clean browser profile, no bookmarks bar, no notifications
- [ ] `demo-deck.html` open, presenter notes (`N`) confirmed OFF, low-power mode (`B`) set and left alone
- [ ] All 4 video slots confirmed playing on click (see Precursor step 5)
- [ ] Admin dashboard clip (`beat5-accountability-inset.mp4`) captured on the leads view, with **at least one lead in each state** (pending / escalated / responded) so the column isn't empty
- [ ] `wanderplanner.org` open and reachable — this is the live deploy, not localhost
- [ ] Rehearsed beat ① as **four turns** (§3.1 of `demo-script-validation.md`), leaving departure city blank
- [ ] Anya's voice is LIVE in production (v10.68/69) — the old "TTS is off" note was stale.
      Still out of this cut for time, but it is available if you want it
- [ ] Beat ③ is one continuous take. Practise it twice before recording.

---

## ① 0:00–0:22 · Cold open — the gate

> **SCREEN:** Live app (wanderplanner.org). No intro card, no logo. Cursor already in Anya's chat.
>
> ⚠️ **The gate needs four turns, not one** — it only fires once all six required
> fields are in and you confirm. Verified transcript (`docs/demo-script-validation.md` §3.1):
>
> | Turn | Type |
> |---|---|
> | 1 | `6-day Bali trip, 2 adults, 20000 rupees` |
> | 2 | `It's a leisure beach and temples holiday, 10 to 15 September 2026` |
> | 3 | `Moderate pace` |
> | 4 | click **`Just generate it!`** |
>
> Speed the clip up through turns 1–3; land at normal speed on the gate.
> **Do not click "Add departure city"** — with origin blank the minimum lands near
> ₹1.5L; supplying one roughly doubles it and breaks the next beat's arithmetic.
> Let the feasibility gate render. Hold on the shortfall.

**SAY** *(45 words)*

This is a real budget on a real trip. Six days in Bali, two adults, twenty thousand rupees.

Watch what Anya does *before* she plans anything.

*(beat — let the gate land)*

She stops. The realistic minimum is around a lakh and a half — against a budget of twenty thousand.

> 🔴 **Read the shortfall off the screen; do not pre-script the digits.** This
> figure is LLM-generated at temperature 0.2. Five live runs of the identical
> trip returned ₹1.48L / ₹2.33L / ₹2.36L / ₹2.68L / ₹2.74L, and the visa line
> flips between a real figure and "not available" between runs.

---

## ② 0:22–0:48 · What Anya actually is

> **SCREEN:** Deck slide 2 — solution overview (WanderPlanner / Anya / RAG / handoff).

**SAY** *(56 words)*

I'm Kunal Mathur. Anya is WanderPlanner's planning agent — and she isn't a chatbot guessing from general knowledge.

Every answer is grounded in a verified corpus: OpenStreetMap, Wikivoyage, YouTube signal, pulled through hybrid vector-plus-keyword retrieval, then reranked before she ever writes a word.

And when she can't safely price something, she doesn't guess — she says so, and there's a human backstop behind her. Me.

---

## ③ 0:48–2:08 · The loop, one unbroken session

> **SCREEN:** Same session throughout. No cuts, no new tabs, no reloads.
>
> | At | Do |
> |---|---|
> | 0:48 | Click the **`Set budget to ₹…`** chip (the app supplies the figure — do not type your own) → Proceed |
> | 0:55 | Itinerary streams. **Visible "×4" speed label on screen** (an editing overlay — the app has no such label; generation really takes 40–50s) |
> | 1:18 | Scroll to the cost breakdown. Rest on it |
> | 1:28 | In Anya's chat, type `we're really into iconic Balinese temples and sunset views` |
> | 1:36 | Pin card lands: **Tanah Lot Temple + Uluwatu Temple pinned**, eight others honestly listed as unverified. Itinerary auto-rebuilds |
> | 1:50 | Type `make day 3 cheaper` |
> | 1:58 | What-changed summary. **Highlight Tanah Lot still present.** Point at day 3's lowered cost and the recalculated total |

**SAY** *(142 words)*

The gate isn't a dead end — it's a fork. Raise the budget, and she plans.

Every place here is verified from OpenStreetMap and Wikivoyage. She will not invent one.

*(over the stream)* Day by day, with a map, and a full cost breakdown — right down to the emergency buffer.

> ⚠️ **Do not say "eight categories."** The card hides any zero row, and Bali's
> visa cost is ₹0, so seven render. A viewer counting along catches it.

*(let it finish — silence is fine here)*

*(type: we're really into iconic Balinese temples and sunset views)*

I asked for temples. She pinned the two she could verify against OpenStreetMap — and told me, unprompted, about eight more she couldn't. That list is the product.

*(type: make day 3 cheaper)*

Day three is cheaper. But look — Tanah Lot is still there. She can't quietly drop a commitment to hit a number.

And the total is recalculated and re-checked against my budget, not left stale.

---

## ④ 2:08–2:38 · Benchmarked, not vibes — and one honest refusal

> **SCREEN:** Deck slide 4 — eval-suite numbers, with a small inset video slot (`beat4-honesty-inset`) showing the live refusal in the corner while the numbers hold the main frame.
> Inset action: type `plan me a trip to Wizarding World Goa` and show the refusal.
> **On-screen only, not voiced:** each KPI now has a short caption underneath (Fidelity/Pin inclusion/Honesty) explaining what it means in a few words — left silent deliberately so it doesn't compete with the 47-word VO below; let it sit on screen for the viewer to read.

**SAY** *(47 words)*

Budget reasoning is benchmarked, not vibes — pins hold across every test case, and she beats a general model badly on saying only what's true.

And the same honesty standard applies to destinations, live: there's no Wizarding World in Goa. She says so instead of inventing it.

---

## ⑤ 2:38–2:58 · Who's accountable, and what's not real yet

> **SCREEN:** Deck slide 5 — merged accountability + honest-gap card, with a small inset video slot (`beat5-accountability-inset`) of the admin dashboard leads view (status column: pending / escalated / responded).

**SAY** *(37 words)*

Once you've liked the plan, a booking request routes to a local expert — tracked on a twenty-four-hour SLA, with escalation if nobody answers. What isn't real yet: live airline and hotel prices, not just estimates.

---

## ⑥ 2:58–3:24 · The launch plan, and how it makes money

> **SCREEN:** Deck slide 6 — roadmap + revenue ledger.

**SAY** *(36 words)*

Phase one is shipped, live at wanderplanner dot org. Phase two, next six months: bring on paying local travel agencies.

Cost per itinerary is a fraction of a cent — margins hold comfortably even at scale.

---

## ⑦ 3:24–4:00 · Close — and it's live, go try it

> **SCREEN:** Deck slide 7 — closing manifesto, with the `wanderplanner.org` live badge visible.

**SAY** *(64 words)*

This isn't running on my laptop — it's live, right now, at wanderplanner dot org. Go try it yourself.

Before you try this, one honest note: I went looking for ways it could put your data at risk — found a spot where a stranger's data could've leaked, and closed it, so you don't have to wonder.

Wanderplanner. Real budgets. Real places. Real plans.

---

## Deliberately still not in this script

| Left out | Why |
|---|---|
| Anya speaking aloud | Works in production as of v10.68/69 (verified: `/api/voice/tts` returns real audio) — left out for time, not capability |
| Signup / login flow | Dead screen time |
| PDF export, share link, booking click-through | One clause each at most; not shots |
| Full test suite scrolling past | Faculty: "the honesty is what makes it credible, not the pass counts" |
| Fundraise ask / moat / TAM slides | Investor deck material, not this rubric — launch plan + revenue math stayed, the pitch framing didn't |
| Separate honesty-guard and accountability demos as standalone beats | Folded into ④ and ⑤ as insets so the overview + launch/revenue beats fit in 4:00 |
