# Data-freshness strategy: keeping pricing data current over time (Workstream D)

**Status: decision-support document only — no recommendation is baked in.
The free-vs-paid call is deliberately left to the user; see "Where sign-off
is needed" at the end.**

## Why this doc exists

`core/distance_pricing.py`'s `DISTANCE_BANDS` and `core/budget_estimator.py`'s
`_COST_MATRIX` are hand-anchored against real fare/rate data points
gathered manually (browser screenshots, `scripts/recalibrate_pricing.py`).
The Kaggle-pricing-plan workstreams (A–D) added two more sources: a
one-time Kaggle flight-fare dataset (`core/domestic_transport_pricing.py`
Workstream A, `scripts/ingest_kaggle_pricing.py` Workstream B) and
Inside Airbnb's hotel listings (`scripts/ingest_airbnb_pricing.py`, shipped
earlier). All of these share the same underlying problem: **the moment
data is gathered, it starts going stale**, and none of the current
mechanisms re-gather automatically. This doc lays out the realistic
options for closing that gap, with honest cost/freshness/effort/coverage
trade-offs for each — not a recommendation.

## The core tension

- **Flights/hotels are genuinely dynamic** (fuel surcharges, demand
  surges, seasonal swings) — a number anchored today is measurably wrong
  within months, not years. `core/pricing_multipliers.py`'s
  `inflation_multiplier()` already assumes ~6%/year drift as a baseline,
  and the Kaggle flight dataset is already ~4 years stale (see
  `docs/kaggle-data-runbook.md`'s sample findings).
- **This project's stated constraint is "free tools only, no paid pricing
  APIs"** (see `core/budget_estimator.py`'s module docstring) — this rules
  out the most reliable freshness mechanism (a live paid fare API) as a
  default, not as an option.
- **India-hotel pricing is the acute case**: no continuously-refreshed
  free source exists at all (see "Known gap" section below) — every other
  option in this doc either doesn't cover India, doesn't have a date
  dimension, or costs money.

## Option comparison

### 1. Manual Kaggle re-download

Periodically (human-triggered) re-run `docs/kaggle-data-runbook.md`'s
download + `scripts/ingest_kaggle_pricing.py` steps against whatever
dataset version is current on Kaggle, review the new proposal, hand-apply
via `scripts/recalibrate_pricing.py`.

- **Cost:** Free (Kaggle account + CC0/CC-BY datasets).
- **Freshness:** Low and unpredictable — depends entirely on whether the
  dataset's original author re-uploads. `shubhambathwal/flight-price-prediction`
  has not been updated since its original 2022 upload as of this doc
  (2026-08); there's no guarantee it ever will be.
- **Effort:** Low per-run (the tooling already exists), but requires a
  human to remember to do it — no automated trigger.
- **Coverage:** Whatever the dataset covers today (6 India metros,
  domestic only, economy class) — doesn't expand automatically.
- **Fit:** Matches this project's existing philosophy exactly (free,
  human-reviewed, propose-don't-auto-apply) — the path of least new
  process, but the weakest freshness guarantee of all five options.

### 2. Scheduled re-pull of the same static datasets

Same mechanism as (1), but on a cron/CI schedule (e.g. quarterly) rather
than ad-hoc human memory.

- **Cost:** Free (same datasets) + trivial CI compute.
- **Freshness:** Still bounded by the upstream dataset's own update
  cadence — a scheduled *check* doesn't create fresher *data* if the
  Kaggle dataset itself never changes. Real risk: the schedule runs
  forever against an unchanged 2022 CSV, producing a false sense of
  freshness ("we checked last quarter") while the actual staleness clock
  keeps ticking unaddressed.
- **Effort:** Low one-time CI setup; near-zero ongoing (until the proposal
  needs human review, which still requires a person regardless of how the
  check was triggered — `scripts/ingest_kaggle_pricing.py` intentionally
  never auto-applies).
- **Coverage:** Same as (1) — no coverage improvement, just a freshness
  *check* improvement (and only if upstream actually updates).
- **Fit:** A cheap process improvement over (1) if the goal is "don't
  forget to check", but doesn't solve the deeper problem that these
  specific datasets may simply never be updated by their authors.

### 3. Inside-Airbnb-style continuously-refreshed open data

Adopt more sources like Inside Airbnb (insideairbnb.com) — a standalone
free project (not Kaggle) publishing genuinely quarterly-refreshed,
CC BY 4.0 per-city listings CSVs, already integrated via
`scripts/ingest_airbnb_pricing.py`.

- **Cost:** Free.
- **Freshness:** Real and structural — this is the one option here where
  "freshness" isn't a manual process at all, it's a property of the
  upstream project's own publishing cadence (proven: this session's
  research confirmed live June-2026 data, i.e. genuinely current at time
  of check).
