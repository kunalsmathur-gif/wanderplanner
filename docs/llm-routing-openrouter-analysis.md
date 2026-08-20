# LLM Routing Analysis: Task-Based Model Selection via OpenRouter (or similar)

**Status:** Draft analysis — not yet a decision record
**Date:** 2026-08-18
**Scope:** All production LLM call sites in `apps/api` (RAG/itinerary generation, wizard chat,
chat refine, feasibility, interest expansion, recommend-cities, corpus extraction, travel tips,
destination comparison). Excludes voice (ADR 0001), embeddings/reranker (separate local models),
and the `eval/` harness (already multi-provider, discussed below as reuse candidate).

## 1. Why this question matters now

Today, **every** LLM call in WanderPlanner uses the same model, regardless of task complexity:

```
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
```

(`.env`; `core/config.py` default is `gemini-2.0-flash`, only relevant as an unset-env fallback.)

Nine production call sites hit `google.genai.Client()` directly, each with its own duplicated
retry/JSON-parsing/usage-tracking boilerplate:

| Call site | Purpose (from `track_gemini_usage(purpose=...)`) | Task shape |
|---|---|---|
| `chains/itinerary_chain.py::_gemini_itinerary` | `itinerary_generation` | Long, RAG-grounded, multi-day structured JSON generation. The one call the product's quality bar is built around. |
| `chains/wizard_chat_chain.py` | `wizard_chat` | Conversational slot-filling + JSON `config_patch` extraction, one turn at a time. |
| `chains/chat_refine_chain.py` | `chat_refine` | Edits an existing itinerary from a chat instruction; also does interest-pin insertion. |
| `chains/feasibility_chain.py` | `feasibility_check` | Short factual/estimate JSON (destination exists? budget realistic?). |
| `chains/recommend_cities_chain.py` | `recommend_cities` | Short structured JSON list of city suggestions. |
| `routers/travel_tips.py` | `travel_tips` | Short JSON list of tips, grounded by Reddit scrape. |
| `services/comparison.py::_compare_qualitative` | `comparison` | Short qualitative JSON comparing two destinations; **already has its own 3-model fallback list** (`gemini_model`, `gemini-2.5-flash-lite-preview-06-17`, `gemini-1.5-flash`). |
| `chains/extract_trip_chain.py` | `extract_trip` | Extraction from pasted itinerary text → structured trip config. Hardcodes `"gemini-2.5-flash"` (not `settings.gemini_model`). |
| `chains/interest_expansion_chain.py` | `interest_expansion` | Expands a user interest into candidate POI search terms. Hardcodes `"gemini-2.5-flash"`. |
| `chains/itinerary_corpus_extraction_chain.py` | `itinerary_corpus_extraction` | Offline corpus ingestion — extracts structured itinerary docs from scraped text. Hardcodes `"gemini-2.5-flash"`. |
| `chains/chat_chain.py` | `chat` | Simple single-turn chat reply (no structured output). |

Two of these (`extract_trip_chain.py`, `interest_expansion_chain.py`,
`itinerary_corpus_extraction_chain.py`) already hardcode a model string instead of reading
`settings.gemini_model` — an early, ad-hoc form of "this task doesn't need the configured
default," which is itself a signal that task-based tiering is already an implicit, undocumented
practice.

Separately, **`eval/llm_providers.py` and `eval/run_model_comparison.py` already solved multi-
provider dispatch** for Gemini/Groq/OpenAI/Anthropic/Moonshot — a `MODEL_REGISTRY` mapping model
id → provider, and a provider-agnostic `call_model(model, prompt) -> (text, prompt_tokens,
output_tokens)`. It is explicitly documented as bypassing production's provider logic and is
eval-only today. This is the closest existing precedent for what a production router would need.

## 2. Proposed task-complexity tiers (starting proposal, not final)

| Tier | Candidate call sites | Rationale |
|---|---|---|
| **Flagship** (current: `gemini-2.5-flash`) | `itinerary_generation` | Only call site with RAG grounding, budget arithmetic, day-by-day structure, and a dedicated 5-model-retry/deadline cascade already tuned around its latency profile. Quality regressions here are the most visible to users and the ones the `docs/eval-set.md` harness is built to catch. |
| **Mid** | `wizard_chat`, `chat_refine`, `comparison` | Multi-turn conversational reasoning with structured output, but shorter context and lower per-call stakes than full itinerary generation. `chat_refine` already treats itself as latency-sensitive (has a "one cheap retry" comment for transient errors). |
| **Cheap/fast** | `feasibility_check`, `recommend_cities`, `travel_tips`, `extract_trip`, `interest_expansion`, `chat` | Short, narrowly-scoped JSON extraction/classification tasks or single-turn replies — good candidates for a smaller/cheaper model, consistent with the fact that 3 of these already hardcode a cheaper-leaning model rather than the primary default. |
| **Offline/batch** | `itinerary_corpus_extraction` | Runs during corpus ingestion, not on the user request path — latency doesn't matter, only per-document cost at ingestion scale. Strongest candidate for the cheapest available model. |

