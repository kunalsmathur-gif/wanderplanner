# WanderPlanner — 4:00 Product Review Video

**Recording script.** Agentic AI PRD Cohort 10 · Kunal Mathur

Total ~535 spoken words · target 3:45 spoken, 4:00 wall-clock (the gap is demo silence, and it is deliberate — do not fill it).

**Rule while cutting:** if you run long, take it out of beats ② and ⑦. Never out of ③.

---

## Setup before you hit record

- [ ] Signed in, on a clean browser profile, no bookmarks bar, no notifications
- [ ] Two slides open in tabs: pitch deck `04 / 15` and `06 / 15`, plus `slide-real-vs-next.html`, plus deck `15 / 15`
- [ ] Admin dashboard open on the leads view, with **at least one lead in each state** (pending / escalated / responded) so the column isn't empty
- [ ] Re-run the suite and confirm the number in beat ⑦: `venv/Scripts/python.exe -m pytest tests/unit -q`
- [ ] Do **not** demo Anya speaking — TTS is off
- [ ] Beat ③ is one continuous take. Practise it twice before recording.

---

## ① 0:00–0:22 · Cold open — the gate

> **SCREEN:** Live app. No intro card, no logo. Cursor already in Anya's chat.
> Type or speak: `6-day Bali trip, 2 adults, ₹20,000, must include Tanah Lot`
> Let the feasibility gate render. Hold on the shortfall.

**SAY** *(45 words)*

This is a real budget on a real trip. Six days in Bali, two adults, twenty thousand rupees.

Watch what Anya does *before* she plans anything.

*(beat — let the gate land)*

She stops. Realistic minimum: one lakh forty-six thousand. You're short by one lakh twenty-six.

---

## ② 0:22–0:45 · Who, and why that matters

> **SCREEN:** Cut to deck **slide 04 / 15** ("5+ tabs, 0 certainty").
> Cut back to the frozen shortfall on the final sentence.

**SAY** *(58 words)*

I'm Kunal Mathur, and that refusal is the product.

Every other planner writes you a beautiful itinerary and prices it afterwards — or never. Indian travellers don't plan that way. They start with a number: six days, family of four, under a lakh.

Today they burn hours across five tabs and still don't know if the number is real.

---

## ③ 0:45–2:05 · The loop, one unbroken session

> **SCREEN:** Same session throughout. No cuts, no new tabs, no reloads.
>
> | At | Do |
> |---|---|
> | 0:45 | Click **Raise budget** → ₹1,60,000 → Proceed |
> | 0:52 | Itinerary streams. **Visible "×4" speed label on screen** |
> | 1:15 | Scroll to the 8-category cost breakdown. Rest on it |
> | 1:25 | Type `make day 3 cheaper` |
> | 1:40 | What-changed summary. **Highlight Tanah Lot still present.** Point at the recalculated total |

**SAY** *(142 words)*

The gate isn't a dead end — it's a fork. Raise the budget, and she plans.

Every place here is verified from OpenStreetMap and Wikipedia. She will not invent one.

*(over the stream)* Day by day, with a map, and a full cost breakdown across eight categories.

*(let it finish — silence is fine here)*

Now I'll change my mind, the way anyone would.

*(type: make day 3 cheaper)*

Day three is cheaper. But look at Tanah Lot — the place I locked in at the very start is still there. She can't quietly drop a commitment to hit a number.

And the total is recalculated and re-checked against my budget, not left stale.

---

## ④ 2:05–2:35 · The three numbers

> **SCREEN:** Deck **slide 06 / 15** ("Benchmarked, not vibes") as backdrop, with these overlaid:
>
> ```
> 35,000×2 + 6,500×2 + 4,500×6 + 3,000×6×2  =  ₹1,46,000   ✓ equals total shown
> pin inclusion 1.000 · pin stability 1.000 · 20/20 cases
> ```

**SAY** *(74 words)*

Three numbers, because budget reasoning is the claim I have to back.

One: that gate fired with the shortfall named — not a silent pass-through.

Two: pins survive. Across twenty cases, inclusion and stability both score a perfect one-point-zero.

Three: the breakdown actually adds up. Those four line items sum to one lakh forty-six thousand exactly. They're never allowed to drift from the total you're shown.

---

## ⑤ 2:35–2:52 · The honesty guard

> **SCREEN:** Back to live app. Type `plan me a trip to Wizarding World Goa`. Show the refusal.

**SAY** *(38 words)*

One more, live.

*(type it)*

There's no Wizarding World in Goa. She says so instead of inventing it. A hundred percent refusal rate on fabricated destinations — and a general-purpose model hedged on every equivalent case.

---

## ⑥ 2:52–3:22 · Who's accountable

> **SCREEN:** Admin dashboard, leads view. Show the response-time column and the status values: `pending` / `escalated` / `reassured` / `responded`.

**SAY** *(76 words)*

When Anya can't safely price something, a human takes over. Right now that human is me — I'm a solo builder, and that's a real single point of failure.

So it isn't a promise, it's a mechanism. Every quote request gets a confirmation email with a twenty-four-hour commitment. An hourly job escalates to me if I've missed it, and at forty-eight hours it emails the traveller anyway — so nobody sits in silence if I'm unreachable.

Response time is a tracked metric on this dashboard. A breach shows up here.

---

## ⑦ 3:22–3:47 · Honest gap, then the pilot

> **SCREEN:** `slide-real-vs-next.html`, full screen.

**SAY** *(64 words)*

What's real today: the whole loop you just watched, a hundred and seventy destinations with deep verified data, and eleven hundred automated checks.

What isn't: budgets are well-grounded *estimates*, not live airline and hotel prices. That integration is next, and it's the reason this doesn't launch publicly.

So the pilot is invite-only. Real travellers from my own network, plus a handful of travel agents hand-onboarded free — while I watch that dashboard.

---

## ⑧ 3:47–4:00 · Close

> **SCREEN:** Deck **slide 15 / 15** ("Plan it once.")

**SAY** *(31 words)*

I found and fixed an SSRF hole and missing rate limits before anyone else did, and I've told you what still doesn't work.

Wanderplanner. Plan it once.

---

## Deliberately not in this script

| Left out | Why |
|---|---|
| Anya speaking aloud | `TTS_PROVIDER` is off; credentials are on another machine |
| Signup / login flow | Dead screen time |
| PDF export, share link, booking click-through | One clause each at most; not shots |
| Test suite scrolling past | Faculty: "the honesty is what makes it credible, not the pass counts" |
| Market size, revenue, moat slides | Investor deck material; not this rubric |
| 0.98 fidelity score | Good number, but not one of the three budget numbers — it competes for the same seconds |
| "Quote requests are routed to agents" | They are tracked and escalated, not routed. Do not overstate this |