- **Effort:** Low per-city (script already built) but **discovery-limited**
  — finding an equivalent continuously-refreshed source for a new
  category (e.g. flights) is its own research project each time, not a
  repeatable mechanism.
- **Coverage:** The core weakness — Inside Airbnb covers ~100 cities,
  almost entirely US/Europe/select global metros. **Confirmed zero India
  coverage** (Mumbai and Goa both 404 on insideairbnb.com). This option
  works well where it has coverage and not at all where it doesn't — it
  can't be extended to India hotels by effort, only by luck of a new
  project appearing.
- **Fit:** Best freshness-to-effort ratio of the free options, but only
  where a project like this happens to exist for the category/region
  needed — doesn't generalize to fill the India-hotel gap.

### 4. Google Places API `price_level`

Paid, low-cost-per-call API returning an ordinal `price_level` (0–4 scale,
not exact ₹) per venue, including hotels, with genuine India coverage.

- **Cost:** Low-cost paid, pay-per-call (breaks the "free tools only"
  constraint, so this is the one option requiring an explicit policy
  exception, not just a budget line).
- **Freshness:** High — live API call, always current at query time (no
  stale-dataset problem at all, structurally different from every
  free option above).
- **Effort:** Real integration work (new API client, cost-per-call
  budgeting, ordinal-to-₹ mapping logic since 0–4 isn't a price figure) —
  moderate, one-time.
- **Coverage:** Real and India-covering — this is the one option that
  actually closes the India-hotel gap rather than working around it.
  Everything else in this doc explicitly does **not** solve that gap.
- **Fit:** Flagged elsewhere in this repo (`docs/NEXT_SESSION_TODO.md`) as
  "the most realistic paid upgrade path specifically for the India-hotel
  gap" — the only option that trades a small, bounded, per-call cost for
  a real coverage fix, rather than accepting the gap.

### 5. A full paid live-fare API

E.g. a flight-fare aggregator API (Skyscanner/Amadeus-style) with exact,
live, per-route/per-date pricing.

- **Cost:** Highest of all five — typically per-call or subscription
  pricing, scaling with usage; the most explicit conflict with the
  "free tools only, no paid pricing APIs" constraint.
- **Freshness:** Best possible — real-time, exact fares, no staleness
  concept at all.
- **Effort:** Highest — full API integration, auth/key management, rate
  limiting, likely a new abstraction layer to keep `DISTANCE_BANDS`-style
  callers decoupled from a specific vendor's response shape.
- **Coverage:** Complete, by construction — any route, any date.
- **Fit:** The "if cost were no object" answer — solves every problem in
  this doc at once, but is the option most at odds with the project's
  current no-paid-pricing-API stance, and the biggest engineering lift.

## Summary table

| Option | Cost | Freshness | Effort | Coverage (incl. India hotels) |
|---|---|---|---|---|
| 1. Manual Kaggle re-download | Free | Low, unpredictable | Low (manual trigger) | No improvement |
| 2. Scheduled re-pull | Free + trivial CI | Same as (1) unless upstream updates | Low one-time | No improvement |
| 3. Inside-Airbnb-style open data | Free | High where it exists | Low per-source, high per-discovery | **Confirmed no India coverage** |
| 4. Google Places `price_level` | Low-cost paid | High (live) | Moderate one-time | **Closes the India-hotel gap** (ordinal, not exact ₹) |
| 5. Full paid live-fare API | Highest | Highest | Highest | Complete |

## Known gap this doc does not resolve

India-hotel pricing remains the specific unresolved case driving most of
this analysis: per `docs/NEXT_SESSION_TODO.md`'s #55 findings, every
free India-hotel dataset checked (Kaggle scrapes of MakeMyTrip/Goibibo/OYO)
either has no date dimension or mixes incompatible pricing segments
(measured 2.38x spread from segment mix alone, larger than the inflation
effect it would be used to correct for) — none of options 1–3 fix this,
only option 4 (with ordinal, not exact, pricing) or option 5 (full cost)
would.

## Where sign-off is needed

This doc intentionally stops short of a recommendation. The decision that
needs the user's explicit sign-off:

1. **Stay fully free** (options 1–3 only) and accept the India-hotel gap
   remains open indefinitely, continuing the current manual
   Numbeo/screenshot-anchor workaround — or
2. **Approve a bounded paid-API exception** (option 4, Google Places
   `price_level`) specifically to close the India-hotel gap, which means
   amending the "free tools only" constraint documented in
   `core/budget_estimator.py`'s module docstring for this one case — or
3. **Approve a full paid live-fare API** (option 5) as a larger
   commercial-launch investment, likely worth revisiting once the product
   is past the pre-commercial phase referenced in `apps/api/core/budget_estimator.py`'s
   "PRE-COMMERCIAL-ONLY DATA SOURCES" flag.

No option has been implemented as a result of this document — it is
comparison material for that decision, not an implementation.