This is a proposal for the user to react to — it is not validated against the actual per-task
accuracy requirements (that validation is exactly what `eval/run_model_comparison.py` /
`docs/eval-set.md` §8 already exists to do, and should be re-run against any specific model
swap before it ships).

## 3. Architectural impact of introducing OpenRouter

### 3.1 New central abstraction required

Today there is no shared "call an LLM" function — each of the 9+ call sites independently
constructs a `genai.Client()`, builds its own retry loop, strips markdown fences, and calls
`track_gemini_usage()`. Adding per-task model routing on top of this shape would mean either:

- duplicating the tiering logic 9 more times (bad), or
- finally centralizing into one `LLMClient`/router — e.g. `call_llm(purpose: str, prompt: str,
  **kwargs) -> LLMResult` — that looks up a model for `purpose`, dispatches to the right
  provider, and does response parsing + retry + usage tracking once.

This refactor is the real architectural cost of this change, independent of which gateway is
chosen. It is a prerequisite, not a nice-to-have, because without it "which model for which
task" becomes yet another thing hand-copied across chains (as `gemini_model` already is).

`eval/llm_providers.py`'s `MODEL_REGISTRY` + `call_model()` is structurally very close to what
this central router needs, but it's a blocking/sync design meant for a single eval script making
one call at a time — it would need adaptation (async, streaming where used, response-schema
validation, structured retry) to be production-grade rather than lifted as-is.

### 3.2 Config surface changes

- `settings.llm_provider: str` (`"groq" | "gemini" | "ollama" | "mock"`) would need an
  `"openrouter"` option, and likely a rename/generalization since "provider" currently means
  "which SDK for the whole app," not "which provider per task."
- `settings.gemini_model: str` (one global model) would need to become a purpose→model map. Two
  reasonable shapes:
  - Flat env vars per purpose (`MODEL_ITINERARY_GENERATION`, `MODEL_WIZARD_CHAT`, ...) — consistent
    with this repo's existing flat-env-var config style in `core/config.py`, easy to override per
    environment (Railway vs local `.env`), but verbose as tiers grow.
  - A small JSON/YAML tiering config (mirroring `eval/eval_config.json`, which `run_model_comparison.py`
    already reads via `eval/config_loader.py`) — less env sprawl, but a second place to look
    besides `.env`, and no precedent for prod (only eval) reading such a file today.
- API keys: currently `gemini_api_key`, `groq_api_key`, plus eval-only `openai_api_key`,
  `anthropic_api_key`, `moonshot_api_key`. OpenRouter collapses this to **one** `openrouter_api_key`
  for all providers it proxies — a real simplification if adopted broadly, at the cost of losing
  direct-provider fallback if OpenRouter itself has an outage (see §3.4).

### 3.2b Recommended immediate step: OpenRouter for `eval/` only, not production

A follow-up question sharpened this analysis considerably: **rather than choosing between Options
A/B/C up front, integrate OpenRouter only into the eval harness first, and let per-purpose eval
scores + measured cost decide the production tiering.** This changes the sequencing of the whole
recommendation (§4, §6) and is now the preferred next step. It works because:

- **Zero production risk.** `eval/llm_providers.py` is already documented as "kept separate from
  production's provider switch... on purpose" — adding an `"openrouter"` entry to its
  `MODEL_REGISTRY` / `_PROVIDER_CALLERS` (a `_call_openrouter()` alongside the existing
  `_call_gemini`/`_call_groq`/`_call_openai`/`_call_anthropic`/`_call_moonshot`) touches only eval
  code. Nothing on the request path changes; `_gemini_itinerary`'s tuned deadline cascade and every
  other production call site stay exactly as they are.
- **One key instead of five.** Today, comparing across providers in eval requires five separate
  keys (`gemini_api_key`, `groq_api_key`, `openai_api_key`, `anthropic_api_key`, `moonshot_api_key`),
  each provisioned and billed separately, and `is_available()`/`unavailable_reason()` already have
  to special-case "this model is skipped, no key set." A single `openrouter_api_key` gives eval
  access to Gemini, Claude, GPT, Llama, and dozens of others through one account/bill, removing
  most of that provisioning friction and letting the eval sweep be wider (more candidate models per
  run) without more keys to obtain.
