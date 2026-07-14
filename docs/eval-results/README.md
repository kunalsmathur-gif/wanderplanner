# Can your AI travel planner prove it listened?

**WanderPlanner vs ChatGPT vs Claude on refinement fidelity — published eval, 2026-07-14**

Every AI travel tool demos well. You say "I'm a huge Harry Potter fan", it says "Sure!", and something plausible appears. The question that actually matters: **did the right places make it into the plan, are they real, and does the plan stay intact when you keep refining it?**

We built an eval for exactly that, ran our own product through it live, ran ChatGPT and Claude through the same prompts, and are publishing everything — including the cases we lose.

## TL;DR

| Metric | WanderPlanner | ChatGPT (free tier) | Claude Sonnet |
|---|---|---|---|
| Verified-POI recall | 0.94 | **1.00** | 0.98 |
| Unverifiable suggestions | **0.00** (dropped by design) | 0.74 | 0.79 |
| Pinned place appears exactly once in the itinerary | **1.00** | n/a¹ | n/a¹ |
| Pins survive an unrelated follow-up refinement | **1.00** | n/a¹ | n/a¹ |
| Honesty on impossible asks (strict, structural) | **4/4** | 0/4 | 0/4 — but see the disclosure below |

¹ Chat assistants return prose, not a structured itinerary with enforced constraints, so inclusion/stability are only measurable on WanderPlanner. That's part of the point — and part of why the comparison isn't apples-to-apples, which we say plainly below.

**The honest headline:** ChatGPT names slightly *more* of the right places than we do (1.00 vs 0.94 recall). But roughly **3 in 4 of its suggestions couldn't be verified** against our OpenStreetMap/Wikivoyage truth set, it padded answers with generic filler, and on the impossible ask ("Harry Potter attractions in Goa") it invented a venue that does not exist — **"Wizarding World Goa"**. WanderPlanner is structurally unable to do that: a place that fails OSM/Wikivoyage verification never becomes a pin.

## What we measured

20 cases from our public eval set ([refinement_fidelity_dataset.json](../../apps/api/eval/refinement_fidelity_dataset.json)): 16 named-interest refinements ("I'm a huge Harry Potter fan" in London, "zen gardens" in Kyoto, "Bollywood" in Mumbai, …) and 4 deliberately impossible asks (Formula 1 in Jaipur, scuba diving in landlocked Kyoto).

- **Pin recall** — of the interest-relevant places in the truth set, how many did the system verify and pin?
- **Inclusion** — does every pinned place appear in the generated itinerary *exactly once*?
- **Stability** — after an unrelated follow-up refinement ("make the pace more relaxed"), are the pins still there?
- **Pin precision** — are the pins actually about the stated interest?
- **Honesty** — when nothing real exists for the ask, does the system say so instead of inventing?

Fidelity score = 0.4·recall + 0.4·inclusion + 0.2·stability.

## WanderPlanner live results (2026-07-14, gemini-2.5-flash)

**Fidelity 0.975 · recall 0.938 · inclusion 1.000 · stability 1.000 · precision 0.979 · honesty 4/4.**

13 of 16 positive cases scored a perfect 1.00. The three misses, because publishing an eval means publishing the misses:

- **RF-001 London (Harry Potter)** — recall 0.67: one truth-set location wasn't proposed during interest expansion.
- **RF-009 Los Angeles (movie studios)** — recall 0.67: same failure mode.
- **RF-012 Mumbai (Bollywood)** — recall 0.67: expansion proposed Film City but not Mannat or Prithvi Theatre; our anti-distractor rule is deliberately conservative about celebrity homes.

Every place that *was* pinned appeared in the itinerary exactly once and survived further refinement, on every case. Full per-case tables: [report_vs_chatgpt.md](report_vs_chatgpt_2026-07-14.md) · [report_vs_claude_sonnet.md](report_vs_claude_sonnet_2026-07-14.md).

## How the baselines were recorded (protocol)

Same 20 prompts, verbatim. Same truth set, same fuzzy matcher, same extraction rule for all three systems: every specific place named in the answer counts; generic advice and whole neighbourhoods don't.

- **ChatGPT free tier** — recorded by hand on 2026-07-13, first answer per prompt, kept verbatim. Two mechanical corrections were made **in ChatGPT's favour** (a pasted-together artifact split into its two constituent places; "King's Cross Station (Platform 9¾)" split so the platform gets credited).
- **Claude Sonnet** — recorded on 2026-07-13 via fresh cold-context agents (claude-sonnet-5), one attempt per case, answering from model knowledge only (no tools, no web). The orchestrating session knew the answer key; the answering agents had zero access to it.

Raw recorded answers ship in the repo (`apps/api/eval/baselines/`) so every score is auditable.

## The honesty disclosure (read this before quoting the 0/4)

The honesty metric is strict and structural: on an impossible ask, the system passes only if it commits **zero** places to the plan.

- **WanderPlanner** passes 4/4: verification comes back empty, nothing is pinned, and Anya says so.
- **ChatGPT** fails 4/4 — and on Goa it invented "Wizarding World Goa", a venue that does not exist.
- **Claude Sonnet** *also* scores 0/4 on the strict metric — **but this materially undersells it.** In all four cases Claude's prose explicitly said the interest cannot genuinely be served at that destination, and only then offered clearly-labelled alternatives. No Claude answer contained an invented place. By verbal honesty Claude is 4/4; it fails only because the strict metric counts any named place, including honestly-labelled alternatives. The raw responses are preserved in the baseline file so you can check this yourself.

We could have published the 0/4 without the nuance. A fidelity eval that misleads about honesty would be a strange thing to build a verified-truth product on.

## What we are NOT claiming

- **"Unverifiable" does not mean "hallucinated."** It means our OSM/Wikivoyage fixture set with the same matcher could not confirm the place. Some unverifiable suggestions are real; one (Wizarding World Goa) provably is not.
- **This is n=20, one live run, one model version.** It's a wedge eval, not a benchmark paper. The offline replay of the same suite is deterministic and gates our CI at 1.000.
- **Chat assistants aren't itinerary engines.** Inclusion/stability being unmeasurable for them is a category difference, not a defeat. Our claim is narrower: if a system *does* promise a structured, refinable plan, these properties are checkable — and ours holds them at 1.00.

## Reproduce it

```
cd apps/api
python -m eval.run_refinement_eval            # offline, deterministic, free
python -m eval.run_refinement_eval --live     # live pipeline (needs GEMINI_API_KEY)
python -m eval.run_refinement_eval --results eval/out/refinement_fidelity_results.json \
    --baseline eval/baselines/chatgpt_refinement.json
```

---

*Reports in this directory are the verbatim generated output of the eval harness from the 2026-07-14 live run. The `eval/out/` directory is gitignored; these copies are committed deliberately as the published record.*
