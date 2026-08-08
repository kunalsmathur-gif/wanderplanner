# WanderPlanner — Voiceover Read Script

**Read-aloud only.** Screen directions, shot tables and timing notes live in
`docs/video-script-4min.md` — this file is what you actually speak.

~420 words · **3:20 spoken over a 4:00 wall clock.** The 40-second gap is
demo silence in beat ③ and it is deliberate. Do not fill it.

**Bold** = land on this word. `[...]` = do not speak, it's a cue.

---

## ① 0:00 – 0:22 · Cold open

This is a real budget on a real trip. Six days in Bali, two adults, twenty
thousand rupees.

Watch what Anya does **before** she plans anything.

`[pause — let the gate render]`

She stops. The realistic minimum is **many times** that — and she says so
before writing a single day.

> ⚠️ Do not name the shortfall figure. It is LLM-generated at temperature
> 0.2 and five live runs of this identical trip returned ₹1.48L, ₹2.33L,
> ₹2.36L, ₹2.68L and ₹2.74L. Any number you pre-script will contradict the
> screen four times out of five. "Many times that" is true against all of
> them. If you want to name it, read it off the screen live.

---

## ② 0:22 – 0:48 · What Anya actually is

I'm Kunal Mathur. Anya is WanderPlanner's planning agent — and she isn't a
chatbot guessing from general knowledge.

Every answer is grounded in a verified corpus: OpenStreetMap, Wikivoyage,
YouTube signal, pulled through hybrid vector-plus-keyword retrieval, then
reranked before she ever writes a word.

And when she can't safely price something, she doesn't guess — she says so.
And there's a human backstop behind her. Me.

---

## ③ 0:48 – 2:08 · The loop

> The one continuous beat. If the video runs long, cut from ② and ⑤ — never
> from here.

The gate isn't a dead end — it's a **fork**. Raise the budget, and she plans.

Every place here is verified from OpenStreetMap and Wikivoyage. She will
**not** invent one.

`[over the stream]` Day by day, with a map, and a full cost breakdown —
right down to the emergency buffer.

`[let it finish — silence is fine here]`

I asked for temples. She pinned the two she could verify against
OpenStreetMap — and told me, unprompted, about **a list of others she
couldn't**. That list is the product.

`[pause for the day-3 edit to land]`

Day three is cheaper. But look — **Tanah Lot is still there**. She can't
quietly drop a commitment to hit a number.

And the total is recalculated and re-checked against my budget, not left
stale.

> ⚠️ Two counts not to say aloud. **"Eight categories"** — the cost card
> hides zero rows and Bali's visa is ₹0, so seven render. **"Eight more"**
> for the unverified pins — that count moved after the item-handling change
> and is no longer reliable. A viewer counting along catches both.

---

## ④ 2:08 – 2:38 · Benchmarked, and one honest refusal

Budget reasoning is benchmarked, not vibes — pins hold across every test
case, and she beats a general model badly on saying only what's true.

`[pick the line that matches what your clip actually shows]`

**If the clip shows the destination refusal** ("Wizarding World Goa"):

And the same honesty standard applies to destinations, live: there's no
Wizarding World in Goa. She says so instead of inventing it.

**If the clip shows the Harry Potter interest refusal** (the live-verified
prompt in `demo-script-prompts.md`):

And the same honesty standard applies live: she couldn't verify anything
for that — so she says so, and pins nothing. Better honest than invented.

> The KPI captions on this slide are deliberately unvoiced. Let them sit on
> screen and read themselves.

---

## ⑤ 2:38 – 2:58 · Who's accountable, and what isn't real yet

Once you've liked the plan, a booking request routes to a local expert —
tracked on a **twenty-four-hour SLA**, with escalation if nobody answers.

What isn't real yet: live airline and hotel prices, not just estimates.

---

## ⑥ 2:58 – 3:24 · The launch plan, and how it makes money

Phase one is shipped, live at wanderplanner dot org. Phase two, next six
months: bring on paying local travel agencies.

Cost per itinerary is a fraction of a cent — margins hold comfortably even
at scale.

---

## ⑦ 3:24 – 4:00 · Close

This isn't running on my laptop — it's live, **right now**, at wanderplanner
dot org. Go try it yourself.

Before you try this, one honest note: I went looking for ways it could put
your data at risk — found a spot where a stranger's data could've leaked,
and closed it, so you don't have to wonder.

`[beat]`

Wanderplanner. Real budgets. Real places. Real plans.

---

## Changed from `video-script-4min.md`

Both edits remove a hardcoded number that the screen was likely to
contradict — the same failure the source script already warns about
elsewhere, applied consistently.

| Beat | Was | Now | Why |
|---|---|---|---|
| ① | "around a lakh and a half" | "many times that" | Only 1 of 5 measured live runs landed near ₹1.5L; four returned ₹2.3L+ |
| ③ | "about eight more she couldn't" | "a list of others she couldn't" | The unverified-candidate count shifted when item handling changed to tag-not-remove |
| ④ | one fixed line | two variants | The source script's prompt and the live-verified prompt exercise different refusal paths |

Verified live on 2026-08-08: `wanderplanner.org` serves the app (200), and
`api.wanderplanner.org/health` returns 200 with the correct CORS origin — so
both "live at wanderplanner dot org" claims are safe to say. The source list
in ② is current and correctly omits Reddit, which was dropped as a source.