- **It directly resolves open risk #1 (§5).** Running the *existing* `eval/run_model_comparison.py`
  with Gemini models routed through OpenRouter side-by-side with the current direct-SDK Gemini
  calls answers the JSON-mode/parity question (§3.3) with real accuracy/hallucination/latency
  numbers instead of an assumption — before any production code changes.
- **It directly resolves open risk #4 (§5, reuse vs. duplication).** Since this keeps OpenRouter
  eval-only, the "should the production router and eval share code" question doesn't need to be
  answered yet — it can be revisited once (if) a production router is actually built, with real
  cost-benefit numbers in hand to justify it.

**The gap this exposes:** today, only two eval harnesses do multi-model comparison —
`run_model_comparison.py` (itinerary generation only) and `run_budget_comparison.py` (a narrower
"ask an LLM directly" budget baseline). The other seven purposes (`wizard_chat`, `chat_refine`,
`feasibility_check`, `recommend_cities`, `travel_tips`, `extract_trip`, `interest_expansion`) have
**no multi-model comparison harness at all** — `run_wizard_eval.py`, for instance, calls the real
`wizard_chat()` production function directly against whatever single model
`settings.gemini_model` is set to; it checks structural correctness (via `wizard_checks.py`), not
model choice. So "run the existing eval suite through OpenRouter" is necessary but not sufficient —
getting real per-purpose, per-model data means either building lightweight comparison harnesses for
the other seven purposes (reusing `eval/llm_providers.py`'s new OpenRouter-aware `call_model()`,
and existing scoring building blocks like `wizard_checks.py` and `model_comparison_scoring.py`
where they're reusable), or accepting that the cost-benefit study only covers itinerary generation
and budget estimation at first and using judgment for the rest.

**Cost-benefit framework this enables**, per purpose: for each candidate model, capture (a) a
quality score (accuracy/schema-validity/hallucination-rate where an eval exists, or an LLM-judge
score per `eval/judge_metrics.py`'s pattern), (b) p50/p95 latency, and (c) cost per call at
realistic volume (`estimate_cost_usd()` already supports scale projection in
`run_model_comparison.py`'s `--scale` flag) — then pick the cheapest model per purpose whose
quality score clears a minimum bar, rather than guessing tiers as in §2. This turns §2's proposed
tiers from a guess into a decision backed by the same eval infrastructure this repo already trusts
for shipping changes (`docs/eval-set.md`).

### 3.2c Eval-set enhancements this actually requires

Two distinct questions came up: do the evalsets need enhancing to support model rating/
prioritization/routing, and do the eval **metrics/outputs** need updating? Both — and they split
into two different kinds of work, which matters because they're validated differently.

**A. Model *quality* rating — needs eval enhancement, purpose by purpose.**
As noted in §3.2b, only itinerary generation and (narrowly) budget estimation have multi-model
comparison today. Rating models for the other seven purposes means either:
- extending existing single-model harnesses to loop over candidate models — cheapest for
  `run_wizard_eval.py`, since `wizard_checks.py`'s checks (`check_chips_is_list`,
  `check_chip_topic_alignment`, `check_ready_to_generate_is_backed`, etc.) are already
  deterministic pass/fail functions decoupled from any specific model; they just need to run once
  per candidate model instead of once against `settings.gemini_model`, and be aggregated into a
  per-model pass-rate; or
- writing new comparison harnesses from scratch for purposes with no existing correctness checks at
  all (`feasibility_check`, `recommend_cities`, `travel_tips`, `interest_expansion`,
  `extract_trip`) — each needs its own small labeled dataset (a handful of cases with known-good
  answers, following `model_comparison_dataset.json`'s pattern) and a scoring function, since
  "correct feasibility estimate" and "correct city recommendation" aren't scored the same way
  "correct itinerary" is.

This is real, purpose-by-purpose effort — not a single generic change — and should be sized and
prioritized against how much each purpose's model choice actually matters (the flagship/mid/cheap
split in §2 is a reasonable order: build coverage for `chat_refine`/`wizard_chat` — the two "mid"
tier, higher-stakes conversational tasks — before the more mechanical "cheap" ones).

**B. Routing/retry *mechanism* correctness — this is a different kind of test, not an eval.**
Model-comparison evals judge output quality from live LLM calls. But a router doing per-purpose
model selection with fallback introduces engineering-logic questions that no amount of LLM judging
answers: does the router pick the configured model for a given purpose? Does fallback actually
trigger when the primary errors? Does the deadline-aware budget math (§3.4) still hold once
OpenRouter's native fallback array is layered in? These need **deterministic, mocked unit tests**,
in the same style `tests/unit/test_itinerary_timing.py` already uses for the current cascade
(`test_cascade_aborts_before_a_sleep_would_exceed_the_deadline`, `test_the_full_three_model_cascade_is_unreachable`,
etc. — no live API calls, a mocked always-failing/always-transient model, assertions on elapsed
time and attempt counts). Any central router built per §3.1 needs an equivalent test suite before
it can be trusted with the timeout math a past production incident already had to fix once.

**C. Metrics/output schema changes needed to actually support cross-purpose, cross-provider ranking.**
`eval/model_comparison_scoring.py`'s `accuracy_score`/`hallucination_rate`/`aggregate_model` are
itinerary-specific (schema validity, day-count match, theme coverage, budget adherence) and don't
generalize as-is to other purposes' correctness criteria. Concretely, the outputs need:
- **Provider-qualified model identity.** `MODEL_REGISTRY` today maps a bare model id (e.g.
  `"gemini-2.5-flash"`) to one provider. Once the same underlying model is reachable two ways
  (direct Gemini SDK vs. OpenRouter), results must distinguish them as separate rows — otherwise a
  report can't show "direct Gemini was faster but OpenRouter-routed Gemini was cheaper" — which
  means a composite key/naming convention (e.g. `openrouter/google/gemini-2.5-flash` vs.
  `gemini-2.5-flash`) rather than today's bare-name key, and `core/llm_client.py`'s `_PRICING` dict
  needs matching OpenRouter-specific entries (reflecting its markup) so cost isn't silently
  under-counted for that path.
- **A normalized, comparable quality scale across purposes.** Itinerary's accuracy score is a
  weighted composite 0–1; wizard's checks are per-check pass/fail booleans. To rank "which model
  for which purpose" on one shared axis, wizard-style checks need aggregating into a percentage
  pass rate (or similar) so it's combinable with itinerary's composite score in one decision table.
- **A combined decision-support output**, not just a per-model report. `render_report()` currently
  produces a per-model report with monthly cost projection; the cost-benefit study in §3.2b implies
  a further rollup — one row per *purpose* showing the winning model, its quality score, latency,
  and cost at the target volume — which doesn't exist yet and would be the actual artifact the
  production ADR (§6) consumes.
- **Judge-metric reuse for subjective quality beyond itinerary.** `eval/judge_metrics.py`'s
  LLM-judge pattern (used for itinerary tone/personalization/coherence) generalizes reasonably well
  to `wizard_chat`'s conversational quality or `chat_refine`'s helpfulness, and is cheaper to extend
  than writing new deterministic scoring for inherently subjective purposes.

### 3.3 Request/response parity risk (the biggest technical unknown)

The current itinerary call uses Gemini's native SDK feature
`response_mime_type="application/json"` (`genai_types.GenerateContentConfig`) to force valid JSON,
and the code still defensively strips markdown fences afterward ("Strip markdown fences if Gemini
adds them despite response_mime_type" — i.e., even the native mode isn't 100% reliable today).

OpenRouter is OpenAI-Chat-Completions-compatible: JSON enforcement goes through
`response_format={"type": "json_object"}` (or provider-dependent `json_schema` variants), routed
through to whichever upstream model is selected. This means:

- For Gemini models called *through* OpenRouter, behavior may differ subtly from calling the native
  `google-genai` SDK directly (different default sampling params, different JSON-mode enforcement
  path, potentially different safety-filter defaults) — this needs empirical verification via the
  existing eval harness before any production traffic moves, not an assumption.
- For non-Gemini models (Claude, GPT, Llama, etc.), JSON-mode support and quality vary by model —
  `eval/llm_providers.py` already encodes some of this per-provider variance today (`_call_anthropic`
  and `_call_moonshot` fall back to a "respond with ONLY valid JSON" prompt suffix instead of a
  structured mode, because their JSON-mode support is weaker/absent).
- Prompt-injection guarding (`core/prompt_guard.py`'s `neutralize`/`wrap_untrusted`, used to sandbox
  RAG-scraped content in every prompt above) is provider-agnostic by construction (it's prompt text,
  not an API feature), so this specific piece is not at risk — but it's worth stating explicitly in
  any migration doc so it isn't assumed to need rework.

### 3.4 Retry/fallback logic

The itinerary chain has a hand-tuned, deadline-aware, multi-model retry cascade (`_gemini_itinerary`):
up to 5 attempts per model across up to 3 fallback model ids, tracked against
`settings.llm_timeout_seconds` minus a safety margin, specifically because an earlier version of
this cascade could burn 225s of sleep against a 120s request budget. `services/comparison.py` has
its own, simpler 3-model fallback loop with the same shape.

OpenRouter supports a native multi-model `models: [...]` fallback array in a single request
(if the primary errors/is rate-limited, it tries the next listed model automatically), which could
*replace* these two hand-rolled cascades with configuration. That is a genuine simplification, but
it trades away the precise deadline-budget control this codebase has already had one production
incident about (see the `⚠️ Deadline-aware cascade (⭐ FIXED...)` comment in `itinerary_chain.py`) —
any migration must confirm OpenRouter's fallback exposes (or can approximate) the same wall-clock
budget guarantee before removing the custom cascade, not assume parity.

### 3.5 Cost/usage tracking

`core/llm_client.py::track_gemini_usage()` is named and shaped around Gemini's
`response.usage_metadata` (`prompt_token_count`, `candidates_token_count`). It already has a
`_PRICING` table with non-Gemini entries pre-populated (from eval work) and calls the
provider-agnostic `core/llm_usage.py::record_usage(provider=..., model=..., ...)` underneath — so
the *storage* layer is already provider-agnostic; only the *extraction* function is Gemini-specific.
Introducing OpenRouter means:

- Adding a `track_openrouter_usage()` (or generalizing `track_gemini_usage` into a
  `track_usage(response, provider, model, purpose)` that branches on response shape), since
  OpenRouter's response includes its own `usage` object plus (per their API) a cost/credits field
  that could replace the manually-maintained `_PRICING` table for OpenRouter-routed calls — worth
  using directly rather than hand-maintaining approximate list pricing that's already flagged in
  the code as "directional, not reconciled against real billing."
- The admin cost dashboard (`core/analytics.py`, referenced by `llm_client.py`'s docstring) would
  need to handle a new `provider="openrouter"` value alongside `"gemini"`.

### 3.6 Latency, reliability, and vendor considerations

- **Extra network hop**: OpenRouter sits between WanderPlanner and the upstream model provider —
  adds its own latency (typically small, but non-zero) and its own uptime as an additional failure
  domain on top of the upstream provider's.
- **Pricing markup**: OpenRouter charges a small margin (historically ~5%) over upstream list
  price in exchange for unified billing/routing — a real, ongoing cost tradeoff against the
  simplification it buys.
- **Rate limits/quotas**: today, Gemini quota is the sole constraint; OpenRouter introduces its own
  rate-limit tier (based on account credit balance) in addition to whatever the upstream provider
  enforces.
- **Single point of failure vs. diversified risk**: paradoxically, OpenRouter *reduces* blast radius
  of a single upstream provider outage (automatic model fallback across providers) but
  *concentrates* risk into OpenRouter's own infrastructure being up. Given the itinerary generation
  path already had a production incident from cascade-timeout-exhaustion (§3.4), this is a
  meaningful axis, not a theoretical one.

### 3.7 Testing impact

`settings.llm_provider == "mock"` is checked directly in `itinerary_chain.py` and used by
`_mock_reply`/`_mock_refine`/`_mock_feasibility`/`_mock_candidates`/`_mock_response`/
`_mock_qualitative` fallback functions across the chains, and existing unit tests
(`tests/unit/test_itinerary_timing.py`, `test_feasibility_stability.py`, etc.) rely on this mock
path plus on mocking `genai.Client` directly in some cases. A central router needs to preserve the
`mock` provider path unchanged (it's the CI-safe, no-network, no-cost test path) and any test that
patches `google.genai.Client` directly would need to be updated to patch the new abstraction
instead — this is a real, if mechanical, test-migration cost proportional to how many call sites
move behind the new router at once (see §4's phasing options).

### 3.8 Reuse vs. redundancy with `eval/`

If a central production router is built, `eval/llm_providers.py`'s `MODEL_REGISTRY` and per-provider
call functions (`_call_gemini`, `_call_groq`, `_call_openai`, `_call_anthropic`, `_call_moonshot`)
become largely redundant with it — both would need to know "how do I call model X." Two options:
have the eval harness import and reuse the production router (keeps one source of truth, but ties
eval code to production code — a deliberate choice the eval file's own docstring currently avoids:
"Kept separate... on purpose"), or keep them intentionally separate as today (accepts duplication,
but preserves the eval harness's ability to bypass production fallback/retry logic entirely when
comparing raw model quality, which is explicitly why it was built separate). This is a real
either-way tradeoff to decide explicitly, not default into.

## 4. Options comparison

| | **A. Status quo** | **B. Hybrid** (OpenRouter for cheap/mid tiers only; itinerary generation stays on direct Gemini SDK) | **C. Full OpenRouter** (all 9+ call sites, including itinerary generation, route through OpenRouter) |
|---|---|---|---|
| Code change scope | None | Build central router; migrate 8 lighter call sites; leave `_gemini_itinerary`'s tuned cascade untouched | Build central router; migrate all 9+ call sites, including replacing the hand-tuned deadline-aware cascade |
| Cost | One model price for everything (`gemini-2.5-flash` for a `feasibility_check` call that likely doesn't need it) | Cheaper models for 8 of 9 call sites' volume; flagship-tier cost unchanged for the highest-stakes call | Cheapest overall per-call pricing, minus OpenRouter's markup; markup applies even to the flagship call |
| Latency | Baseline (well-understood, already had one tuned incident-fix) | Unchanged for itinerary generation (the latency-critical path); other calls gain OpenRouter's hop but were not latency-critical to begin with | Itinerary generation gains OpenRouter's hop + must re-prove the deadline-cascade behavior holds |
| Reliability / blast radius | Single provider (Gemini) outage stops everything | Itinerary generation keeps direct-provider reliability (already hardened); lighter tasks depend on OpenRouter's uptime | Everything depends on OpenRouter's uptime, including the product's core feature |
| Vendor lock-in | High (Gemini-specific SDK calls, `response_mime_type` feature) | Reduced for 8 call sites; itinerary generation stays Gemini-SDK-coupled | Lowest — provider becomes a config value everywhere |
| Migration/testing risk | None | Moderate — 8 call sites' mocks/tests to update, itinerary path untouched and lowest-risk | Highest — must re-validate the itinerary path's JSON-mode reliability and retry-deadline math through a new gateway before it can replace a production-hardened path |
| Eval-harness overlap | None resolved | Central router built for 8 call sites could reuse `eval/llm_providers.py`'s registry as a starting point | Same, at larger scope |

**Revised recommendation:** Don't choose between A/B/C yet — do the **eval-only OpenRouter
integration (§3.2b) first**, run the per-purpose cost-benefit study it enables, and let that data
pick the tiering in §2 and the production option below. On the current evidence, **Option B
(hybrid)** is the more defensible destination once that data exists — it captures the bulk of the
cost win (8 of 9 call sites are the "cheap/fast" or "mid" tier candidates in §2, and none of them
carry the itinerary path's tuned incident history), builds the central router abstraction that's
required regardless of scope, and defers touching the one call site (`itinerary_generation`) that
has already had a production timeout incident and a dedicated, carefully-commented fix for it. Only
once the eval data specifically shows an OpenRouter-routed Gemini call preserves JSON fidelity and
the deadline-cascade behavior for that path should Option C be reconsidered — as a separate,
explicitly-scoped follow-up, not bundled into the same change, and not before real numbers exist.

## 5. Open risks / questions (flagged, not resolved here)

1. **JSON-mode parity**: does OpenRouter's `response_format` enforcement for Gemini models produce
   output at least as reliably-parseable as the native SDK's `response_mime_type`, given the
   current code already needs a markdown-fence-stripping fallback even on the native path? Needs
   an empirical run through `eval/run_model_comparison.py` (or an extension of it) before any
   call site moves, not an assumption.
2. **Deadline-budget parity**: if OpenRouter's native model-fallback array ever replaces the
   hand-rolled cascade in `_gemini_itinerary` (Option C), does it expose (or can it be configured
   to respect) the same wall-clock deadline guarantee that was added specifically to fix a past
   production incident (`llm_timeout_seconds` minus margin)? This must be verified, since silently
   losing that guaras behind a "simpler" gateway config would reintroduce the exact bug it fixed.
3. **Cost-tracking accuracy**: should OpenRouter-routed calls use OpenRouter's own reported
   cost/usage fields instead of `core/llm_client.py`'s manually-maintained `_PRICING` table (which
   the code already documents as "approximate... not reconciled against actual billing")? This
   seems like a clear win but touches the admin cost dashboard's assumptions and needs its own
   verification pass.
4. **Reuse vs. duplication of `eval/llm_providers.py`**: decide explicitly (§3.8) whether the
   central production router and the eval harness share code or intentionally stay separate —
   don't let this happen by default.
5. **Eval-set and metrics gaps (§3.2c)**: seven of nine purposes have no multi-model comparison
   harness today, and existing scoring (`accuracy_score`, `wizard_checks.py`'s pass/fail checks)
   isn't on a shared comparable scale across purposes — both need addressing before a data-driven
   per-purpose tier decision is trustworthy, not just for itinerary generation.
6. **Routing/retry mechanism testing (§3.2c-B)**: whatever central router gets built needs its own
   deterministic, mocked test suite (in the style of `test_itinerary_timing.py`) proving fallback
   and deadline-budget behavior — this is separate from, and in addition to, the LLM-quality evals
   above.
7. **Config shape**: flat per-purpose env vars vs. a JSON/YAML tiering config (§3.2) — a decision
   that affects how easy it is to change tiering later without a deploy, and should be made before,
   not during, implementation.
8. **Scope of "openrouter" as the specific chosen gateway** vs. the broader question of task-based
   model routing: nothing in this analysis is specific to OpenRouter as a brand — the same
   architectural changes (central router, purpose→model config, provider-agnostic usage tracking)
   would be required for any similar gateway (e.g. Portkey, LiteLLM proxy, or a hand-rolled
   multi-SDK router using the existing per-provider keys already scaffolded in `core/config.py`
   for eval). Worth deciding whether the gateway choice itself needs its own comparison before
   committing to OpenRouter specifically.

## 6. Suggested next step

Two phases, in order:

1. **Eval-only OpenRouter integration + per-purpose cost-benefit study (§3.2b, §3.2c).** Add an
   `openrouter` provider to `eval/llm_providers.py` (one API key, no production code touched, using
   provider-qualified model ids per §3.2c so direct-vs-OpenRouter-routed calls stay distinguishable
   in results); extend `run_model_comparison.py`'s itinerary comparison to include OpenRouter-routed
   models first (fastest to get data from, and directly answers open risk #1). Then close the
   per-purpose eval coverage gap (§3.2c-A) — prioritizing `wizard_chat`/`chat_refine` (the "mid"
   tier, highest-stakes conversational purposes) — and build the routing/retry mechanism test suite
   (§3.2c-B, mocked/deterministic, no live calls) alongside whichever central router gets built.
   Output: a per-purpose decision table (§3.2c-C) of candidate models with quality score, latency,
   and projected cost at realistic volume.
2. **Production ADR**, informed by phase 1's data (following the
   `docs/adr/0001-anya-voice-provider.md` convention), recording: the decision to introduce a
   central LLM router, the chosen config shape (§3.2), the data-backed tier mapping (replacing §2's
   guess), the explicit reuse-vs-duplication call on `eval/llm_providers.py` (§3.8), and which of
   Options A/B/C (§4) to build. Only at that point does the work become implementable as a scoped,
   incremental migration (one call site at a time, per this repo's existing incremental-
   implementation practice) — not before.

## 7. Live eval progress log (phase 1 execution — see GitHub issue #66)

**2026-08-19 — network exemption granted, first live run done.** The corporate Netskope DLP block
that stopped every OpenRouter call (documented in issue #66) was lifted. First live smoke test and
first `run_model_comparison.py` sweep (`--runs 1`, the 5 originally-registered `openrouter/*`
models) both succeeded end-to-end. Full results table in `docs/eval-set.md` §8D — short version:
`gpt-4o-mini` won on accuracy/cost/reliability, `llama-3.3-70b-instruct` had a weak judge-quality
score and one severe latency outlier, `gemini-2.5-flash` had the best judge quality but one hard
failure, and **2 of the 5 registered ids 404'd every call** (see below).

Two bugs found getting this far, both fixed:
- `_call_openrouter()` didn't cap `max_tokens`, so OpenRouter defaulted to the upstream model's own
  max (65535 for gemini-2.5-flash) — exceeded the account's available credit and 402'd every call.
  Now capped at 8192.
- `openai==1.51.0` (the `requirements-ml.txt` pin) isn't compatible with the `httpx` already
  installed in this venv (`proxies` kwarg TypeError) — bumped to `3.2.0`, live-verified against the
  real OpenRouter API.

**Model-id drift is real and ongoing**: `openrouter/google/gemini-2.0-flash-001` and
`openrouter/anthropic/claude-3.5-haiku` both now return `404 No endpoints found` — OpenRouter
retired those model generations since the registry was first written. Confirmed by downloading and
parsing `https://openrouter.ai/api/v1/models` directly (not a docs page, not an LLM's summary of
one — summarization of a 414-model JSON page is a real hallucination risk for exact id strings that
are about to be hardcoded into paid API calls). **Lesson: re-verify OpenRouter ids against the live
catalog endpoint before trusting a comparison, don't assume a slug that worked once still resolves.**

**Registry expanded same session** to 12 `openrouter/*` models: replaced the two dead ids with each
provider's current fast/cheap tier (`gemini-3.5-flash-lite`, `claude-haiku-4.5`), and added OpenAI
(`gpt-5-mini`), Kimi/Moonshot (`kimi-k2`), and DeepSeek (`deepseek-chat`) as new provider rows — all
at or above gemini-2.5-flash's capability tier — plus a low-cost/nano tier (`gpt-5-nano`,
`gemini-2.5-flash-lite`, `deepseek-v4-flash`, `llama-3.1-8b-instruct`) for future simple/non-critical
task routing (§3.2c-A's "mid" tier discussion). Also fixed a stale pricing entry found in the
process: `openrouter/meta-llama/llama-3.3-70b-instruct` was priced at `(0.59, 0.79)` in
`core/llm_client.py`, but OpenRouter's live rate is `(0.10, 0.32)` — the earlier comparison's cost
column for that model was quietly wrong.

**2026-08-19 (later) — first full-registry run invalidated by the account running out of credit
mid-run.** 6 of the 12 models failed every single call with `402 requires more credits`; models that
did complete showed latencies inflated to 3-6x normal (retries against a shrinking balance, not real
model speed). Confirmed via `GET /api/v1/credits`: `total_credits: 0`. **Lesson: check the credits
endpoint before trusting a multi-model sweep's latency/error numbers — a starved account produces
data that LOOKS like a real comparison (numbers, not outright failures) but isn't one.** User added
$10 credit.

**2026-08-20 — clean full run + one more real bug found and fixed.** Re-ran all 12 models with a
funded account: 10/12 succeeded cleanly (0-33% error rates, real latencies 11-134s p50). Full
results table in `docs/eval-set.md` §8D. `gpt-4o-mini` remains the strongest all-round pick (highest
accuracy, zero errors, cheapest of the reliable models); `claude-haiku-4.5`/`kimi-k2`/
`gemini-2.5-flash-lite` beat it on judge quality at a cost/latency premium; `llama-3.1-8b-instruct`
is far cheapest/fastest but weakest on judge quality — a candidate for the low-cost tier's intended
purpose (simple task routing), not itinerary generation.

Two models still failed, for two different real reasons:
- **`kimi-k2` (fixed)**: 400'd with `"model: moonshotai/kimi-k2-instruct does not support feature:
  structured-outputs"` — OpenRouter's routing for this model (via the Novita provider) doesn't
  support `response_format={"type": "json_object"}`. `_call_openrouter()` now catches that specific
  `BadRequestError` and retries once with a prompt-suffix JSON instruction, the same fallback
  `_call_anthropic`/`_call_moonshot` already use elsewhere in this file. Live-verified: re-run after
  the fix succeeded 5/6 (the 1 remaining failure was a genuine malformed-JSON response, an inherent
  risk of the prompt-suffix fallback vs. structured mode — see §3.3's parity-risk discussion, this
  IS that risk materializing). **Can't hardcode this per model id** — OpenRouter can route the same
  id to a different upstream provider over time, so any model could hit this.
- **`gpt-5-nano` (documented, not fixed)**: returned `content=None` on all 6 calls. It's a reasoning
  model — even a trivial test prompt spent 192 of 266 completion tokens on hidden `reasoning_tokens`
  before any visible output. Against the much longer real itinerary prompt it likely burns the whole
  8192-token cap on reasoning before emitting JSON. Same failure class already known in this project
  for Gemini's hidden-thinking tokens (§3.3 also flags "different default sampling params...
  potentially different safety-filter defaults" as an open unknown — add hidden reasoning-token
  budgets to that list). Real fix needs a reasoning-effort/budget control (OpenRouter exposes a
  `reasoning` param on some routes) — deferred as a per-model tuning problem, not a shared-code fix.

**2026-08-20 (later) — 3 frontier-tier models added on request** (`claude-sonnet-5`, `gpt-5.6-terra`,
`gpt-5.6-luna` — $2-12/1M tokens, notably pricier than the 12 above) to see whether spend buys a
real quality gain over `gpt-4o-mini`'s mid-tier win. It doesn't, on accuracy: neither beats
`gpt-4o-mini`'s 0.7478 despite costing 3-36x more per request. Judge quality is genuinely higher
(`gpt-5.6-luna` 0.97, 0 errors; `gpt-5.6-terra` 1.0 but only 3 judged samples) — full table in
`docs/eval-set.md` §8D.

**One more real, undiagnosed-until-now failure mode**: `claude-sonnet-5` failed all 6 calls with
`JSONDecodeError: Unterminated string...`. A direct diagnostic call against the actual production
prompt confirmed the cause: `finish_reason: length` at exactly 8192 completion tokens — Sonnet 5
produces longer itineraries than the shared `max_tokens` cap allows for this prompt shape, and gets
cut off mid-string. **Not fixed**: the cap is shared across every OpenRouter model in
`_call_openrouter()` specifically to stop the credit-exhaustion 402s documented above; raising it
globally would raise cost for every cheaper model too. The real fix is a per-model `max_tokens`
override (e.g. a second field alongside each `MODEL_REGISTRY` entry), not a blind global bump —
scoped as a follow-up, not attempted live this session.
