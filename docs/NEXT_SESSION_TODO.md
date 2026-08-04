# Next-Session TODO — Post-Cloud-migration cleanup → Reddit approval → Phase 2

---

## 📌 SESSION OF 2026-08-05 — demo-script validation (v10.71.0)

Validated every claim in `docs/video-script-4min.md` against live production
before recording. Full findings, reproducible test cases with verbatim outputs,
and a recording runbook: **`docs/demo-script-validation.md`**.

**Shipped:** three "Anya narrated an action she cannot perform" bugs (a pin
claimed but never created; the honesty message made unreachable by an early
return when interest-expansion found nothing; "make day 3 cheaper" promising an
edit with nothing to move it), per-day costs as a real feature, a cost-sanity
guard with one retry, Bali's OSM pool re-ingested from the correct centre, and
CI mypy back to green. Suite **1224 passed / 6 skipped**.

### Open items from this session

1. 🔴 **`geocode_city`'s hub-town correction is an Overpass call, and fails
   silently when throttled.** A bare region name resolves to the area centroid;
   `_hub_town_in_bbox` normally fixes it, but a `429`/`504` there means the raw
   centroid is used and ingestion lands tens of km away. **No downstream guard
   notices** — POI count, category share and the prominence check all pass on
   wrong-location data. Bali is pinned via `GEOCODE_QUERY_OVERRIDES`; **every
   other region-scale destination is unaudited.** Suggested: reverse-geocode
   each destination's stored POI centroid and compare against the expected
   country/hub, the way v10.37.0's geocode spot-check did for the mis-geocoded
   trio (Austin/La Paz/Valencia).

2. **The deck's `0.992` fidelity figure is unpublished.** It came from a live
   run on another machine and is real, but `apps/api/eval/out/` is gitignored,
   so every committed artifact still says **0.983** — including
   `docs/eval-results/report_vs_chatgpt_2026-07-15.md`, `eval-set.md` §509,
   `system-design.md`, `TECHNICAL_DOCUMENTATION.md` and the pitch deck's own
   `index.html` (×3). On a slide captioned "a published eval suite", the
   headline should be a number the repo can show a source for. **This is a
   publishing job, not a re-measure** — copy that machine's
   `refinement_fidelity_report.md` + `refinement_fidelity_results.json` into
   `docs/eval-results/` as a dated pair, then sweep 0.983 → 0.992.
   ⚠️ **Copy the raw JSON off that machine before running anything else there**
   — any subsequent run overwrites it in place, including the free offline
   gate. That is how the 2026-07-14 live results were lost.

3. **Deck slide 4 compares two different metrics.** It reads "0.992 — Fidelity
   score (vs ChatGPT 0.74)", but **0.74 is ChatGPT's unverifiable-suggestion
   rate**, not a fidelity score. The older `pitch-deck/index.html` says "vs
   ChatGPT 0.74 unverifiable"; the new `demo-deck.html` dropped the qualifier.
   Also on that slide: "Pin inclusion & stability · 20/20" — both metrics are
   only defined on the 16 positive cases; the other 4 are honesty cases.

4. **Cost estimates can still be wrong ~1 in 5 runs without the guard firing
   on scale.** The guard catches gross unit errors and direction violations,
   but a *plausible-looking* wrong number passes. Worth a second anchor if
   costs ever become user-facing beyond an estimate — the deterministic
   `estimate_bare_minimum_budget` floor is the obvious candidate, at the cost
   of an extra call on the generation path.

5. **Frontend `tsc` has one pre-existing error** —
   `__tests__/hooks/useVoice.test.tsx(606,84): Expected 1 arguments, but got 2`,
   which arrived with v10.68 and is unrelated to this session. Confirmed
   pre-existing by stashing all v10.71 frontend changes.

6. **`ExpenseBreakupCard` hides zero-value rows**, so Bali (visa ₹0) renders
   seven of the eight cost categories. Not a bug — but any copy that says
   "eight categories" is wrong for such destinations, and the demo script has
   been corrected accordingly.

---

## 📌 SESSION OF 2026-08-03 — one security fix shipped, one research issue closed

**v10.65.0 — the prompt-injection fence could be closed from inside (#42, closed).**
The issue's premise was stale: `tests/unit/test_prompt_guard.py` had existed since
2026-07-21. The real gap was that it never touched `eval/red_team_dataset.json`.
Writing that test surfaced an actual vulnerability: `wrap_untrusted()` fenced
untrusted text in `<tag>…</tag>`, but `neutralize()`'s pattern list **did not
include the guard's own tag** — the one tag an attacker can predict exactly,
since all 8 call sites pass hardcoded literals. Scraped content containing a
literal `</untrusted_content>` closed the fence early and the rest read as
top-level prompt. Fixed with `_strip_fence_tags()`. 28 → **49 tests**.
⚠️ **Two rules in that function's docstring must not be undone** — a code review
caught both: (1) it must match `[^>]*` not `\s*` after the tag name, because
HTML5 parses `</div foo="bar">` as an end tag; (2) both character classes must
stay **single quantifiers** — the original `<\s*/?\s*tag\s*>` was quadratic and
took 0.169s at the 6000-char cap (attacker-triggerable event-loop block) vs
0.00076s now, ~220x faster. Pinned by a scaling test.
🔵 Deliberately **not** redacted: `---`. It's a visual separator, not the
terminator, and scraped markdown is full of horizontal rules. Pinned by test.

**#55 closed — Kaggle hotel-pricing search done, answer is "nothing usable".**
Two premises in that issue were wrong: the token flow has moved off `kaggle.json`,
and the search never needed a human at all (`kaggle datasets list --search` hits
the REST API; only the *website* is JS-rendered). Detail inline in Workstream B
below. Headline: **India hotel pricing stays unresolved**, now confirmed against
the live corpus rather than assumed, and **segment mix (2.38x) is a bigger error
source than staleness (1.10x)** — so an inflation multiplier alone would make
pooled Kaggle hotel data *confidently* wrong. Recorded as scope input on #53.

**#57 deferred (not closed).** Hobby project, invite-only, no commercial launch —
so the Numbeo/budgetyourtrip re-sourcing isn't a live gate yet. `ready-for-agent`
removed; left open with re-activation triggers on the issue. ⚠️ This supersedes
the "Numbeo premium food is top priority" note further down this doc.

**Found, not fixed (carry forward):**
- `TECHNICAL_DOCUMENTATION.md` §14 has **no entries for v10.63.0 / v10.64.0**.
- `Skeleton Test City` fixture data is still sitting in the **production** Qdrant
  cluster (from the 2026-08-01 session).
- v10.55.0's cookie/logout fix is **still unverified on the deployed site** —
  needs a Railway redeploy + manual check on wanderplanner.org.
- `kaggle==2.2.4` was installed into `apps/api/.venv` to run the #55 searches but
  **deliberately left out of `requirements.txt`** — whether it becomes a real
  dependency is #52's call.

---

## 📌 SESSION OF 2026-08-01 — what shipped, and what it changed

Three releases. Read this before picking anything below.

**v10.54.0 — first `visa_info` ingestion (#59, closed).** 1,291 chunks across
**73/73** seed countries, verified against the live cluster (point count,
distinct countries, attributed `retrieve_visa_note()` with a negative control,
zero `[ edit ]` markers, full v10.50 metadata). 📦 **`scripts/ingest_visa_info_full.py`
is committed — don't rebuild it** (resumable, `--fresh`, free Wikimedia API).
🔴 It also found a bug: `/wiki/Georgia` is a **disambiguation page** answering
200 OK while the real guide sits at `Georgia (country)`. `scrape_visa_info()`
now retries with the `"<Name> (country)"` suffix, on the empty path only.
⚠️ **All 73 titles were audited for the silently-wrong-article case** — a
real-but-wrong page still returns chunks, which a point count structurally
cannot catch. Only Georgia was affected. **Re-run that audit if
`VISA_SEED_COUNTRIES` grows.**

**v10.54.1 — CI was red on `main`, now green.** 1 ruff + 8 mypy errors that
arrived with the 19 commits pulled at the start of the session; confirmed
pre-existing against a pristine worktree at `9e876ba`. ⚠️ `routers/admin.py`'s
`datetime | None` access was **not** a latent `AttributeError` — the query
filters `responded_at.is_not(None)`.

**v10.55.0 — three live-reported auth/routing bugs, one root cause: the
itinerary had no route of its own.** It now lives at **`/itinerary`** and `/`
is the landing page only. Logout appeared dead there because
`router.push('/')` is a no-op on the page you are already on, and `logout()`
cleared only `user`. Separately `_clear_session_cookies()` emitted
`SameSite=lax` with no `Secure` while issuance used `Secure; SameSite=none`, so
**the browser ignored the deletion and the session survived logout** — the
DB-side revocation had always worked, which is exactly why no existing test
caught it. Issuance and deletion now share one `_cookie_kwargs()`.
🔴 **Still unconfirmed on the deployed site:** that cookie fix only changes
behaviour cross-site, so it needs a Railway redeploy plus one manual
logout-then-revisit check against `wanderplanner.org`.

**Issue tracker: 20 → 17 open.** Closed #59, #49 (wikidata prominence shipped
in v10.40.0) and #46 (`youtube_narration` verified at 172 destinations,
identical to `youtube_comments`, zero missing). ⚠️ **#47 was left open
deliberately** — the code is done, but **only 1 of the 9 Wikivoyage seed titles
has ever produced a document in `itinerary_corpus`** (`Buddhist Circuit`), so
the India-thinness the issue exists to fix is untouched and the cause for the
other 7 is unmeasured. Read closed issue **#60** before touching it: that run
already diagnosed `Grand Trunk Road`.

**Found, not fixed:** `Skeleton Test City` is test-fixture data sitting in the
**production** Qdrant cluster (8 points in `youtube_narration`, also present in
`youtube_comments`). It inflates destination counts and consumes free-tier
headroom.

---

## 🔥 QUEUE AGREED WITH THE USER 2026-07-27 (do these in order)

**1. ✅ DONE — hidden-gem re-audit (shipped as v10.42.0).** Full write-up in
`TECHNICAL_DOCUMENTATION.md` §14 v10.42.0. Headline: first 168-destination measurement; the pool
problem from v10.39.0 is fixed, the bottleneck had moved to the sentiment floor, and destinations
returning a gem went **44% → 54%** (total gems 127 → 172) while total matched POIs *fell* 541 → 530
as double-counts were removed. **Two items below came out of it.**

> **📦 The audit tooling is committed — don't rebuild it.** This is the fourth gem audit, so it is
> now a permanent entry point rather than a throwaway script:
> - **`apps/api/scripts/audit_gems.py`** — full 168-destination read-only audit. Resumable, no
>   flags, ~15 min against the live cluster. Prints zero-gem attribution buckets, so it answers
>   *why* a destination returns nothing, not just that it does. ⚠️ It carries a replica of
>   `gems.py`'s scoring loop and asserts `replica_matches_real` per destination — **if that flag
>   ever goes False the shipped loop has changed and the script needs re-syncing before its
>   diagnostics mean anything** (that check caught exactly this drift during v10.42.0).
> - **`apps/api/scripts/calibrate_gem_lexicon.py`** — **run this before adding ANY word to the
>   sentiment lexicon.** Scores each candidate's enrichment for creator context and prints an
>   accept/reject verdict, which is what stops someone re-adding `great`/`nice`/`awesome` on
>   intuition. Runs offline against the committed baseline in seconds.
> - **`apps/api/scripts/baselines/`** (tracked, deliberately *not* under the gitignored
>   `scripts/out/`): `gems_audit_20260727_pre_v10.42.0.jsonl` is the **pre-fix baseline and cannot
>   be regenerated** — the scoring code has changed since. The post-fix run and the 1,274-window
>   `gem_mention_windows_20260727.json` calibration corpus sit alongside it.

**2. ✅ DONE 2026-07-28 — input validation / "monkey testing" hardening (shipped as v10.43.0).**
Full write-up in `TECHNICAL_DOCUMENTATION.md` §14 v10.43.0 and `docs/system-design.md` §8 + §16.
New `core/validation.py` holds the caps, the normaliser and the `Annotated` field types; every
model that carries user text uses them, six endpoints validate query/path params through the same
rules, `apps/web/lib/limits.ts` mirrors the numbers, and `tests/unit/test_input_validation.py`
covers it (84 tests). Suite **806 passed / 6 skipped**, ruff + mypy clean.

**Four defects the probe had NOT found, all more serious than the ones it did:**

- 🔴 **A long date span was a memory-exhaustion vector.** `_mock_itinerary` builds one dict per day
  with three items each, so `{"start": "2026-01-01", "end": "2999-01-01"}` was ~355,000 iterations
  from a single request body. Now bounded in the model *and* clamped in the loop — that path also
  runs on dicts that never went through the validator.
- 🔴 **Unparseable dates were swallowed by a bare `except`** and replaced with a hard-coded default,
  so a user was silently planned a trip in a different month.
- 🔴 **`hops` said "multi-stop, max 5" in a comment and enforced nothing** — and each hop is its own
  cold-start Overpass + Wikivoyage + embedding run.
- 🔴 **`_tips_cache` is a process-lifetime dict keyed on the raw destination string**, so unbounded
  input meant unbounded keys.

**Worth carrying forward:**

- The 422 body echoes the rejected value back by default, so an input cap without a response cap is
  paid for twice. `main.py` now truncates the echo. Check this on any future validation work.
- ~~⚠️ **Deliberately NOT converted to `Literal`: `pace`, `scope`, `crowd_preference`,
  `destination_mode`.**~~ — ✅ **DONE 2026-07-28 (v10.46.0).** Normalise-then-constrain, in that
  order: `core/validation.py` holds a per-field vocabulary + alias map behind an
  `Annotated[Literal[...], BeforeValidator(...)]`, so the literal is satisfied by construction. It
  absorbs casing (`"Moderate"`), decoration (`"off-beat"`, `"off_the_beaten_path"`) and synonyms
  (`"slow"`, `"abroad"`, `"undecided"`). 51 tests in `tests/unit/test_choice_normalisation.py`.

  🔴 **The one thing worth carrying: doing this at the model layer alone would have fixed almost
  nothing.** `config_patch` is merged as a **plain dict** into `partial_config` and handed back to
  the frontend — it never passes through `TripConfig` during the conversation, `wizard_chat_chain.py`
  branches on exact values (`mode == "fixed"`) for every remaining turn, and the frontend's
  TypeScript unions are erased at runtime so it would simply have believed the bad value.
  Normalisation therefore runs at the patch-merge point in `wizard_chat_chain.py` **and**
  `chat_refine_chain.py`. **Generalises: when a value is validated at a boundary the request only
  reaches at the end, find every earlier consumer first.**

  ⚠️ **Two rules recorded in `core/validation.py` so a future edit doesn't undo them:** (1)
  unrecognised values **fall back + log a WARNING rather than raising** — the deliberate exception to
  that module's "reject, never coerce" rule, because here the producer is our own prompt, not a user;
  (2) **alias maps are per-field and must not be merged** — `"moderate"` is a canonical `pace` *and*
  an alias for `crowd_preference: "balanced"`.
- The frontend caps mirror the backend **exactly, on purpose** (`apps/web/lib/limits.ts` says so).
  A tighter frontend cap silently truncates what the API would accept; a looser one lets the user
  type what can only fail at submit. Change them together.

**3. ✅ DONE 2026-07-28 — voice mode tested for the first time, and Anya now speaks Hindi (shipped
as v10.45.0).** Full write-up in `TECHNICAL_DOCUMENTATION.md` §14 v10.45.0 and
`docs/system-design.md` §16. Voice moved out of the 959-line `LLMWizard.tsx` into
`apps/web/lib/voice.ts` (pure helpers) and `apps/web/hooks/useVoice.ts` (state + Web Speech
wiring). Frontend tests **44 → 122**, backend **830 → 844**; ruff, mypy and `tsc --noEmit` clean.

> 🔴 **A fifth defect, larger than the four below, only turned up while writing the tests: TTS had
> never fired in production at all.** Two independent causes, either sufficient. (1) `toggleVoice()`
> assigned `rec.onresult` and *then* called `setVoiceActive(true)`, so the handler held the
> `handleSubmit`/`sendMessage` pair from the render where the flag was still `false` — and
> `sendMessage`'s `if (voiceActive) speak(res.reply)` read that stale `false` every time. (2) One
> flag meant both "the user wants a spoken conversation" and "the mic is open", and `rec.onend`
> fires the moment the user stops talking, seconds before the reply lands. **Confirmed by
> reconstructing the old implementation and running it through the real event order**, not by
> reading — the reply arrived, `speak` was never called. `voiceMode` / `isListening` / `isSpeaking`
> are now three separate things.

⭐ **New in the same release: Hindi voice I/O.** `rec.lang` was hardcoded `en-IN` (Indian-accented
*English*), so speaking Hindi returned garbled English guesses. The Web Speech API has **no
auto-detect** — one language per recognition session — so there is now an explicit English / हिंदी
toggle driving recognition language, utterance language and voice selection together.
`WIZARD_SYSTEM_PROMPT` §3a makes Anya reply in the user's language, while **`chips` and
`config_patch` stay English**: chips are classified by English keyword match (a translated chip
silently collapses multi-select rather than failing), and a destination is a database key, so "गोवा"
would fork from "Goa" and trigger a redundant cold-start ingestion. Typed Devanagari already worked
end-to-end — verified by measurement against `clean_user_text`, not assumed from its docstring.

⚠️ **Residuals worth carrying (measured, not guessed):**

- **The dev machine has no `hi-IN` voice installed** — `getVoices()` returns five, all
  `en-US`/`en-IN`. Hindi *recognition* works (Chrome routes it to a cloud service); Hindi *speech*
  needs a Windows Hindi language pack. This is the expected desktop case, so the hook checks voice
  availability up front and says so, rather than waiting for a `language-unavailable` event that
  several browsers never fire.
- **English-in-`config_patch` is a prompt-level guarantee, not an enforced one.** `CityName` accepts
  `"गोवा"` — verified. Enforcing it needs transliteration or a lookup; not built.
- **`_strip_leaked_reasoning` does not fire on Hindi replies.** Pass 1 matches English warm openers,
  pass 2 splits on `[.!?]` which a danda-terminated sentence never matches. It degrades to "return
  unchanged" — the safe direction — and leaks are English-shaped in practice because the model
  reasons about our English field names.
- **UI chrome stays English when हिंदी is selected.** The toggle is scoped to voice and labelled
  that way; full interface localisation is separate work.
- 📱 **Mobile is unverified and mobile is the bulk of the users — see queue item 6 below for the
  step-by-step.**
- 🔴 **Anya was speaking in a *male* voice, and it was measured not guessed.** The female
  preference matched `/female/` in the voice name, but no platform puts it there. On the real dev
  machine `pickVoice(voices, 'en-IN')` returned **Microsoft Ravi**, with Heera sitting right beside
  him in the list, purely because neither name says "female" so it fell through to array order.
  Fixed with curated per-platform name lists (Kalpana/Lekha/Swara for hi-IN, Heera/Veena/Neerja for
  en-IN, plus the male names to rank *below* unknown ones). **The Web Speech API has no gender
  field** — verified: Windows records `Attributes\Gender` per voice in the registry and the browser
  drops it, so name matching is the only lever, not a shortcut. An unrecognised name scores neutral
  and is still used; the cost of not knowing a voice is the wrong gender, the cost of refusing it is
  silence.

**The four defects as originally filed, all fixed:**

- 🔴 **The mic button is dead on Firefox with no feedback.** Rendered unconditionally
  (`LLMWizard.tsx:692` and `:922`), but `toggleVoice` does `if (!Ctor) return` (`:640`) and Firefox
  has never shipped `SpeechRecognition`. Click → nothing at all.
- 🔴 **Every recognition error collapses into one silent handler** — `rec.onerror = () =>
  setVoiceActive(false)` (`:651`). The API distinguishes `not-allowed` (permission denied),
  `no-speech`, `audio-capture` (no mic), `network`, `aborted`; a user who *denied mic permission*
  gets the same nothing as one who paused. TTS has the identical swallow at `:370`.
- 🔴 **`getVoices()` race** (`:359`) — Chrome returns `[]` until `voiceschanged` fires and there is
  no `voiceschanged` listener in the file, so on a cold load the en-IN female voice selection falls
  through to the system default and the India-first persona doesn't apply to the first utterance.
- 🔴 **TTS silently drops Devanagari entirely.** `:353` is `.replace(/[^\w\s.,!?'₹%-]/g, '')`, and
  JavaScript's `\w` is always ASCII `[A-Za-z0-9_]` (the `u` flag does not change this) — so every
  Devanagari character is stripped, `clean` becomes empty, and `if (!clean) return` on the next line
  means TTS **says nothing**. `₹` was explicitly whitelisted, so India was in mind — just the
  currency, not the script. **Same bug family as v10.41.0's "`\b` silently fails on Devanagari", in
  a module nobody had connected to it — the third recurrence of that pattern.**
- ℹ️ **Stale as written — corrected 2026-07-28:** `ConversationalWizard.tsx` no longer exists in the
  repo (it was deleted along with `WizardForm.tsx`). `app/page.tsx` renders `LLMWizard`, which was
  the only voice code left.
- ➕ **Found while doing this, also fixed:** `isSpeaking` was set in three places and read in none,
  so there was no speaking indicator anywhere in the UI; and `ListeningOrb` is rendered only by
  `FloatingAnyaButton` with hardcoded `isActive={false} isRecording={false}`, so **the orb has never
  animated** — still true, and out of scope here since that button has no access to wizard state.

**4. 🔴 Carried out of the gem audit, NOT fixed — `name_matching.py` derives demonyms.**
`name_variants("Egyptian Museum")` peels the structural word "museum" and emits the bare token
`egyptian`, which clears `_MIN_CORE_TOKEN_LEN` (8) and then matches "egyptian food", "as an
egyptian". Live-measured: **Cairo's Egyptian Museum shows 30 mentions, 29 of them from the bare
token** — the real name appears in 1 chunk. ⚠️ **Not a knob turn:** `_MIN_CORE_TOKEN_LEN` is
documented as calibrated against the 2026-07-25 audit, `egyptian` is exactly 8 characters, and so is
the genuine recovery `immanuel` — raising it to 9 loses the latter. The module is shared with
`services/poi_pinning.py`, so any change needs its own calibration pass across both consumers.

✅ **DONE 2026-07-28 — shipped as v10.44.0.** Full write-up in `TECHNICAL_DOCUMENTATION.md` §14
v10.44.0 and `docs/system-design.md` §16. The guard now tests whether a derived single-token core is
an *ordinary English word* rather than only whether it is long enough, against a committed word list
generated from the embedding model's WordPiece vocabulary (`scripts/generate_common_words.py` →
`services/data/common_english_words.txt`; read from disk, no model at runtime). Suite **830 passed /
6 skipped**, ruff + mypy clean.

**Two corrections to the framing above, both worth internalising:**

- 🔴 **The scope was a tenth of the real bug.** It was filed from one observation (Cairo, 29 wrong
  mentions). Measuring the class *before* sizing the fix — 9,892 POIs, all 168 destinations —
  showed `egyptian` is a mid-sized instance of a much larger one: **any POI whose name begins with
  its own city**, in that city's corpus, where the city name is the most frequent token by
  construction. **Singapore Zoo 100 mentions → 2, Edinburgh Castle 84 → 2**, and Melbourne Museum /
  Melbourne Park / Melbourne City Synagogue each independently absorbing Melbourne's entire comment
  volume at 59-61.
- **"The module is shared with `poi_pinning.py`" was true of the module and wrong about the
  function.** `poi_pinning.py` imports only `normalize_name`, which is untouched; `name_variants`
  and its guard have exactly one production consumer. That caution added work that did not exist.

**Results across all 168 destinations** (committed `audit_gems.py` vs the committed post-v10.42.0
baseline; `n_candidates` identical at 9,556 — the control saying only matching changed): matched
POIs 530 → **472**, crowd favourites 87 → **50**, gems 172 → 166, destinations returning a gem
90 → 88, replica mismatches 0. Crowd favourites fall hardest because a POI with 100 fabricated
mentions ranks as one *by definition*. Three destinations lost their only gem and all three were
gems solely via a common-word core (Colombo "Independence Square", Ooty "Government Museum",
Prague "National Theatre"); Melbourne gained one.

**Carry forward:**

- ⚠️ **Fame and vocabulary membership correlate** — `guggenheim`, `griffith` and `hollywood` are
  rejected along with the demonyms, because they are in the vocabulary *because* they are famous.
  Acceptable for a hidden-*gem* feature; if it ever matters the fix is a curated exception list,
  **not** a lower threshold. A wrong variant corrupts the output while a missing one falls back to
  the full name — that asymmetry is why the guard is deliberately conservative.
- ⚠️ **`audit_gems.py`'s `top_matches` holds only the top 5 per destination**, so a POI vanishing
  from it is not the same as its mentions reaching zero. Of 42 POIs that dropped by 3+, 35 are
  directly measured and 7 are unknown. Do not read absence from that list as a zero.
- `services/data/common_english_words.txt` is **generated, not hand-edited** — re-run
  `scripts/generate_common_words.py` if the embedding model ever changes.

**5. ✅ DONE 2026-07-29 — `generate_itinerary()` is instrumented and measured (shipped as v10.47.0).**
Full write-up in `TECHNICAL_DOCUMENTATION.md` §14 v10.47.0 and `docs/system-design.md` §16. New
`core/timing.py` accumulates per-stage wall-clock against a `ContextVar` (so no signature churn
across six call sites) and emits one structured record per generation, escalating to WARNING past
`slow_itinerary_threshold_seconds`. 22 tests; suite **883 passed / 6 skipped**, ruff + mypy clean.

> 🔴 **A prerequisite bug: `JsonFormatter` silently dropped `extra=`.** It emitted only
> timestamp/level/logger/message, so the timings would have reached no sink at all. `RedactionFilter`
> had the matching hole — it covers `getMessage()`, and structured values ride *beside* the message,
> so they went out unredacted. Same blind spot as v10.40.3's state-file leak.

**Measured live (Gemini + real Qdrant Cloud): total 62.6s Jaipur / 48.0s Paris, `llm_api` 57–87%.**
Three of the four bullets originally filed here turned out to be wrong, and the numbers are why:

- ✅ **"Each new refinement stacks onto the critical path" — refuted.** Scoring + persona injection +
  pin enforcement + `generation_tier` cost **1.3 milliseconds** combined.
- 🔴 **"Destination cold-start ingestion blocks the response" — true in principle, but the gate cost
  0.03s and the *real* cold start is elsewhere.** Jaipur's 20.9s retrieval was **one-time model
  load**, isolated by measuring retrieval alone: cold process 20.0s → warm 1.4s → Paris 2.2s →
  Jaipur again 1.45s. So **the first request after every deploy pays ~18.6s**, and Railway redeploys
  on every push. Nobody had named that.
- ✅ **RESOLVED 2026-08-02 (v10.59.0) — but not the way this bullet expected, and its standing
  instruction was deliberately overridden.** The original text ended *"do not move the fetch off the
  critical path until [the instrumentation] has [answered its p95]"*. That was right while the open
  question was "how slow is this?", and it stopped being the question once the *consumers* were
  checked: `image_url` is read by `ItineraryDocument.tsx` and nothing else — the dashboard day
  cards render YouTube thumbnails, and no file under `components/itinerary/` touches the field. So
  every generation was awaiting a metered call for images only PDF-exporting users ever see, and no
  p95 could change that verdict; a fast unnecessary call is still unnecessary. Moved to
  `POST /api/day-photos`, fetched when the user presses Download.
  ⚠️ The measurement gap itself is **not** closed. `PEXELS_API_KEY` is still absent from local
  `.env`, so `get_day_photo()` still returns at its no-key guard locally and the 0.3ms figure is
  still not evidence (the key is set on Railway, not locally — that correction stands). It now only
  matters for costing the PDF path, not generation.
- 🔴 **The retry-cascade bullet understated it — this is the real finding.** It said "no cap on
  worst-case wall-clock"; there *is* a cap, and that is the problem. The backoff is 5+10+20+40 =
  **75s of sleeping per model** (225s for all three), while `routers/itinerary.py` caps the whole
  call at `llm_timeout_seconds` — 30s by code default, **120s in both local `.env` and Railway**
  (checked, since a Railway variable overrides a code default — the `NOMINATIM_USER_AGENT` lesson).
  So `_fallback_itinerary()`'s cache → RAG-skeleton → mock ladder, which only runs after *every*
  model is exhausted, **is unreachable under sustained transient errors** — the user gets
  `LLM_TIMEOUT` instead of the degraded-but-real itinerary built for that exact case.
  **Deliberately NOT fixed:** shorter schedule vs. a deadline threaded into the cascade vs. fewer
  attempts is a product call, and choosing before the instrumentation reports the real
  transient-error rate would be another guess. Arithmetic pinned by test, documented at
  `max_attempts`, and filed as its own row in `scaling-tech-challenges.md` §4.

**Follow-on, not done:** only this one endpoint is instrumented. `core/timing.py`'s `track()` is
endpoint-agnostic and no-ops when untracked, so extending it to the other LLM-backed endpoints is
cheap. Still no APM, no dashboards, no percentile aggregation.

**6. 📱 NEW (2026-07-28) — verify voice on real iOS and Android, then extend the voice lists from
that data.** Shipped v10.45.0 without this: Android and iOS are the bulk of the users and **neither
is measurable from a Windows dev box**. Everything needed is already committed — `app/dev/voice` is
a `noindex` diagnostic built for exactly this. **This is a data-collection task, not a coding task;
the coding only starts at step 5.**

**Steps:**

1. **Serve the app somewhere the phone can reach.** Either deploy to Vercel and use the live URL,
   or run `npm run dev -- --host` and hit `http://<dev-machine-LAN-IP>:3000` from a phone on the
   same Wi-Fi. `localhost` will not work from the phone.
2. **On a real iPhone (Safari)**, open `/dev/voice`. Do all three:
   - Read the **What Anya would use** section — note the selected voice and whether it is
     classified `female`, `male` or `unknown` for **both** English and Hindi.
   - Tap **Speak English sample** and **Speak Hindi sample**. Confirm audio actually plays, and
     whether the Hindi one sounds like a Hindi speaker or an English voice mangling Devanagari.
   - Tap **Run delayed-speech test**. 🔴 **This is the important one.** It waits a second and then
     speaks with no user gesture on the stack — exactly how Anya's real replies arrive, after an
     awaited API call. `SILENT` means WebKit's gesture restriction is real here and the
     zero-volume priming utterance in `useVoice.primeSynthesis()` is load-bearing. `spoke` means
     the priming is harmless insurance. Desktop reports `spoke`, which proves nothing about iOS.
3. **On a real Android (Chrome)**, repeat all of step 2.
4. **Hit *Copy report* on each device and save both outputs**, labelled by device and OS version.
   The report carries `userAgent`, capability flags, the delayed-speech result, and every voice
   with `name | lang | guessed gender | localService | voiceURI`.
5. **Only now, extend `apps/web/lib/voice.ts`.** Add any newly-seen female/male voice names to
   `FEMALE_VOICE_TOKENS` / `MALE_VOICE_TOKENS`, and add a regression test using the **real captured
   voice list** for that device — the same way `voice.test.ts` already pins the measured Windows
   list and asserts Heera over Ravi.

**⚠️ The caution that matters most here.** Android's Google TTS voices arrive with **no personal
name and no gender token** — `"Google हिन्दी"`, `"Google English (India)"` — so the curated name
lists cannot match them at all and selection falls through to the platform's own ordering. It
usually lands on a female Hindi voice, but **that is Google's default landing right, not this code
getting it right**, and the two must not be conflated in the docs.

The one place a signal *might* exist is the `voiceURI`, which on Android looks like
`hi-in-x-hia-local` / `hi-in-x-hid-network`. 🔴 **Those `x-hia` / `x-hid` variant codes are
undocumented. Do NOT invent a gender mapping for them — not from pattern-matching, not from
plausibility, not because an LLM (including me) suggests one.** The only acceptable basis is
listening to each variant on a real device and recording what it actually sounds like. A wrong
mapping is worse than no mapping: today an unrecognised voice scores neutral and is still used,
whereas a wrong entry actively selects the wrong gender and looks authoritative in the code.

**Definition of done:** two saved reports (iOS + Android), a recorded yes/no on whether the iOS
gesture restriction applies, and either extended token lists backed by device tests or an explicit
note that no name-based signal exists on that platform.

**7. ✅ DONE 2026-07-29 — voice-mic states redesigned + every finding from a full E2E accessibility
audit fixed (shipped as v10.48.0).** Full write-up in `docs/UI_UX_AUDIT_2026-07-29.md`,
`TECHNICAL_DOCUMENTATION.md` §14 v10.48.0, `docs/system-design.md` §16 v10.48, and
`DESIGN_REVAMP_SUMMARY.md` (July 29, 2026 section). Started from two live user reports (issues
[#30](https://github.com/kunalsmathur-gif/wanderplanner/issues/30)/[#31](https://github.com/kunalsmathur-gif/wanderplanner/issues/31)):
the persistent language toggle clipped the mic icon on mobile (→ one-time per-session prompt
instead), and the mic button had one red/broken-looking state for idle, active and unsupported
alike (→ four distinct states). Follow-up pushback ("is red really the right active color?") was
answered with the `ui-ux-pro-max` skill against the app's own tokens plus a survey of top
voice-chat conventions (ChatGPT/Gemini/Siri all avoid red for "listening") — switched to emerald.

Asked next to run a full read-only `ui-ux-pro-max` audit across every surface, then, per explicit
direction, **fix every finding rather than a top-priority subset** — ~25 items across landing,
auth, wizard, dashboard/chat, itinerary view, account/admin, layout/voice, and comparison
components (ARIA labeling, focus trap/Escape/restore, 44px tap targets, `<img>` → `next/image`,
responsive-layout fixes, non-color-only status cues).

**Every UI/UX change was backed by a concrete regression + performance check, not asserted:**
`git diff apps/api` confirmed **zero backend files touched**; full backend suite run anyway on a
rebuilt Python 3.12 venv (committed `.venv` is 3.9, incompatible with `datetime.UTC`) — **917
passed / 6 skipped**; `tests/unit/test_itinerary_timing.py` re-run in isolation, **22/22**, to
confirm v10.47.0's LLM-latency instrumentation itself wasn't disturbed. `load_test_rag.py` was
deliberately **not** run — needs live Gemini/embedding keys and real cost, and nothing backend
changed for it to catch. Frontend: real before/after `next build` (fixes stashed vs. applied,
identical 14 routes) measured client JS **+0.6% raw and gzip** (+18KB / +5.6KB), fully attributable
to the added a11y code with **zero new npm dependencies**; `tsc --noEmit` clean; `vitest run` **126
passed** across 10 files (2 new: `UserMenu.test.tsx`, `ListeningOrb.test.tsx`).

**Filed, not fixed — pre-existing repo hygiene found incidentally:** the committed
`apps/api/.venv` targets Python 3.9 while the code requires ≥3.11; `requirements.txt` pins
`httpx==0.28.1` while `requirements-dev.txt` pins `httpx==0.27.0`.

**Not yet done:** none of this session's changes have been committed to git — everything is still
an uncommitted working-tree diff across ~21 files plus 2 new test files.

**8. ✅ DONE 2026-07-29 — the two repo-hygiene items filed above (v10.48.0) fixed, plus Qdrant
storage monitoring and a full Redis migration (shipped as v10.49.0).** Full write-up in
`TECHNICAL_DOCUMENTATION.md` §14 v10.49.0 and `docs/system-design.md`. Rebuilt local `.venv` on
Python 3.12, added a fail-fast `sys.version_info` guard to `main.py`, and aligned the `httpx` pins.
Added a calibrated Qdrant Cloud headroom check (scheduler job + admin dashboard card) — the first
estimate, based on vector-dimension math, undercounted real usage by ~4.4x against the live
console, so it now uses an empirically-derived bytes/point constant instead. Migrated share links
and the travel-tips cache off in-process dicts (which lost everything on every restart, and never
actually enforced the tips cache's claimed 1h TTL) onto a real Redis instance deployed on Railway,
with a periodic memory-headroom check that auto-flushes the cache past a configured ceiling.
Deleted `KNOWN_ISSUES.md`/`BUG_FIXES_SUMMARY.md` (stale, referenced a component removed months
ago). Suite **917 passed / 6 skipped**; ruff + mypy clean.

**🆕 New backlog item found along the way, not fixed here:** `services/geocode.py`'s
`_cached_geocode()` is decorated with `@lru_cache` but its body unconditionally `return None`s —
it has never actually cached a real geocode response, despite the module's docstring and
`docs/scaling-tech-challenges.md` describing a working geocode cache. When this is fixed, wire it
into the new `apps/api/core/redis_client.py` cache layer (same `get_cache()` used by share links
and travel tips) rather than reintroducing a process-local `lru_cache`, so it survives restarts
too.

---

## ✅ DO THIS NEXT — open items as of 2026-07-27 (v10.40.7)

Ordered by value. **Items 1, 2 (code + data), 3, 5 and 7 are done.** Item 2's re-ingestion data run
finished 2026-07-27 with `0 pending` on the real Qdrant Cloud cluster — see the session block below
for the last-mile bug it uncovered. The Resend email pipeline is now also confirmed working
end-to-end (a real password-reset was triggered against prod and completed). Item 3's
`PEXELS_API_KEY` is now set locally and on Railway, with a redeploy confirmed live. **Item 6 (domain
cutover) is also done** — `wanderplanner.org`/`api.wanderplanner.org` are live; see its entry for a
`COOKIE_SAMESITE` follow-up left deliberately undone and a critical unrelated Dockerfile bug found
and fixed along the way (`sentence-transformers` missing from prod, breaking itinerary generation).
Only item 4 remains, blocked on the user (YouTube key rotation in Cloud Console). Narrative and
evidence for each is in the session blocks below.

**1. ✅ DONE 2026-07-26 (v10.40.2) — the YouTube comment corpus is complete: 170/170 destinations.**
The final 90 went through on a fresh Pacific quota day: 90 ingested, **13,477 comments**. Verified
on the real cluster, not the run log — `youtube_comments` holds **25,347 points across 172
destinations** (was 12,429 / 84). 8 of the 90 failed on the first pass with Qdrant
`read/write operation timed out` — *not* quota — and all 8 succeeded on an immediate retry, so they
were transient. **The v10.40.1 resume fix is what made that recoverable**: the run reported
`remaining: 8` and left them pending, where the old code would have recorded them done and
abandoned them. Note a Qdrant-write failure still costs a `search.list` call, since the search
succeeded first — which against a 100/day cap is exactly why the resume semantics matter.

Keeping the quota facts below, since any future re-ingestion runs into them again.

<details>
<summary>Original item 1 — the quota constraint (still accurate)</summary>

The 2026-07-25 run covered 80 of 170. A 2026-07-26 retry **failed on all 47 destinations it
reached** and turned up the real constraint (full narrative in TECHNICAL_DOCUMENTATION §14 v10.40.1):

> 🔴 **`search.list` has its own hard cap of 100 calls per project per day**
> (`defaultSearchListPerDayPerProject`) — a *separate meter* from the 10,000 units/day that
> `core/config.py` and this file have been reasoning about. Against the quota that actually binds,
> the old default budget of 80 was 80% of the day, not the comfortable headroom the config comment
> claimed (it is now 100, matching the cap). **It resets at midnight Pacific**, not UTC and not
> IST — 08:00 UTC is still the *previous* quota day, which is exactly how the retry was launched
> into an empty tank.

The run is quota-bound, not time-bound: **90 destinations need 90 of the day's 100 calls.**
`youtube_daily_search_budget` was raised 80 → 100 to match the provider cap (holding back 20 was
reserving headroom the process cannot protect anyway — a concurrent prod cold-start spends from the
same project quota and never consults this window), so no override is needed. Run this **after
00:00 Pacific** (12:30 IST):
```bash
cd apps/api && venv/Scripts/python.exe scripts/ingest_youtube_full.py
```
Verify persistence against the real cluster afterwards (`youtube_comments` point count + distinct
destinations), not just the run log — it was 12,429 points / 84 destinations after run 1.

⚠️ **A failed run is no longer silent, but it is still expensive.** v10.40.1 fixed the resume state
so a failure stays *pending* instead of being recorded as done (it would otherwise have abandoned
those 47 destinations permanently), and a zero-comment result now logs `NO comments — stays
pending` at WARNING instead of the old success-shaped `0 comments ingested`. But
`search_travel_videos` still retries a 429 three times — see the carried-over list below — so if
anything consumes the day's quota first, the tail of the run burns 3 calls per destination
achieving nothing.

</details>

**2. ✅ DONE 2026-07-25 (v10.40.0) — the pool is ranked by prominence. What's left is the data run.**
Ranking was genuinely missing, but it was the *second* of two causes and would have changed nothing
on its own: **the Overpass query only ever asked for `node` elements**, and famous landmarks are
mapped as areas (Kiyomizu-dera, Kinkaku-ji, Ginkaku-ji are `way`s; Delhi's Jama Masjid a
`relation`). They were unreachable, not out-ranked. Fixed with a second prominence-filtered `nwr`
pass, tiered prominence selection, and a 25% per-category cap — which also settles the open
`MAX_CATEGORY_SHARE` question further down. Full narrative in the session block below and in
TECHNICAL_DOCUMENTATION §14.

**What remains is only the re-ingestion run**, since selection changes are ingestion-time only.
Resumable, no flags:
```bash
cd apps/api && venv/Scripts/python.exe scripts/reingest_prominence_ranking.py
```
**Re-run until it reports `0 still pending`.** A destination whose *prominence pass* failed is
deliberately left un-done and retried next run — Overpass 403s/504s are routine and the prominence
query is the heavier of the two. Bangkok hit exactly this on the first pass and was correctly left
on its old data rather than overwritten. The script gives up after 3 attempts per destination so a
genuinely unremarkable place can't loop forever. **This also subsumes old item 7** (Tokyo's
local-script names) — the same run re-fetches Tokyo.

#### Where the run actually stands (measured 2026-07-27 from the state file, not the run log)

✅ **DONE 2026-07-27 — `0 still pending`. The re-ingestion is complete on the real Qdrant Cloud
cluster.** Dropped the dead `overpass.openstreetmap.fr` mirror from
`osm_overpass_fallback_mirrors` first (it answered 403 to everything and was a guaranteed-wasted
rotation slot). Jaisalmer, Lyon, Montreal, Nice, Oslo, Pondicherry and Siem Reap all got real
prominence data on retry (Lyon/Montreal/Nice/Oslo landed 60/60). Amalfi and Medellin exhausted
their 3 attempts against permanently-degraded Overpass responses and were accepted on their
existing stored data, per the retry rule.

🔴 **Found and fixed a real bug in `ingest_osm_pois` (`scrapers/osm.py`) while running this**:
when *every* Overpass mirror failed on *both* passes (`pois` came back fully empty, as opposed to
merely non-prominent), the function returned `0` instead of falling back to the existing stored
count. `reingest_prominence_ranking.py`'s state loader requires `osm_count` to be truthy before its
"accept after 3 attempts" rule can fire, so a destination hitting this path (Medellin did, three
times in a row) would retry **forever** rather than ever being accepted. Fixed by extending the
existing "keep existing data" guard to cover the fully-empty-fetch case too, consistent with the
guards already just below it in the same function.

<details>
<summary>How the 29 were originally identified (2026-07-26)</summary>

The batch reached the end of the alphabet at 17:46 UTC (23:16 IST), having touched **all 169**. But
reaching a destination is not finishing it: replaying `_load_state()`'s own rule
(`osm_count and (prominent or attempts >= 3)`) gave **140 done, 29 still pending**, every one of
them at `attempt=1`.

⚠️ **Do not measure this run by "did every destination get a row".** All 169 have rows and all 169
have `stored > 0`, because the *base* OSM pass succeeded everywhere — count the ones carrying a
prominence signal instead. This is the same trap as v10.40.1's `0 comments ingested` run log and
v10.40.0's complete-but-wrong pool: the shape of the output looked finished, and the content was not.

**All 29 pending share one symptom: `prominent = 0` with `error = null`.** The base pass succeeded,
the prominence pass failed on every mirror (diagnosed below — it *failed*, it did not come back
empty), and the script correctly declined to call that done.
The list is not the thin rural places the retry rule was written for — it includes **Rome, Venice,
Paris, London, Sydney, Osaka, Taipei, Porto, Split, Vilnius**, which cannot plausibly have zero
`wikidata`-tagged features:

> Darjeeling, Jaisalmer, Lonavala, London, Lyon, Medellin, Montreal, Nainital, Nairobi, Nice, Osaka,
> Oslo, Paris, Pondicherry, Porto, Pushkar, Queenstown, Riga, Rishikesh, Rome, Shillong, Siem Reap,
> Split, Srinagar, Sydney, Taipei, Varanasi, Venice, Vilnius

(Amalfi had the same symptom and is *not* in the list — it exhausted its 3 attempts and was accepted,
per the rule above. Worth re-checking by hand, since the evidence now says its result was a failure
rather than a genuinely unremarkable place.)

</details>

**Two hypotheses tested and rejected — don't redo them:**
- *Not a throttling window.* Failures interleave with clean successes minutes apart: Rome `prom=0`
  at 15:30 UTC, San Francisco `prom=60` at 15:36 UTC. Successes and failures alternate throughout.
  (The state file's `at` is UTC — beware tooling that renders it in local IST, +5:30.)
- *Not partial degradation.* The outcome is near-binary — a destination gets `prominent=60` or
  `prominent=0`, with genuine middles (Oaxaca 7, Ooty 19, Phuket 49) rare. The prominence pass either
  wholly works or wholly returns nothing.

#### ✅ Diagnosed 2026-07-27 with live Overpass probes — the mechanism, and two wrong guesses

**The mechanism is confirmed, and nothing is broken in our code.** The prominence pass fails on
every mirror, so `_fetch_overpass` returns `None`; `prominence_ok` is then `False`, and
`ingest_osm_pois`'s data-loss guard (osm.py, "keeping the N POIs already stored rather than
overwriting them") **keeps the old pool and returns `existing_count`**. That is exactly the
`osm_count > 0, stored = 60, prominent = 0, error = null` signature — a *successful protection of
good data*, not a silent failure. The pre-v10.40.0 pool it preserved has no `prominence` payload
field at all, which is why the readback is 0 of 60 rather than merely low.

**Live mirror health** (Rome, the full 25-clause prominence query, 15km):

| mirror | result |
|---|---|
| `overpass-api.de` | **HTTP 504** in 13–16s, HTML body |
| `overpass.kumi.systems` | **ReadTimeout** after 122s (client cap is 120s) |
| `overpass.openstreetmap.fr` | **HTTP 403**, `"This service is only available to white-listed usages"` |

That 403 body is worth recording: the mirror is not rate-limiting us, it is **not open to public
use at all**. It will never answer, which makes the case to drop it from
`osm_overpass_fallback_mirrors` concrete rather than speculative — and note
`_PROMINENCE_FETCH_ATTEMPTS = 4` rotates over three mirrors, so **attempt 3 always lands on the dead
mirror and is guaranteed wasted**. Removing it buys a real third try, not just tidiness.

🔴 **Wrong guess #1 — "the prominence query is timing out."** Recorded above as the place to start,
on an elapsed-time correlation. Only partly right: one mirror does hit a client ReadTimeout, but the
dominant mode is a *fast* 504 (8–16s) from the gateway, which is a slot refusal, not a query running
to its 90s server-side limit. The timing correlation was real and the causal story drawn from it was
not.

🔴 **Wrong guess #2 — "radius is the lever."** Rome 504s at 15km but returns **1,023 elements at
10km**, which looked decisive. It is not — the very next destination refuted it:

| destination | 15km | 10km |
|---|---|---|
| Rome | 504 | ✅ 1,023 elements |
| **Paris** | ✅ **3,013 elements** | **504** |
| London | ✅ 2,797 | ✅ 2,166 |

Paris is the exact reverse of Rome and London works at both, so **the failures are stochastic
server-side availability, not query weight.** Do not "fix" this by lowering
`osm_prominence_radius_m` — the measurement above says it would not help and would cost real
coverage. Successful queries take 35–75s, so the 120s client timeout is adequate but not generous.

**Therefore the 29 are transient and re-running is the fix** — confirmed on a pending small town:
Pushkar, which failed in the batch, returned HTTP 200 on a fresh probe. No code change is required
to finish the run.

⚠️ **But mind the 3-attempt cap while re-running.** Each script run costs one attempt per
destination, and after three the destination is accepted *whatever* its prominence result — a
destination that is merely unlucky three times gets recorded as done on stale data. **That is what
happened to Amalfi**, and it is the one way a re-run can make things quietly worse. If a
destination is still failing after two runs, drop the dead mirror (above) before spending its last
attempt.

**Early live results** (first destinations through the new pipeline, real cluster): Kyoto's pool
went from 21 obscure temples + 20 small museums to Kiyomizu-dera, Kinkaku-ji, Ginkakuji, Ryōan-ji,
Nijō Castle and Katsura Imperial Villa, with 60/60 carrying a prominence signal and top category
share 0.35 → 0.25; Delhi gained Red Fort, India Gate, Jama Masjid, Lotus Temple, Chandni Chowk,
Purana Qila, Hauz Khas and Jantar Mantar (attractions 4 → 14, cinemas 4 → 1). **Hidden gems moved
for the first time on these destinations: Kyoto 0 → 3 (Byōdō-in, Kinkaku-ji, Murin-an), Goa 0 → 1
(Museum of Goa), and Delhi now correctly classifies Chandni Chowk as a crowd favourite** — the
exact POI the v10.39.0 audit found commenters naming 4× and the pool lacking.

**Next prominence signal, when this needs to go further:** Delhi is the weak case, and it's OSM's
data rather than the ranking. Humayun's Tomb carries only `wikidata` + a *Hindi* `wikipedia` tag —
no `heritage`, no `name:en` — so it scores 6, while the fully-tagged Sulabh Museum of Toilets
scores 8. Delhi barely uses `heritage`, so scores bunch at 6 and ties break on arrival order.
Kyoto, where `heritage=1` is used properly, ranks perfectly (Kinkaku-ji, Kiyomizu-dera, Ryōan-ji,
Nijō Castle, Byōdō-in all score 12). The fix is **Wikidata sitelink count** — how many language
Wikipedias describe a place, the classic fame proxy — free and batchable (50 ids/call) but a second
API and its own change. **Don't re-try the two ideas already measured and rejected:** scoring areas
above nodes made Delhi *worse* (10/14 → 9/14, losing Chandni Chowk), and relaxing the category cap
to 0.35 gained nothing across three cities.

**3. ✅ DONE 2026-07-27 — `PEXELS_API_KEY` supplied and live in production.**
⚠️ **Corrected 2026-07-29: it is set on Railway but is NOT in local `apps/api/.env`** (verified —
no `PEXELS` entry of any kind). That matters more than it looks: `get_day_photo()` returns at its
no-key guard locally, so **any local measurement of the day-photo fetch measures nothing**, which is
exactly what happened while instrumenting item 5. The paragraph below is kept as written for the
Railway half, which is accurate.

Set on Railway production via `railway variables --set`
(verified present with a masked `variable list`). Railway service redeployed (`railway redeploy`)
to pick up the new variable — confirmed `● Online` and `/health` returning 200 post-deploy. Day
photos should no longer silently fail to load in production.

~~`RESEND_API_KEY`~~ — **✅ done 2026-07-25 (v10.38.3).** `wanderplanner.org` bought at Spaceship
and verified with Resend (DKIM + return-path MX/SPF + DMARC live at the registrar);
`RESEND_API_KEY` and `EMAIL_FROM_ADDRESS=Wanderplanner <no-reply@wanderplanner.org>` set on
Railway. **✅ Smoke-tested 2026-07-27** — `POST /api/auth/password/forgot` triggered against prod
(`https://api-production-3e3e.up.railway.app`) for a real account, confirmed via Railway logs
(`POST https://api.resend.com/emails "HTTP/1.1 200 OK"`), and the user confirmed the email arrived
and the reset link worked end-to-end. Note the sending region is `ap-northeast-1`.

**4. Rotate the YouTube API key.** ✅ *The code side is fixed as of v10.40.3 — see below. Only the
rotation itself is left, and it is yours to do in the Cloud Console.*

**Original note — and why the mitigation recorded here was incomplete:**
This item previously said silencing `httpx` to WARNING in `scripts/ingest_youtube_full.py` had
closed the leak. **It had not.** On 2026-07-26 the key was written to a local log 47 more times, by
a different path: `raise_for_status()` embeds the full request URL — key and all — in its exception
message, and `scrapers/youtube_comments.py` logs that message on failure. Silencing httpx does
nothing about the scraper's own warning.

**Production remains genuinely unaffected** — `core/logging_config.py`'s `RedactionFilter` rewrites
`AIza…` to `[redacted-key]` before the formatter runs, and only standalone scripts using
`logging.basicConfig` bypass it. The 2026-07-26 log files were deleted. But the key has now been
written in the clear twice by two different mechanisms, so **rotation is worth doing rather than
optional**, and the real fix is to stop logging the URL at all:

✅ **Both done in v10.40.3, taking the preferred route:**
- `core/logging_config.py` gained `configure_script_logging()`, which installs the app's
  `RedactionFilter` on a plain-text console handler and pins `httpx` to WARNING. **All 12 scripts
  under `scripts/` now use it instead of bare `logging.basicConfig`**, so the class of bug is closed
  rather than this instance of it.
- `scrapers/youtube_comments.py` no longer interpolates the caught exception into its warnings (it
  logs `type(e).__name__`), since that message is what carried the URL.
- Also found while fixing it: `scripts/ingest_youtube_full.py` wrote `f"{type(e).__name__}: {e}"`
  into its **JSONL state file**, which no logging filter ever sees. `core/logging_config.py` now
  exposes a public `redact()` for exactly this — text bound for a non-log sink — and the script uses
  it.

**5. ✅ DONE 2026-07-26 (v10.40.2) — CI's mypy step is green: `Success: no issues found in 166 source files`.**
Two corrections to how this was recorded. **(a) It was never eval-specific** — `scripts/` has the
same no-`__init__.py` shape, and excluding `eval/` just moved the abort there. **(b) Only one of the
two candidate fixes touches runtime**: `explicit_package_bases` is a mypy-only setting with no
effect on import resolution, so the eval harness's `sys.path` manipulation is untouched and **no
eval re-run was needed** — the caution recorded here applied to the `__init__.py` option alone. It
now lives in `pyproject.toml` (so local and CI agree; `.github/workflows` unchanged), along with a
`venv/` exclusion that CI never needed but local runs did.

The abort was hiding **91 errors across 54 sites**, since mypy had never actually type-checked the
codebase. All cleared. **Three were real bugs** — a cancelled cold-start ingestion reading as a
*successful* one (`isinstance(result, Exception)` misses `CancelledError`, which is a
`BaseException`), and two in the comparison path (a `None` winner raising `ValidationError` and
killing the whole comparison; attribute access on a plain dict). Two more latent ones fell out of
harness code. Full detail in TECHNICAL_DOCUMENTATION §14 v10.40.2.

⚠️ **If you add a file under `eval/` or `scripts/`, mypy now type-checks it** — that's the point,
but it does mean CI can newly fail on code that would previously have been skipped.

**6. ✅ DONE 2026-07-27 — domain cutover to `wanderplanner.org` complete.**
Frontend now live at `wanderplanner.org` / `www.wanderplanner.org` (Vercel), API at
`api.wanderplanner.org` (Railway custom domain, cert verified). DNS added at Spaceship — nameservers
kept unchanged (Resend DKIM/SPF/DMARC unaffected): `A @ → 76.76.21.21`, `A www → 76.76.21.21`,
`CNAME api → l5qq36b6.up.railway.app`, plus the Railway ownership-verification TXT record.
`ALLOWED_ORIGINS` updated additively (old `wanderplanner-web.vercel.app` origin kept alongside the
new ones) and `FRONTEND_BASE_URL` flipped to `https://wanderplanner.org`, each followed by a Railway
redeploy and a `/health` check.

⚠️ **`COOKIE_SAMESITE` was deliberately left at `none`, not flipped to `lax`.** Frontend and API are
now same-site (`wanderplanner.org` / `api.wanderplanner.org` share the same eTLD+1), which would
make `lax` viable and slightly more secure — but `core/config.py`'s `_validate_cookie_settings_for_prod`
hard-codes the old cross-origin assumption and **raises at startup** if `cookie_samesite=lax` in
production. That's a real code change (relaxing/updating the validator), not just an env var flip,
and wasn't made — don't set `COOKIE_SAMESITE=lax` on Railway without first updating that validator,
or the app will fail to start.

🔴 **Also found and fixed while verifying the cutover, unrelated to domains**: `apps/api/Dockerfile`
had never installed `requirements-ml.txt` since it was created, so `sentence-transformers` was
missing from the production image — silently breaking itinerary generation end-to-end (both the
primary Gemini RAG path and its fallback chain need it for embeddings; see `core/embeddings.py`).
Fixed by installing only `sentence-transformers==3.0.0` directly in the Dockerfile rather than the
full ml requirements file — confirmed no production code under `chains/`, `routers/`, `services/`,
`core/` imports `langchain`/`groq`/`openai`/`anthropic`, so those stay eval-only/local-dev-only.
Verified live: `POST /api/generate-itinerary` now returns 200 and a real itinerary.

⚠️ **New non-blocking bug surfaced by the same verification, not yet fixed**: `core/analytics.py`'s
`log_event` fails on the `itinerary_generated` event with `TypeError: Object of type DestinationInput
is not JSON serializable` — the event's metadata carries a Pydantic model instead of a plain dict/
JSON-safe value. Doesn't block generation (itinerary still returns fine), but that analytics event
is silently never recorded. Needs `DestinationInput` serialized (e.g. `.model_dump()`) before being
put in `event_metadata`.

**7. ✅ DONE — Tokyo's OSM re-ingestion, closed by item 2's run.**
Tokyo was still 58/60 Japanese-script after failing every v10.39.0 attempt. The v10.40.0
re-ingestion re-fetches all 169 destinations through the same `_display_name()` fix, and Tokyo went
through on the first try: **60/60 Latin-script names, 60/60 carrying a prominence signal, top
category share 0.10** (Hama-rikyū Gardens, Rikugi Garden, Sumida Aquarium, Tokyo Sea Life Park,
Former Asakura Estate …). Verified by reading the stored payloads back off the cluster, not from the
run log. (`scripts/reingest_local_script_names.py` is now redundant — kept for provenance.)

⚠️ **Related finding worth acting on if Overpass keeps hurting:** `overpass.openstreetmap.fr`
answered **403 to 5 of 5 requests** during this session while the other two mirrors were serving —
it is hard-refusing us, not rate-limiting. v10.40.0 stopped that from wasting a backoff sleep
(`_is_hard_refusal` rotates off a 4xx immediately), but the mirror is still dead weight in the
rotation. If it stays refusing, drop it from `osm_overpass_fallback_mirrors` and find a
replacement.

**Also still carried over from earlier blocks (unchanged, detail further down):**
- ~~**`search_travel_videos` retries quota errors**~~ — **✅ done 2026-07-26 (v10.40.3).** 429/403
  are now terminal in the search path, matching what `fetch_video_comments` already did for 403, so a
  quota mishap costs one call per destination instead of three and burns no backoff sleep. A transient
  500 or dropped connection is still retried; both behaviours are covered by tests.
- 🆕 **Quota accounting is per-process, not per-project.** ⚠️ An earlier version of this bullet
  claimed the cold-start gate's 5/hour ≈ 120/day over-subscribes the 100/day cap on its own. **That
  was wrong** — every cold start goes through `search_travel_videos`, which checks the budget window
  first, so one process cannot exceed the budget in a rolling 24h however many cold starts fire.
  The real gap: prod, a manual script and an eval run each keep their *own* in-memory window and can
  collectively exceed the project's 100/day. Fully closing it needs a shared persisted counter — a DB
  write per `search.list` call. Deliberately not built, because v10.40.3 made the failure cheap and
  visible: a process meeting an exhausted quota spends one call per destination instead of three,
  logs at WARNING, and leaves the work pending. Revisit if that stops being true.
- ~~Price grounding: per-amount proximity matching~~ — **✅ done 2026-07-26 (v10.40.4).** The
  v10.39.0 template was the right one, and it surfaced the *same* underlying bug: keyword matching
  was bare substring, so FOOD's `"eat"` matched **"great"** — every "great views" snippet counted as
  food context. Now word-boundary anchored, and context is scoped to each amount's own sentence
  (widened only when that sentence names nothing bought, never past a competing kind of spending).
  Stay grounding restored for Paris/Jaipur via `_STAY_MIN_SAMPLES = 1`. Detail in
  TECHNICAL_DOCUMENTATION §14 v10.40.4.
- `_FOOD_MEALS_PER_DAY = 3.0` calibration — **still deferred, now with a measurement behind it
  rather than an assumption.** Completing the YouTube corpus (v10.40.2, 170/170 destinations) was
  expected to unblock this. It does not: across 8 destinations there are only **0–3 extractable food
  amounts each**, and `food_per_day_estimate_inr` returns `None` for all of them, before *and* after
  v10.40.4's filter change (`min_samples=2` is not met either way). **A complete corpus is not a
  dense one — food grounding is corpus-density-limited, not retrieval- or filter-limited.**
  Calibrating the multiplier from this would be picking a number again, which is what the deferral
  exists to prevent. The unblocker is denser price-bearing text (Reddit OAuth would help most), not
  more tuning.
- ~~Open user decision on the residual `MAX_CATEGORY_SHARE` failures~~ — **✅ CLOSED 2026-07-28.
  🔒 USER DECISION: accept the remaining three as real-world skew. Do not relax the gate, do not
  build anything further in `osm.py` for them, and do not re-open this.** Boston (0.65), Alleppey
  (0.633) and Sri Lanka (0.60) are places of worship because that is what is actually mapped there;
  a gate exception for "pilgrimage towns" would be a threshold fitted to three data points, and
  pulling in irrelevant POIs to dilute the share would make the pool worse, not better. **A gate
  failure on these three is expected output, not a regression** — if a future audit flags them,
  that is the gate working.

  **Mechanism, for context (settled in v10.40.0):** the third option was taken — a per-category hard
  cap in `osm.py` at 25% of the pool during selection, half the gate's 0.5 threshold. It removed the
  *artificial* skew (Paris metro, Bangkok/Delhi train stations) but deliberately **defers** over-cap
  POIs rather than discarding them, so a thin destination still fills its 60 from whatever it has.
  That is why real skew survives it, and that is the behaviour being accepted here rather than
  worked around.

  **✅ The four named for re-check have now been measured (2026-07-26, full run):** three of them
  **pass** the 0.5 gate and are off the list — Dharamshala 0.483, Khajuraho 0.471 (restaurant, down
  from 0.71), Mahabaleshwar 0.459. Across all 169, only **four** destinations exceed 0.5, and the
  distribution is healthy: 128 at ≤0.25, 24 in 0.25–0.4, 13 in 0.4–0.5.

  | destination | share | top category | prominence signal |
  |---|---|---|---|
  | Boston | 0.65 | place of worship | yes |
  | Alleppey | 0.633 | place of worship | yes |
  | Sri Lanka | 0.60 | place of worship | yes (5/60) |
  | **Paris** | **0.583** | **train station** | **none — `prominent=0`** |

  🔴 **Paris is not a genuine-skew case and must not be read as one, so the decision above does not
  cover it.** It was one of the 29 destinations whose prominence pass returned nothing at the time of
  that measurement, so its pool was selected without any prominence signal — the 0.583 train-station
  share is the *old* pre-v10.40.0 behaviour surviving, not the new cap failing on real data.

  ⏳ **The one thing still outstanding here is a measurement, not a decision.** Item 2's re-ingestion
  reached `0 pending` on 2026-07-27, so Paris now has prominence data, but **its share has not been
  re-measured since** — the 0.583 in the table above is stale. Re-run the completeness gate for Paris
  and record the new number; metro/rail density is exactly the artificial skew the cap was built for,
  so this is the case that says whether the cap works. If it still exceeds 0.5 *with* a prominence
  signal, that is a new finding and not covered by the accept-as-skew decision.
- Reddit ingestion still 403s in prod on every boot — ask whether the OAuth app review came
  through, then rewire `scrapers/reddit.py` to the authenticated API.
- Non-blocking timing note: the YouTube scheduler job uses `IntervalTrigger` with no `start_date`,
  so its **first fire is 14 days after boot** and any deploy resets that clock. Only Reddit is
  seeded at startup (`main.py::_seed_reddit`). Near-term prod YouTube ingestion therefore comes
  from the cold-start gate, or from running the script above.

---

## 🆕 TOP OF THE LIST — 2026-07-26 late session: Reddit is out, Wikivoyage/YouTube are in

**Decision taken 2026-07-26: Reddit is no longer a planned ingestion source.** The OAuth app review
never produced credentials (submitted 2026-07-16; on 2026-07-26 the bot account's `/prefs/apps` page
showed **no developed app at all**, only Reddit's own "DevPlatform Actions" authorisation). Prod has
403'd on every boot since the Qdrant Cloud migration. Rather than keep waiting on an external
approval with no ETA, price/sentiment grounding now rests on Wikivoyage + YouTube.

**⚠️ This was NOT the blocker it was billed as.** An earlier note in this file called Reddit "the
biggest unblocker for food price grounding". That was wrong, and the measurement is below — no
existing corpus had price density, so Reddit was never the deciding factor.

### The measurement that drove the decision (don't re-derive this)

Money-shaped text present in each corpus, measured live 2026-07-26 with a regex *looser* than the
extractor's:

| corpus | chunks/destination | money-shaped | conclusion |
|---|---|---|---|
| `youtube_comments` | 126–234 | **1–3** | wrong medium — people don't quote prices in comments |
| `wiki` (Wikivoyage) | 10–48 | 0–6 | under-ingested, see item A |
| `itinerary_corpus` | 0 | 0 | **4 points total, effectively dead** |

Tokyo's 2 qualifying comments yielded 6 amounts, so **the extractor was capturing nearly everything
present** — the shortfall was never extraction recall. `food_per_day_estimate_inr` returned `None`
for all 8 destinations spot-checked, before and after v10.40.4.

### A. 🔴 Wikivoyage `<section>` parser fix — committed; the data run is what's left

`_parse_sections` collected only `("p", "ul", "li")`. MediaWiki wraps every **subsection** in a
`<section>` element, and Wikivoyage keeps its Budget / Mid-range / Splurge **priced listings**
there — so the parser kept nothing but each section's intro prose. One-word fix (add `"section"`),
measured live:

| | chunks | food amounts |
|---|---|---|
| **Jaipur** | 10 → **141** | 3 → **116** |
| Paris | 32 → 156 | 4 (unchanged) |
| Bangkok | 31 → 143 | 0 (unchanged) |

**State (corrected 2026-07-26): the edit is committed and pushed** — `9fa3106` on
`feat/frontend-scaffold`, merged to `main` as `deaed8b`, both in sync with origin. The paragraph
here previously said "in the working tree, uncommitted"; that is stale.

⚠️ **Still genuinely outstanding: the full suite.** The note above recorded that only `ruff` and the
28 Wikivoyage tests had been run, and the commit does not show otherwise — so **run the full suite
against `9fa3106` before building on it**, rather than assuming the commit implies it passed.

Then note this is **ingestion-time only**: it does nothing until destinations are re-ingested, which
is a third data run. ✅ **The "must not overlap the prominence run" constraint is now LIFTED** — that
run finished at `0 pending` on 2026-07-27 (item 2), so this can be scheduled freely. Re-measure food
grounding afterwards — Jaipur should produce a real grounded figure for the first time.

### B. ✅ Big-city guides — district sub-articles — DONE 2026-07-29 (v10.51.0, issue #45)

Original note: "Paris and Bangkok gained chunks but no food amounts: their guides delegate listings
to district sub-pages (`Paris/Le_Marais`, `Paris/1st_arrondissement`, …) which the scraper never
fetches."

Shipped in `scrapers/wikivoyage.py` via `_discover_district_subpages()` +
`_scrape_district_subpages()`, capped by `settings.wikivoyage_max_district_subpages` (default 8,
`0` disables). Full write-up in `TECHNICAL_DOCUMENTATION.md` §14 v10.51.0. **Three corrections to
the note above, all measured rather than assumed:**

1. 🔴 **The proposed detection mechanism does not work.** Both this note and issue #45 assumed the
   parent guide *links* its district sub-pages. It does not — Paris/Bangkok/Tokyo/London render
   **zero** `/wiki/<City>/<District>` hrefs, and their Districts sections contain only
   `Special:Map` links. Discovery goes through `list=allpages&apprefix=<City>/` instead. A
   link-parsing build would have passed fixture-based unit tests and ingested nothing in prod.
2. ⚠️ **"Yield nothing" was already stale.** The §A `<section>` fix (`9fa3106`) had already taken
   Paris to 28 and Bangkok to 17 price-bearing chunks. The upside was real and *larger* than this
   note claimed, but the stated symptom had been fixed before the issue was picked up.
3. **`Paris/Le_Marais` does not exist** — verified MISSING via the API. `Paris/1st arrondissement`
   and `Bangkok/Sukhumvit` do. Don't hard-code example titles copied out of a note.

Live at the default cap, price-bearing chunks: Paris 28→123, Bangkok 17→67, Tokyo 11→31, **Delhi
8→65 (×8.1, the largest gain and an India destination)**; Jaipur unchanged at 74 with 0 districts,
the non-hub control. ⚠️ **Ingestion-time only — the re-ingestion data run has NOT been done**, so
none of this is live on the cluster yet.

### C. ✅ YouTube transcripts + video descriptions — SHIPPED v10.41.0 (2026-07-27)

The premise held. New `scrapers/youtube_narration.py` → `youtube_narration` collection, wired into
`core/cost_grounding.py::_price_collections()`. Live on Jaipur:

| corpus | chunks | money-shaped |
|---|---|---|
| `youtube_comments` | 149 | **0** |
| `wiki` | 10 | 2 |
| **`youtube_narration`** | **110** | **24** |

Costs essentially nothing: discovery makes **no `search.list` call** (video IDs are read back out of
`youtube_comments`, which v10.40.2 populated for all 170 destinations), transcripts need no key, and
descriptions are 1 unit per 50 videos. **Separate collection on purpose** — `services/gems.py`
counts mentions as independent community signal, and a vlogger naming a place eight times in one
video is one voice; merging would have misclassified gems as crowd favourites. A test asserts
narration is in the price path and *not* in gems.

**Two real bugs fell out, both of which were hiding the value:**
- 🔴 **Transcripts were English-only.** Most Indian destination vlogs have **no English caption
  track**, only a Hindi auto-generated one — an India-first product was discarding its own primary
  market. `languages` is now a parameter; narration passes `("en", "hi")`. Jaipur went 21 → 110
  chunks, 1 → 24 money-shaped on this fix alone.
- 🔴 **`\b` silently fails on Devanagari.** Matras are not `\w` characters, so `\bखाना\b` never
  matched while `\bहोटल\b` did. **0 of 24** Hindi price chunks matched any food/stay keyword.
  `core/keyword_match.py` now uses explicit lookarounds; ASCII behaviour verified unchanged. This is
  the *third* distinct bug in this keyword-matching family (v10.40.4/5/6 were false positives; this
  is a false negative introduced by the fix for them). **General rule now recorded: a boundary rule
  written for one script is an assumption about every script in the corpus.**

**⚠️ Honest limits — do not read this as "food grounding is solved."** Jaipur food-context matches
went 0 → 2 of 24 and stay 0 → 6, but `food_per_day_estimate_inr` still returns `None` for Jaipur:
two matching *chunks* don't yield the two in-bounds *amounts* `min_samples` needs after per-amount
sentence scoping. `_FOOD_MEALS_PER_DAY` calibration stays deferred.

**Next step here — the data run, which has NOT been done.** Only Jaipur was ingested, as the
verification case. Resumable, no flags:
```bash
cd apps/api && venv/Scripts/python.exe scripts/ingest_youtube_narration.py
```
Then re-measure food/stay grounding across destinations to see whether density now clears
`min_samples` anywhere. Narration is also **not on the scheduler** yet — deliberate, pending a look
at what a full run costs in wall-clock time.

### D. ✅ Documentation sweep — Reddit removal (DONE 2026-07-27)

All seven listed docs updated, **plus `README.md`**, which this list missed and which is the most
public of the lot (16 mentions, including the feature list and architecture diagram). The sweep
found **275 mentions across 18 files**, not the 7 files recorded here — enumerating rather than
triaging by eye is what caught the README.

**Files updated (current-state claims only):** `README.md`, `docs/DEMO_DAY_FAQ_CHEATSHEET.md`,
`docs/rag-strategy.md` (+ a status banner at the top, since the file is too long to read linearly),
`docs/system-design.md`, `docs/PRD.md`, `docs/scaling-tech-challenges.md`,
`TECHNICAL_DOCUMENTATION.md`, `docs/itinerary-generation-flow.md`.

**Second pass, same day:** `docs/GTM_STRATEGY.md` (all 5 mentions — moat claim, Bet 1, gem scoring,
budget-estimator proof point, roadmap row), `docs/pitch-deck/index.html` (the live deck, both
mentions), and `docs/MARKET_RESEARCH.md`. An earlier version of this list put those three under
"left alone"; that was superseded.

🔒 **`docs/MARKET_RESEARCH.md`'s remaining Reddit mention is DELIBERATE — do not remove it.**
Confirmed by the user 2026-07-27. The persona line ("high trust in peer/community content")
describes where the **user** places trust, which is a true market observation about Indian
travellers and is completely independent of which sources we ingest. Stripping it would make the
market research *wrong*, not cleaner. It carries an inline annotation saying so; keep both.

**Deliberately left alone — rewriting them would falsify the record:**
- **Changelog / version-history sections** (`TECHNICAL_DOCUMENTATION.md` §14, README's version log,
  rag-strategy's "✅ DONE" roadmap rows). These describe what shipped at the time and were true then.
- **Dated audit artifacts**: `BUG_FIXES_SUMMARY.md`, `docs/UI_UX_AUDIT_2026-07-13.md`,
  `E2E_SANITY_REPORT.md`, `test_e2e_sanity.md`, `MULTI_CITY_IMPLEMENTATION.md`,
  `docs/STARTUP_EVALUATION.md`, `docs/eval-set.md`.
- **`docs/pitch-deck/index-2026-07-11-evaluation.html`** — a dated snapshot of the deck. One of its
  two mentions is also the *user-behaviour* kind ("Users juggle Google Maps, Skyscanner, Reddit
  threads, and spreadsheets"), which describes the problem being solved and is true regardless.
- **Code-behaviour documentation that is still literally true**: `scrapers/reddit.py` still exists,
  still defines the live `KNOWN_DESTINATIONS` list, and the `reddit` collection is still *read* by
  `services/search.py`, `services/gems.py` and `core/cost_grounding.py::_price_collections()`.
  Descriptions of those read paths were kept and annotated, not deleted.

⚠️ **Still true and still deliberate: no code was touched.** The read paths degrade to empty rather
than erroring, so leaving them costs nothing. Removing them is a separate change.

**Two things worth knowing for the next doc pass** — ✅ **both swept 2026-07-28.** They were left as
out of scope at the time; the sweep enumerated rather than triaging, and both were larger than filed:
- ~~Qdrant described as "(in-memory)"~~ — **done.** `docs/system-design.md`'s architecture diagram
  now says `(Cloud)`, with the full collection set and the `:memory:`-is-local-only caveat spelled
  out below it; `TECHNICAL_DOCUMENTATION.md`'s tech-stack table and `README.md`'s `QDRANT_URL` row
  (which now documents `QDRANT_API_KEY` too) are corrected. 🔴 **The real find was
  `docs/scaling-tech-challenges.md`**, which the filed item didn't mention: it still described
  `:memory:` as the *current* architecture in its one-line summary and carried three open risk rows
  saying it "must be fixed before any multi-instance deployment" — a risk doc claiming an existing
  fix was outstanding. Marked resolved with a dated banner, keeping the findings in place because
  the reasoning still applies to the genuinely-unresolved in-process state.
- ~~"10,000 units/day" YouTube quota~~ — **done.** Corrected in `README.md` (whose
  `YOUTUBE_DAILY_SEARCH_BUDGET` row also still said the default was 80 — it has been 100 since
  v10.40.1), `DEMO_DAY_FAQ_CHEATSHEET.md`, `scaling-tech-challenges.md`, `core/config.py`'s
  docstring and `scrapers/youtube_comments.py`'s module docstring.

**Three further stale claims fell out of the same sweep, all fixed:**
- 🔴 `docs/rag-strategy.md` still carried the **retracted** "cold-start gate over-subscribes the cap
  on its own" claim. v10.40.3 corrected that in three docs and **missed this one** — every cold start
  routes through `search_travel_videos()`, which checks the budget before spending. Annotated as a
  second correction rather than silently rewritten, since it is a correction of a correction.
- 🔴 `docs/PRD.md` §6.1 still described Reddit as an active scheduled source and the YouTube Data API
  path as "**planned (not yet built)**" — it shipped in v10.30.0 and covers all 170 destinations.
- `scrapers/youtube_comments.py`'s docstring still said YouTube was a stand-in "while Reddit stays
  blocked on approval". Reddit was dropped outright on 2026-07-26.

⚠️ **New item this raised, not fixed:** the Qdrant Cloud **free tier is 1GB and nothing monitors
headroom** against it. `youtube_comments` alone is ~25k points / 172 destinations and
`youtube_narration` is growing beside it. The first symptom of hitting the ceiling would be write
failures mid-ingestion. Filed in `scaling-tech-challenges.md` §4.

⚠️ **Docs only — do not rip Reddit out of the code in the same pass.** `scrapers/reddit.py`,
`services/gems.py`'s multi-source blend, and `core/cost_grounding.py::_price_collections()` all
still reference the `reddit` collection, and it still holds real ingested points. The collection
degrades to empty rather than erroring, so leaving the code path costs nothing and keeps the option
open if Reddit's API access ever reopens. Removing it is a separate, deliberate change.


---

## 2026-07-26 session (latest) — the backfill was metering against the wrong quota (v10.40.1)

Taken up as "finish the YouTube backfill". The run failed on **all 47 destinations it reached**
while logging `0 comments ingested` for each — no exception, no failure count, a clean-looking run
log. What gave it away was reading the *content* rather than the shape of the log: Paris, London,
New York and Mumbai do not have zero travel-vlog comments.

**1. 🔴 The binding quota is not the one the code models.** `search.list` has a dedicated cap of
**100 calls per project per day** (`defaultSearchListPerDayPerProject`), a separate meter from the
10,000 units/day everything in the codebase reasons about. `core/config.py`'s comment — "80
searches ≈ 8,000 units … leaves real headroom" — is measuring the quota that never binds. Against
the one that does, the default budget of 80 is 80% of the day. Diagnosed by probing three endpoints:
`videos.list` and `i18nLanguages.list` returned 200 (key fine, project not blocked) while
`search.list` returned 429 naming the metric and its limit of 100.

**2. 🔴 The resume state recorded failures as completed work.** `_load_done()` keyed every row as
done regardless of outcome, so all 47 zero-comment destinations would have been skipped on every
future run — silently abandoned rather than retried. This contradicted the rule the module's own
docstring states and the scheduler follows (leave the timestamp NULL; an empty result is a
*retryable no-op*, never a recorded-but-empty success). Fixed to the same idiom
`reingest_prominence_ranking.py::_load_state` already used: done means comments were actually
ingested, with a 3-attempt cap so a genuinely un-vlogged destination can't spend a search call every
run forever. The 47 bogus rows were stripped (backed up first, and only after asserting every
retained row carried a non-zero count). **Nothing had reached Qdrant, so no data was lost** — the
failure was entirely upstream of ingestion.

**3. ⚠️ Quota-day arithmetic, since it was got wrong twice in one session.** These quotas reset at
**midnight Pacific**. The first backfill ran 2026-07-25 08:13 UTC = 01:13 PDT on the 25th; the retry
went out 2026-07-26 03:49 UTC = **20:49 PDT, still the 25th** — same quota day, ~20 hours later by
the wall clock and zero days later by the meter. The 80 calls already spent were still on the books,
which is why the very first request 429'd.

**4. Two real bugs found and deliberately left** (scope kept minimal; both now in the carried-over
list above): `search_travel_videos` retries a 429 three times, tripling the cost of any quota
mishap; and the API key reaches standalone script logs through `raise_for_status()`'s exception
message, which embeds the full URL — a *different* path from the httpx one that item 4 recorded as
already fixed. Production is unaffected by the latter (`RedactionFilter`), and the local log files
were deleted.

**Generalisable, and it is the same shape as v10.40.0's "complete but wrong" POI pool:** a rate
limit you have not actually looked up is an assumption, and a run log full of zeros is not evidence
of an empty corpus. Both sessions in a row, the failure was a check that measured the wrong thing
and passed.

---

## 2026-07-25/26 session — the POI pool: landmarks were unreachable, not out-ranked (v10.40.0)

Taken up as "rank the OSM POI pool by prominence" (the previous session's top item). Ranking was
genuinely missing — but **it was the second of two causes, and on its own it would have fixed
nothing.**

**1. 🔴 The Overpass query only ever asked for `node` elements.** Famous landmarks are mapped as
*areas*. A live probe settled it in one shot: Kiyomizu-dera, Kinkaku-ji and Ginkaku-ji are `way`
elements, Delhi's Jama Masjid a `relation`. They were never candidates for the 60 slots at all, so
no amount of ranking would have surfaced them. The tell was already in the code — the query asked
for `out center` and the parser read `element["center"]`, both meaningless for nodes. Only the
query kind was missing.

**2. ⚠️ The obvious one-line fix is a trap that looks like it works.** Switching the broad query to
`nwr` does *not* work: Overpass's `out <limit>` truncates in element-type order, **nodes first**, so
a capped `nwr` query returns an all-node result and silently drops every way and relation —
verified, an `nwr` query for Kyoto capped at 3000 came back 3000/3000 nodes. Removing the cap is
the other extreme and simply times out in a dense city. **Generalisable: when a result cap and a
type filter interact, check what the cap truncates *by* — a full-looking result set is not evidence
the filter worked.**

**3. ✅ Prominence is fetched as its own pass.** `nwr` + `["wikidata"]`, 15km, **no cap** (a cap
would reintroduce the truncation above). The filter is what makes an uncapped query affordable:
Delhi 159 elements, Kyoto 345, Bangkok 668. A wider `wikidata|wikipedia|heritage` regex filter was
measured and rejected — +7 elements out of 836 for Istanbul at double the time, and a full timeout
on Bangkok.

**4. ✅ Selection by prominence tier, then a per-category cap.** With the prominence pass merged but
round-robin unchanged, Delhi came back with 4 cinemas and 4 art galleries but only 4 attractions —
**round-robin gave a cinema exactly the same claim on a slot as the Red Fort.** Selection now runs
in descending prominence tiers, round-robinning across categories *within* each tier, then caps any
category at 25% of the pool. With no prominence signal anywhere the pool collapses to one tier and
behaves exactly as before, so the old anti-domination guarantee is preserved rather than replaced.

**5. 🔴 New data-loss guard, found by being bitten by it.** Delhi's prominence query 403'd on all
three mirrors mid-verification, and the broad-pass-only fallback returned a **full 60 POIs, well
distributed across 22 categories, top share 0.07 — and containing none of Red Fort, Humayun's Tomb,
Qutub Minar, India Gate, Lotus Temple, Jama Masjid or Lodhi Gardens.** Every existing health check
passed it, including the thin/dominated data-loss guard. The prominence pass's success is now
tracked explicitly (it *cannot* be inferred from the POIs) and won't overwrite an already-populated
destination. **Generalisable, and the same shape as the v10.37.0 mis-geocoding lesson: a
completeness check that counts and distributes can't see a pool that is complete but wrong.**

**The tuning was measured, not guessed** — raw Overpass results for Delhi/Kyoto/Bangkok cached once,
then 8 variants compared offline on identical inputs, scored by how many genuinely famous landmarks
land in the final 60. **No variant beat the shipped one (25/37).** Two that sound obviously right
are *worse* and are recorded so nobody re-tries them: scoring areas above nodes (Delhi 10/14 →
9/14, losing Chandni Chowk to traced buildings), and relaxing the cap to 0.35 (looked like +1 on
two cities, evaporated at three).

**Live results so far** (re-ingestion still running at time of writing):

| | before | after |
|---|---|---|
| Kyoto pool | 21 obscure temples + 20 small museums, no Kiyomizu-dera | Kiyomizu-dera, Kinkaku-ji, Ginkakuji, Ryōan-ji, Nijō Castle, Katsura Imperial Villa; 60/60 with a prominence signal; top share 0.35 → 0.25 |
| Delhi pool | 7 train stations, no Red Fort | Red Fort, India Gate, Jama Masjid, Lotus Temple, Chandni Chowk, Purana Qila, Hauz Khas, Jantar Mantar; attractions 4 → 14, cinemas 4 → 1 |
| Bangkok pool | 12 train stations, no Wat Arun | Wat Arun, Grand Palace, Chatuchak, Jim Thompson House; 60/60 prominent |
| Istanbul pool | 6 train stations, no Grand Bazaar | 60/60 prominent, top share 0.25 |
| Tokyo | 58/60 Japanese-script (failed 3 v10.39.0 runs) | **60/60 Latin-script, 60/60 prominent, share 0.10** — closes old item 7 |
| Hidden gems | Kyoto 0, Goa 0, Delhi 0 | **Kyoto 3** (Byōdō-in, Kinkaku-ji, Murin-an), **Goa 1** (Museum of Goa), **Delhi** now classifies **Chandni Chowk** as a crowd favourite — the exact POI the v10.39.0 audit found commenters naming 4× and the pool lacking |

**What the cap does *not* fix, measured:** it defers over-cap POIs rather than discarding them, so a
destination that lacks other categories still ends up dominated. Alleppey came back at **0.63
top-category share (38/60 places of worship)** — that is genuinely what is mapped there. The
artificial skew (Paris metro, Bangkok/Delhi train stations) is gone; the real skew is not, and
whether to accept it or relax the gate for pilgrimage/backwater towns is still a product call.
*(🔒 Resolved 2026-07-28 — the user accepted the real skew as-is. See the open-items list above; the
gate is not being relaxed and nothing further is being built in `osm.py` for it.)*

Suite **612 passed / 6 skipped / 0 failed** (+27). Ruff clean.

### Still open after this session

- **The re-ingestion run itself** — item 2 at the top. Re-run until `0 still pending`.
- **Delhi's residual weakness is OSM's data, not the ranking** — Humayun's Tomb carries only
  `wikidata` + a Hindi `wikipedia` tag and scores 6, below the fully-tagged Sulabh Museum of
  Toilets at 8. Wikidata sitelink count is the signal that would fix it. Detail in item 2.
- **`overpass.openstreetmap.fr` is hard-refusing us** (403 on 5/5) — see item 7.

---

## 2026-07-25 session — hidden-gem name matching, and the ingestion bug underneath it (v10.39.0)

Taken up as "gem-intel name matching under-fires". **The premise did not survive a look at the real
data**, which is the main lesson from the session: a read-only audit of 8 destinations' live
`osm_pois` + `youtube_comments` showed normalisation and aliasing recover about **one POI per
destination**, and the aggressive part of it recovers as many false matches as real ones. Three
other causes were doing the damage.

**1. 🔴 OSM POI names were being stored in the local language.** `scrapers/osm.py` read
`tags.get("name")`, which OSM defines as the name *in the local language* — so Kyoto's POIs went
into the cluster as 清水寺 and Cairo's in Arabic. Every consumer treats that field as text an
English-speaking traveller would recognise: gems searches for it in comments, `poi_pinning` matches
it against LLM-proposed names, **and the itinerary renders it to the user**. So this was never a
gems bug; those destinations were degraded across the board and English users were being shown
Japanese, Greek and Thai place names. Audit across all 170 ingested destinations: **17 with ≥10% of
names in a non-Latin script, 9 above 66%** (Tokyo 58/60, Taipei 56/60, Seoul 56/60, Athens 54/60,
Tbilisi 53/60, Osaka 53/60, Cairo 50/60, Kyoto 49/60, Bangkok 40/60). Now prefers `name:en`, then
`int_name`, then a Latin fragment parenthesised inside an otherwise non-Latin name — a live
Overpass probe confirmed `name:en` exists on 43 of 107 named Kyoto nodes.

**2. 🔴 Gem candidates were dominated by transport nodes.** Istanbul's entire live gem list was
Kadıköy, Karaköy and Beyoğlu — three metro stops. Jaipur's second-strongest match was a POI named
"Railway Station"; Khajuraho's strongest was a station called "Khajuraho". `train station`/`airport`
types and any POI named after the destination itself are now excluded from both lists.

**3. ✅ New `services/name_matching.py`**, shared with `poi_pinning.py` (which had its own half of
the same logic). Diacritic-folded, word-boundary-anchored, with variants for OSM's actual naming
habits. **Two latent bugs fell out, both live in the pinning path too:** NFKD-based folding
*deleted* letters it cannot decompose, so Turkish "Kadıköy" became "kad koy" (same for `ø ł đ ß æ
œ þ`); and apostrophes were split rather than removed, so "St Mary's" became "st mary s", matching
neither spelling. A third: `_sentiment_around` hand-replaced only `,`, `.` and `!` before splitting,
so a lexicon word touching any other punctuation — `a real gem;`, `(peaceful)` — scored nothing.

**4. ✅ Re-ingested 16 of 17 affected destinations** via new
`scripts/reingest_local_script_names.py` (resumable JSONL state). Latin-script names across that
set went **49% → 82%**; Kathmandu and Chiang Mai are now 60/60, Bangkok 59/60, Tbilisi 58/60, Seoul
and Cairo 57/60. **Tokyo failed all attempts** (Overpass 504/403 — see item 7 above); its existing
data was left intact rather than overwritten with a partial fetch.

**Live result on unchanged data:** Kochi 0 → 1 gem (Marine Drive), Khajuraho's train-station "gem"
replaced by a real one (Matangeshwar Temple), Jaipur's "Railway Station" noise gone with Hawa Mahal
retained, Istanbul's three metro stops correctly gone to zero.

Suite **585 passed / 6 skipped / 0 failed** (+16). Ruff clean.

### Still open after this session

- **The POI pool is now the ceiling** — consolidated as item 2 in the checklist at the top, with the
  per-destination evidence. Kyoto proves it cleanly: after re-ingestion its pool has proper English
  names (Renge Temple, Shiramine Jingu, Koshoji Temple, Kyoto Tower) and still returns zero gems,
  because Kiyomizu-dera, Fushimi Inari, Kinkaku-ji and Arashiyama are **not in the pool at all**.
- **Tokyo still needs its re-ingestion** — item 7 above.
- **The refinement eval was not re-run.** `services/poi_pinning.py::_normalize` changed behaviour
  (diacritic and apostrophe fixes), and `eval/refinement_scoring.py` uses it via `_names_match`.
  Both changes are strictly more permissive — an exact match now lands where the fuzzy-ratio
  fallback used to, so scores should hold or improve — but that is reasoning, not a measurement.
  Worth a run when the eval harness is next exercised (remember to copy live raw results to a dated
  `live_YYYYMMDD_*.json` **before** the offline gate overwrites them).

---

## 2026-07-25 session — prod env audit, dead prod guards fixed, first full YouTube backfill (v10.38.2)

Started as "is `YOUTUBE_API_KEY` set in prod?" and turned up two live misconfigurations plus a
safety net that had never once fired. Suite **569 passed / 6 skipped / 0 failed**, ruff clean.

**1. 🔴 The production guards were not running in production.** `core/config.py`'s cookie and
`JWT_SECRET` validators both gated on `os.getenv("ENVIRONMENT", "development") != "production"`,
and **Railway never sets a bare `ENVIRONMENT`** — it injects `RAILWAY_ENVIRONMENT_NAME` and
`RAILWAY_ENVIRONMENT`. So the v10.26 fix for the cross-site cookie bug (the one where a signed-in
user got bounced to sign-in mid-generation and their purpose/budget didn't persist) has been
*inert on every prod boot since it was written*. Prod is correct today only because
`COOKIE_SAMESITE=none` is set by hand — delete it and the app would boot happily on the `lax`
default and the bug returns silently. Fixed with a new `is_production()` helper recognising all
three markers. **The tests were the reason this hid so well: every one of them set
`ENVIRONMENT=production` itself, so they proved the guard works when told it's production and
never checked that the deployment says so.** Added 6 tests including the no-cookie-config-under-
Railway-production case and a staging-is-not-production case.

**2. Prod env vars corrected (live).** `YOUTUBE_API_KEY` was absent → set. `NOMINATIM_USER_AGENT`
was still the old `wanderplan/1.0` → **a Railway variable overrides the `core/config.py` default,
so the 2026-07-21 Wikimedia-403 fix never reached prod at all.** Now correct. **Generalizable: when
a fix changes a config default that also exists as a Railway variable, the variable wins — check
prod env, not just the code.**

**3. ✅ First full YouTube backfill: 80 destinations, 11,838 comments, 0 failures.** New
`scripts/ingest_youtube_full.py` (scheduler-identical ordering, resumable, budget-aware). Verified
live: `youtube_comments` now holds **12,429 points across 84 destinations**. Stopped exactly on the
80-search daily budget — **90 destinations remain, re-run the script tomorrow** (it resumes from
its JSONL state; no flags needed).

### Still open after this session

Consolidated into the **"✅ DO THIS NEXT"** checklist at the top of this file — items 1 (finish the
backfill, 90 destinations left), 2 (gem-intel name matching), 3 (Pexels/Resend keys, blocked on
the user), 4 (optional YouTube key rotation) and the 14-day `IntervalTrigger` timing note.

### Railway notes for the next session (the CLI is not on PATH)

Run it via `npx --yes @railway/cli@latest` with **explicit flags** — the link entries in
`~/.railway/config.json` are stale and point at a project id that 404s:
```bash
npx --yes @railway/cli@latest variable list --project 82ad930d-3ae8-404e-8e92-6e5e926741f2 --service api --environment production --json
```
⚠️ That command prints **raw secret values** — pipe it through a mask (name + length) rather than
echoing it. To set a value, prefer the `variable set "KEY=$var"` arg form: piping a secret in via
`--stdin` from PowerShell 5.1 **prepends a UTF-8 BOM (U+FEFF)** to the stored value, which happened
during this session and would have made every YouTube API call fail. Verify after setting with
`[int]$value[0]` (65279 = BOM) and an ordinal string compare — PowerShell's `-eq`/`-ceq` reported a
misleading `True` against the BOM-prefixed value.

---

## 🆕 2026-07-25 session (later) — Ruff cleanup closed + deploy-prerequisite check (v10.38.1)

Both open items from the end of the previous block. Full suite green throughout:
**563 passed / 6 skipped / 0 failed**. `ruff check .` → *All checks passed*.

**1. ✅ Ruff: repo is now lint-clean under the version CI runs.** 318 violations at `be9e30e`
(the "257" in the earlier note was an undercount), cleared in one pass — 304 safe auto-fixes,
13 unsafe auto-fixes (reviewed in the diff: `UP038` isinstance tuples, `UP031` percent-format in
the `reingest_*` logging calls), 4 by hand.
- **The version pin was never actually missing** — `ruff==0.4.9` is pinned in
  `requirements-dev.txt` and matches the local venv, so CI and local already agreed. The real
  drift was `pyproject.toml` still using the deprecated top-level `[tool.ruff]` `select`/`ignore`;
  moved to `[tool.ruff.lint]`, which also silences the warning ruff printed on every run.
- Added a `tests/**` → `E402` per-file-ignore rather than hoisting the section-banner imports in
  `tests/unit/test_rag.py` — the grouping is deliberate and reads better than one block at top.
- **3 latent bugs fell out of it**, which is the real payoff:
  - `scrapers/wikivoyage.py` and `services/comparison.py` both had their module docstring *after*
    `from __future__ import annotations`, so it was a bare string expression, not a docstring —
    `__doc__` was `None` on both. (That's what generated 20 of the 27 `E402`s.)
  - `chains/itinerary_chain.py::_parse_expense_breakdown` had an unresolvable `"ExpenseBreakdown"`
    forward-ref plus a redundant in-function re-import of a module already imported at the top.
  - `chains/feasibility_chain.py::_mock_feasibility` assigned `dest` and never used it.

**2. ✅ Deploy prerequisites for the 0005 migration + scheduler job — verified, no code change
needed.** `apps/api/railway.toml`'s `startCommand` is already
`sh -c 'alembic upgrade head && uvicorn main:app …'`, so `0005_youtube_ingestion_state` applies
itself on deploy, and the deploy restarts the process, which is what
`core/scheduler.py::start_scheduler()` needs to register `youtube_comments_refresh`. Revision chain
verified linear (`0001 → 0002 → 0003 → 0004 → 0005`). **The one genuine prod prerequisite left is
env, not code: `YOUTUBE_API_KEY` must be set on Railway** — `_refresh_youtube_comments` returns
early without it, so the job would register and then no-op silently forever. Worth confirming in
the Railway dashboard right after the next deploy.

### Found, not fixed — CI's mypy step is red for an unrelated reason

`mypy . --ignore-missing-imports` fails *before* type-checking anything:
`eval\config_loader.py: Source file found twice under different module names: "config_loader" and
"eval.config_loader"` — `apps/api/eval/` has no `__init__.py`. **Confirmed pre-existing** by
running the same command against a pristine `be9e30e` worktree, so it is not fallout from the ruff
pass. The two fixes (add `apps/api/eval/__init__.py`, or switch the CI step to
`--explicit-package-bases`) both change how the eval harness resolves its imports, and the harness
does `sys.path` manipulation in several scripts — so this needs its own change with the eval
scripts actually re-run, not a drive-by.

---

## 🆕 2026-07-25 session — 4 carried-over items closed (YouTube wiring, gems dead zone, price retrieval, food anchoring)

All four were long-standing "deferred pending data" items. Two of them (gems thresholds,
`_FOOD_MEALS_PER_DAY`) were deferred specifically because tuning a magic number without
calibration data just moves the guess — so both were fixed **structurally** instead, in ways
that don't require a new guessed constant. Full suite green: **529 passed / 6 skipped / 0 failed**
(+54 tests, from 475). Changes uncommitted pending review.

**1. ✅ YouTube ingestion wired into the cold-start gate + scheduler (was manual-only).**
The blocker was quota, not plumbing: `search.list` costs 100 of the free tier's 10,000 daily
units, and the cold-start gate allows 5/hour = up to 120/day = 12,000 units, i.e. wiring it in
naively would have blown the daily quota and starved manual/eval runs. Added a rolling-24h
search budget in `scrapers/youtube_comments.py` (`_search_budget_available()`, same shape as
`destination_ingestion.py`'s existing cold-start window, `settings.youtube_daily_search_budget=80`
≈ 8,000 units with headroom). With that guard in place:
- `services/destination_ingestion.py` now ingests YouTube comments on first request, gated on
  `youtube_ingest_on_cold_start` + a key being set. Over budget → returns 0 and leaves
  `youtube_last_ingested_at` NULL so the scheduler retries; it never records a destination as
  freshly-ingested-but-empty.
- New `core/scheduler.py::_refresh_youtube_comments` job on its own longer cadence
  (`youtube_refresh_days=14`, `youtube_refresh_batch_size=20`), **NULL-first then demand-ranked**
  (`request_count` DESC) so limited quota goes to what users actually ask for.
- New column `destination_ingestion_state.youtube_last_ingested_at` + migration
  `0005_youtube_ingestion_state` (applied and verified locally).
- **Bug found and fixed while wiring**: the cold-start `asyncio.gather` had no
  `return_exceptions`, so a raising OSM fetch discarded an already-successful Wikivoyage scrape.
  Each source is now independent.

**2. ✅ `itinerary_corpus.py` now discovers videos live instead of using the empty static list.**
`discover_youtube_itinerary_videos()` reuses `search_travel_videos()` (shared client + quota
budget) with an **itinerary-shaped** query, deliberately distinct from the hidden-gems phrasing,
over a new India-weighted `YOUTUBE_ITINERARY_SEED_DESTINATIONS` (10 India / 6 international —
correcting the pattern where every prior seed list under-served domestic destinations).
Discovered titles are filtered through the existing `_is_itinerary_shaped()` (search relevance
happily returns "10 THINGS TO KNOW" videos with no day structure). `YOUTUBE_ITINERARY_VIDEO_IDS`
is kept as a manual supplement and deduped against, so the module still works keyless.

**3. ✅ gems.py dead zone fixed — and it was a bug, not a tuning problem.**
The old fixed pair (gem ≤ 6, crowd ≥ 12) left POIs mentioned **7–11 times classified as neither**,
so they vanished from both lists — exactly what happened to Jaipur's only match (Hawa Mahal,
8 mentions), which is why the feature returned empty despite having real signal. Absolute counts
also can't be right for two corpus sizes at once (8 mentions means "obscure" in a 500-comment
corpus and "the most talked-about place here" in a 30-comment one). Replaced with a **per-destination
percentile split** (`_crowd_mention_threshold`, top ~20%), clamped into
`[_CROWD_MIN_MENTIONS=3, _CROWD_ABSOLUTE_MENTIONS=12]`, falling back to the absolute ceiling below
`_MIN_POIS_FOR_RELATIVE_SPLIT=5` mentioned POIs (a percentile over 1–2 POIs is meaningless). The
two branches now **partition** every mentioned POI — the sentiment floor is the only remaining
reason one lands in neither list, which is deliberate. This is scale-free, so it stays correct as
ingestion coverage grows rather than needing a re-tune per destination.

**4. ✅ Price-grounding retrieval fixed — the ranking gap AND two silent bugs behind it.**
Root cause was a category error: presence of a price is a **lexical** property, but selection was
being done **semantically**. A casual "Choki dani 700 per person" comment is topically about a
restaurant, not about "cost", so it carries almost no signal for a price-flavoured query to rank on
and never made the top-N cut. Fixes:
- New `core/cost_grounding.py::_scroll_price_candidates_sync` — bounded destination-filtered scroll
  (400 chunks/collection) keeping chunks that literally contain a price, via the same regex the
  extractor uses (`has_price_mention`). Merged ahead of the semantic pass in a new
  `community_price_samples()`, kept separate from `community_price_snippets()` so the prompt-hint
  callers' token budget is untouched.
- **Silent bug 1**: snippets were head-truncated at 280 chars, so any chunk whose price sat past
  char 280 was passed on with the price already cut off — it looked on-topic and contributed
  nothing, invisibly. The prompt path now uses `price_focused_excerpt()` (window centred on the
  price, keeping the trailing "per person"/"per night" qualifier in view).
- **Silent bug 2**: the extraction path shouldn't truncate *at all* — only a regex reads it, and a
  280-char excerpt discards additional prices later in the same chunk (Wikivoyage "Eat"/"Sleep"
  sections routinely list several). Now passes full chunk text.
- **Live-verified read-only against the real cluster**: price-bearing snippets found went 0→1
  (Jaipur), 0→3 (Paris), 1→3 (London) vs. the semantic-only path. Dropping the extraction-path
  truncation took Paris from 1→2 extractable amounts, which **crossed `min_samples` and produced
  the first non-None food grounding this feature has ever returned** (₹3,375/day).

**5. ✅ `_FOOD_MEALS_PER_DAY` no longer unconditionally load-bearing; the floor is now conditional.**
Rather than invent a calibration number, the multiplier was demoted to a *fallback*. New
`core/price_extraction.py::food_per_day_estimate_inr` returns `(value, directly_observed)`:
- enough amounts already expressed **per-day** ("we spent ₹900 a day on food") → used directly,
  **no multiplier involved at all**, `directly_observed=True`;
- otherwise → per-meal amounts scaled by `_FOOD_MEALS_PER_DAY` and pooled, `directly_observed=False`.

`core/budget_estimator.py::_grounded_food_per_day` then applies the safety floor **only to the
reconciled path**. The floor's entire justification was "the meals/day factor is uncalibrated, so a
low result may be an artefact" — that reasoning doesn't apply to a directly-observed daily figure,
which *is* the "anchored against real daily-spend data" condition the floor was always meant to be
temporary pending. So directly-observed figures are now trusted in both directions (same latitude
stay grounding already has), while reconciled ones stay floored. Net effect: the uncalibrated
constant becomes progressively less relevant as ingestion improves, instead of needing a one-off
calibration pass to retire.

### Still open after this session (real findings from the live run, not hand-waving)

- **Grounding still returns None for most destinations — but the reason has changed.** It is now a
  *corpus density* problem, not a retrieval one: destinations yield 0–2 extractable on-topic
  amounts and `min_samples=2` isn't met. Mumbai/Delhi/Goa/Bengaluru/London all found price-bearing
  chunks but zero *food-priced* ones. More ingestion (item 2) or Reddit (item 4) is the unblock.
- **Snippet-level context matching is coarse and produced a live false positive.** Paris's grounded
  ₹3,375/day is partly contaminated by a €5 *bus fare* from a chunk that mentions food words
  elsewhere, so it passed `FOOD_CONTEXT_KEYWORDS`. The floor correctly discarded it (3,375 < flat
  6,546 → `food_community_based=False`), which is the floor doing exactly its job — but per-amount
  proximity matching (rather than whole-snippet) is the real fix, and is now the highest-value next
  step for this feature.
- `_FOOD_MEALS_PER_DAY = 3.0` is still the fallback value; it just isn't used when real daily data
  exists. Calibrating it remains open, now lower-stakes.
- ~~Ruff: the repo is **not** ruff-clean under the currently-installed version~~ — **✅ closed
  2026-07-25 (v10.38.1).** Actual count at `be9e30e` was 318, not 257. All cleared; `ruff check .`
  now passes. The version pin turned out to already exist (`ruff==0.4.9` in `requirements-dev.txt`,
  matching the venv) — the real drift was the config using the deprecated top-level `[tool.ruff]`
  `select`/`ignore`. See the 2026-07-25 (later) block at the top.

**Last updated:** 2026-07-26 (latest) — v10.40.6: **the bare-substring keyword bug was in FIVE modules.** Beyond price grounding: `chains/safety.py`'s `"pub"` matched **"Public Garden"** (kid-safety filter silently deleting kid-friendly places), `core/budget_estimator.py`'s `"uk"` matched **"Sukhothai"** (moderate destination priced as premium), `chains/wizard_chat_chain.py`'s `"any"` matched **"Germany"** (destination chips classed as "no preference"), and `services/poi_pinning.py`'s `"art"` matched **"apartment"** (false wiki-verified pins). All on `core/keyword_match.py` now. **⚠️ `scrapers/wikivoyage.py` must stay substring-matched** — its section ids contain underscores and `_` is a word char to ``, so `go` would stop matching `go_next`. `chains/safety.py`'s `"pub"` matched **"Public Garden"**, so the kid-safety filter had been silently deleting kid-friendly places (also Public Library/Park, and "bar" → "Bara Imambara") from family itineraries; `core/budget_estimator.py`'s `"uk"` matched **"Sukhothai"**, pricing a moderate destination as premium. Both are the v10.39.0 gem-matching shape, unrecognised in these modules. Consolidated into `core/keyword_match.py`. **Deliberately not a blanket sweep** — `PREMIUM_KEYWORDS`' `"luxur"` is an intentional stem and must stay substring-matched. Previous entry: v10.40.4: **price grounding now matches the amount, not the blob** — context is scoped to each amount's own sentence, and a pre-existing bare-substring bug meant FOOD's `"eat"` matched **"great"** (the same failure shape as v10.39.0's gem matching, in a module nobody had connected to it). Stay grounding restored for Paris/Jaipur via `_STAY_MIN_SAMPLES = 1`. **Measured finding: a complete corpus is not a dense one** — only 0–3 extractable food amounts per destination even after the 170/170 backfill, so the `_FOOD_MEALS_PER_DAY` calibration stays deferred with evidence rather than assumption. Previous entry: v10.40.3: **YouTube quota discipline** — a 429/403 in the search path is now terminal instead of retried 3x against a 100/day cap (the mechanism behind 141 wasted calls), and all 12 `scripts/` entry points use a new `configure_script_logging()` carrying the app's `RedactionFilter` rather than bare `basicConfig`. That work surfaced a further leak path: the key could reach a JSONL **state file**, which no logging filter sees — hence a public `redact()` for non-log sinks. **Also corrects a v10.40.1 claim of mine**: the cold-start gate does *not* over-subscribe the quota on its own (every cold start consults the budget window first); the real gap is that the window is per-process while the quota is per-project. Previous entry: v10.40.2: **the YouTube comment corpus is complete (170/170 destinations, 25,347 points / 172 destinations verified on the cluster)**, and **`mypy .` runs for the first time** — the recorded "add an `__init__.py`" framing was wrong twice over (it was never eval-specific, and the `explicit_package_bases` option is mypy-only with no runtime effect, so no eval re-run was needed). The crawl abort was hiding **91 errors across 54 sites**, now zero; three were real bugs, including a cancelled cold-start ingestion that read as a *successful* one. Previous entry: v10.40.1: the YouTube backfill was **metering against the wrong quota** — `search.list` has its own hard cap of 100 calls/project/day (`defaultSearchListPerDayPerProject`), a separate meter from the 10,000 units/day the code models, and it resets at **midnight Pacific**, so a retry launched at 08:00 UTC is still on the *previous* quota day. All 47 destinations the retry reached failed while logging `0 comments ingested` — a clean-looking log. Underneath it, `_load_done()` was recording those failures as completed work, which would have silently abandoned all 47; fixed to the attempt-capped idiom the prominence script already used, and the bogus rows stripped (nothing had reached Qdrant). Found-and-deferred: `search_travel_videos` retries a 429 three times, and the API key reaches standalone script logs via `raise_for_status()`'s URL-bearing exception message — a different path from the httpx one previously recorded as fixed (prod unaffected, `RedactionFilter` covers it). Previous entry: v10.40.0: the POI pool is ranked by prominence, but the headline finding is that ranking was the *second* of two causes — **`scrapers/osm.py` only ever queried `node` elements**, and famous landmarks are mapped as areas (Kiyomizu-dera, Kinkaku-ji, Ginkaku-ji are `way`s; Delhi's Jama Masjid a `relation`), so they were **unreachable, not out-ranked**. Fixed with a second prominence-filtered `nwr` pass (uncapped on purpose — Overpass's `out <limit>` truncates nodes-first, so a cap silently drops every way), tiered prominence selection, and a 25% per-category cap that also settles the long-open `MAX_CATEGORY_SHARE` question. A new guard stops a *failed* prominence pass from overwriting good data with a full-looking-but-landmark-less pool — found by being bitten by it on Delhi. Tuning was measured against cached raw Overpass data across 3 cities, 8 variants; nothing beat the shipped config, and two plausible-sounding ideas were measurably worse. Live: Kyoto gems 0 → 3, Goa 0 → 1, Delhi now flags Chandni Chowk as a crowd favourite. **The 169-destination re-ingestion is the remaining work — re-run the script until `0 still pending`.** Previous entry: v10.39.0: hidden-gem name matching rebuilt on a new shared `services/name_matching.py`, but the audit that preceded it found the real cause upstream — **`scrapers/osm.py` was storing OSM's local-language `name` tag**, leaving 17 destinations (Tokyo 58/60, Seoul 56/60, Kyoto 49/60 …) with unmatchable names and showing English users Japanese/Greek/Thai place names in itineraries. Fixed to prefer `name:en`; 16 of 17 re-ingested (49% → 82% Latin-script), Tokyo still pending on Overpass failures. Gems also stopped recommending metro stops. Three latent bugs fixed along the way, two of them live in the interest-pinning path as well (NFKD folding *deleted* `ı`/`ø`/`ł`, apostrophes were split not removed). **The new ceiling is the POI pool, not the matcher** — see item 2 at the top. Previous entry: v10.38.2: the `COOKIE_SAMESITE`/`JWT_SECRET` prod guards were **inert on Railway** (they keyed off an `ENVIRONMENT` var Railway never sets) — fixed with `is_production()` + 6 regression tests; `NOMINATIM_USER_AGENT` in Railway was still the old `wanderplan/1.0` so the Wikimedia-403 fix had never reached prod; `YOUTUBE_API_KEY` set; first full YouTube backfill ran (80 destinations, 11,838 comments, 90 left for tomorrow). See the block at the top. Previous entry: v10.38.1 repo-wide Ruff cleanup: 318 pre-existing violations cleared, `ruff check .` now passes under the already-pinned `ruff==0.4.9`, config moved off the deprecated top-level `[tool.ruff]` section, and 3 latent bugs fixed (2 dead module docstrings, 1 unresolvable forward-ref + redundant import, 1 dead local). Also verified the 0005 migration + scheduler job need no deploy-side code change (`railway.toml` already runs `alembic upgrade head`); the only prod prerequisite left is setting `YOUTUBE_API_KEY` on Railway. Found-not-fixed: CI's mypy step is red pre-existing (`eval/` missing `__init__.py`). See the block at the top. Previous entry: manual frontend/stage bug-bash session found and fixed 5 Anya wizard bugs total: a dead-end fallback reply, a broken post-sign-in resume state sync, a ZWJ-emoji chip-tap detection bug, a misleading `(NO_DATA)` error masking real generation failures, and (found on stage after the first 3 were live) stale group-type chips repeating under the traveler-count follow-up. See "2026-07-24 session — Anya wizard bug bash" block immediately below. Previous entry: (1) full 168-destination live re-audit found the backlog nearly clear (only 10 failing, none wiki/osm-zero); fixed **3 silently mis-geocoded destinations the count-only gate can't detect** (Austin→was Nevada ghost town, La Paz→was Mexico, Valencia→was Venezuela) + re-ingested the 10 gate failures, landing at **7/12 fixed, 5 residual = genuine real-world category skew** (Paris metro + 4 temple/pilgrimage towns), not bugs. (2) Shipped the **food-grounding per-meal→per-day reconciliation** ("item A" proper fix) — now unit-aware, floor-kept-as-safety-net. See the two "2026-07-24 session" blocks further below. Prior top-priority (food under-estimation) is now resolved.

---

## 🆕 2026-07-24 session — Anya wizard bug bash (manual frontend testing)

User manually tested the wizard chat flow locally and reported three "Anya got stuck" symptoms; all three root-caused and fixed:

- **✅ Dead-end fallback reply (`apps/api/chains/wizard_chat_chain.py`).** When Gemini's response failed to parse as JSON, the except-branch fallback returned a hardcoded `"I'm on it! Just a moment…"` placeholder with no chips — text that falsely implies more processing is coming, but this is a synchronous request/response call, so the chat visibly stalled until the user sent another message to trigger a fresh turn. Fixed to use `_next_missing_field_prompt()` (already computed for chip backfill in that branch) as the reply text too, so every turn now ends with a real, answerable question.
- **✅ Post-sign-in generation resume left the wizard looking blank (`apps/web/components/wizard/LLMWizard.tsx`).** Repro: fill out the wizard → tap "Just generate it!" while signed out → redirected to `/signup` → sign up fails ("email already exists") → log in instead → resume effect fires. The resume effect only updated the Zustand `tripConfigStore`, never the component's own local `partialConfig`/`messages` state that the pill checklist and the chatting-phase view render from — so right after sign-in the wizard showed every pill gray and no chat history while generation ran silently, and any generation failure dropped the user into an empty-looking chat with no memory of what they'd already answered. Fixed by also syncing `partialConfig` and adding a "Welcome back…" message in the resume effect.
- **✅ Stale purpose/group chips after tapping ZWJ-sequence emoji chips (`apps/api/chains/wizard_chat_chain.py`).** Repro: tap "Family Vacation 👨‍👩‍👧" → Anya correctly moves on to the destination question, but re-shows the purpose chips instead of destination chips. Root cause: the chip-tap-detection emoji-stripping regex only removed emoji *pictograph* codepoints, not the invisible ZERO WIDTH JOINER (U+200D) that glues together multi-part emoji — "Family Vacation 👨‍👩‍👧" is actually `👨 + ZWJ + 👩 + ZWJ + 👧`, so after stripping, `"family vacation \u200d\u200d"` failed the exact-match lookup against `"family vacation"`, `purpose` never got backfilled into state, and the stale-chip safety net (which depends on `purpose` being recorded) never fired. Also found and fixed the same class of bug for "Couple ❤️" (a **group** chip) — the ❤ heart glyph lives in the Dingbats/Misc-Symbols block (U+2600–27BF), entirely outside the pictograph range, so it wasn't stripped at all. Fixed via a shared `_strip_emoji()` helper covering both ranges plus ZWJ/variation-selector codepoints; audited **every** chip across all 4 canonical fields (`purpose`, `destination`, `group`, `pace`) to confirm no other chip has this issue. Theme chips (LLM-generated, matched via substring keyword `.includes()`, not exact-match) were never exposed to this bug class.
- **Not a bug — diagnosed only:** Maldives showing a country flag instead of a beach photo in the homepage "Inspiration" gallery was reported, but turned out to already be resolved (an `imageQuery: 'Maldives tourism travel'` override from an earlier uncommitted change now resolves to the Wikipedia "Tourism in the Maldives" article's resort photo, live-verified). No code change needed; flagged that this relies on Wikipedia's live search ranking rather than a pinned landmark query, so it could regress if Wikipedia's top result for that query ever changes.
- **✅ Misleading generic `(NO_DATA)` error masking the real generation failure (`apps/web/lib/api.ts`).** Repro: build out a large trip and hit "Generate my itinerary" → red banner *"Generation failed: Itinerary generation did not complete. Please try again. (NO_DATA)"* even when the backend had already streamed a proper SSE `error` event with a real code/message (e.g. `LLM_TIMEOUT`). Root cause: `streamItinerary()`'s post-loop fallback `if (!receivedData) { onError('NO_DATA', ...) }` fired unconditionally whenever no data event arrived — including when a real `error` event *had* already arrived and called `onError` correctly, since that path never set `receivedData = true`. The generic fallback always ran last and clobbered the real error. Fixed with a `receivedError` flag (set in the `error` event branch) and the fallback condition changed to `if (!receivedData && !receivedError)`, so a real backend error now reaches the user unmodified.
- **✅ Stale group-TYPE chips repeating under the traveler-count follow-up (`apps/api/chains/wizard_chat_chain.py`).** Repro (found on stage after the above fixes were live): tap "Family 👨‍👩‍👧" in response to "who all will be joining you?" → Anya correctly asks the follow-up "how many adults, children (and their ages), and any seniors will be travelling?" → but re-shows the *same* Solo/Couple/Family/Friends chips instead of no chips (that question expects free-form numbers). Root cause: `_is_stale_chips()`'s "is this field already filled" check for `group` only looks at `config.group.adults >= 1`, which is still `False` right after a group-type tap — the type chip only signals category, not the numeric composition asked in the very next question — so the existing stale-chip safety net didn't consider `group` "filled" yet and didn't fire, and the general chip-backfill fallback (which recomputes "what's still missing") would also independently re-suggest the same group-type chips for the same reason. Fixed by adding `_is_group_type_chip_tap()` (mirroring the existing `_is_destination_mode_chip_tap()` pattern) and using it in both the JSON-success and JSON-parse-failure code paths: (1) drop echoed group chips outright when the LLM re-emits them right after a group-type tap, and (2) exclude `group` from the "backfill missing-field chips" fallback in that same situation. Verified via a standalone script confirming all 4 group chips are now correctly detected as type-taps; existing `tests/unit/test_wizard_budget_geocode.py` still passes (7 passed).

**Push note:** the 3 originally-listed fixes above were committed (`dc69748`) but not pushed for a while — the stage bug-bash that surfaced the group-chip bug was actually testing against that un-pushed old code, which is why the same bug class reappeared even though the purpose/destination cases were already fixed locally. Lesson: confirm a fix is deployed (pushed + redeployed), not just committed locally, before concluding a reported repro is a *new* bug.
- **✅ Post-sign-in resume permanently frozen at "Starting up..." in local dev (`apps/web/components/wizard/LLMWizard.tsx` + `apps/api/routers/itinerary.py`).** Repro (only in `next dev`, not production): fill out the wizard while signed out → sign in → resume effect syncs state correctly (pills all show checked, "Welcome back" message appears) but generation never progresses past "Starting up...", forever, with no error. Root cause (two compounding issues, both fixed):
  1. **Frontend race with React 18 Strict Mode.** The resume effect called `startGeneration()` synchronously, which dispatches the `/api/generate-itinerary` fetch and stores its abort handle in `cancelStreamRef`. Strict Mode's dev-only synchronous mount→cleanup→mount double-invoke runs the *separate* "cleanup on unmount" effect's cleanup (empty deps) in between, which calls `cancelStreamRef.current?.()` — aborting the fetch the same tick it was dispatched. Aborted (`AbortError`) fetches are deliberately treated as a silent, intentional cancel (no error banner), so the wizard was left frozen forever with no data, no error, nothing. Confirmed via the browser's Network tab showing the request as "cancelled". Fixed by deferring the actual `startGeneration()` call to a macrotask (`setTimeout(..., 0)`) so it runs after Strict Mode's synchronous double-invoke settles — at that point `cancelStreamRef.current` is still `null` when the phantom cleanup fires, making it a harmless no-op, while a genuine unmount shortly after still correctly aborts the (by-then-real) fetch.
  2. **Orphaned backend generation task (real resource leak, found while investigating #1).** When the client's fetch is aborted, Starlette closes `_stream_generation`'s async generator via `GeneratorExit` at whatever `yield` it's suspended on — but the actual generation work was scheduled via `asyncio.ensure_future(...)` as an independent `Task`, which is **not** automatically cancelled just because the generator that created it gets torn down. Left unguarded, the abandoned task kept running to completion in the background with nobody listening — burning a real Gemini call, Qdrant cache writes, and a full batch of Pexels image lookups for a result that's simply discarded (observed: an abandoned attempt finishing several hours later, well after the client had already given up). Fixed with a `try/finally` around the task's lifecycle that explicitly cancels it on every exit path (success, timeout, error, or client-disconnect) if it isn't already done. Verified with a standalone async-generator simulation confirming `.aclose()` now correctly cancels the underlying task; `tsc --noEmit` clean; `tests/integration/test_itinerary_gating.py` + `tests/unit/test_wizard_budget_geocode.py` still pass (8 passed).

---

## 🆕 2026-07-24 session — item 1: full re-audit + 3 wrong-city geocode fixes + final straggler re-ingestion

Ran a **fresh read-only completeness audit of all 168 `KNOWN_DESTINATIONS`** against the live cluster (not trusting old lists — the big `reingest_remaining_backlog.py` batch had clearly been run since the prior note's "~74 remaining" estimate). Result: **only 10/168 failing**, and — unlike every prior audit — **none are wiki-zero or osm-zero** anymore. The 10: category-dominated (Sri Lanka, Dharamshala, Pushkar, Alleppey, Varkala, Khajuraho, Paris) + thin-OSM (Mahabaleshwar, Lonavala, Austin).

**Geocode spot-check of the *passing* set found 3 silent wrong-city bugs** (the count-only gate passes them with 60 POIs for the WRONG same-named city — it checks POI *count*, never *correctness*, exactly the blind spot flagged last session):
- **Austin** → resolved to Austin, **Nevada** (a ~150-person former mining town, 3 OSM POIs) instead of Austin, Texas. This is *also* why it failed the gate (osm=3).
- **La Paz** → resolved to La Paz, **Mexico** (Baja California Sur) instead of the Bolivian seat of government the catalog groups it with (Santiago/Montevideo/Cusco). Passed the gate with 60 POIs for the wrong city.
- **Valencia** → resolved to Valencia, **Venezuela** instead of Valencia, Spain (catalog groups it with Seville/Granada/Nice/Lyon). Passed the gate with 60 POIs for the wrong city.

All 3 fixed via `services/geocode.py::GEOCODE_QUERY_OVERRIDES` — these are same-name collisions the generic Wikipedia country cross-check *cannot* resolve (Austin is a same-country namesake; La Paz/Valencia are real cities of comparable prominence to the intended one), i.e. exactly the escape-hatch's stated purpose. Live-verified each now resolves to the right place; 4 new unit tests (`test_geocode.py::TestGeocodeQueryOverrides`, incl. a lowercase-key guard). The 3 wrong-city datasets were **wiped first** (`delete_stale_destination_points` with an empty keep-set) before re-ingest so the OSM data-loss guard couldn't fall back to the wrong-city data on a transient thin fetch.

New script `apps/api/scripts/reingest_geocode_fixes_and_stragglers.py` re-ingested all 12 (10 failures + La Paz + Valencia). After one spaced-out retry pass for Overpass rate-limit noise (the batch hit sustained 504/429/403 across all mirrors), **7/12 now pass**: Austin (60, Texas ✓), La Paz (60 ✓), Valencia (60 ✓), Sri Lanka (62%→27%), Pushkar (63%→32%), Varkala (62%→28%), Lonavala (thin→20).

**5 residual failures are genuine real-world category skew, NOT bugs** — the same class prior sessions labelled "🟡 real-world skew": **Paris** (train-station 58% — Paris's metro density; the documented "no per-category cap" limitation / Bug 1b remnant), **Dharamshala** (place-of-worship 53%), **Alleppey** (78%), **Mahabaleshwar** (53%), **Khajuraho** (restaurant 71% — tiny temple town whose OSM is genuinely mostly eateries). Re-ingestion (geocode + adaptive radius expansion + round-robin) legitimately can't clear these without pulling in *irrelevant* POIs just to satisfy a count. **The real structural fix is the per-category hard cap in `scrapers/osm.py`** ("Still incomplete" list below), deliberately deferred there pending eval data on whether it hurts itinerary quality — this is the concrete case that would justify prototyping it. **Decision for user: accept these 5 as real-world skew, or relax `MAX_CATEGORY_SHARE` for genuinely single-category pilgrimage towns, or build the per-category cap?** *(🔒 Answered: the per-category cap was built in v10.40.0, which re-measured this list down to 3 genuine cases, and on 2026-07-28 the user accepted those 3 as real-world skew. Closed — see the open-items list near the top of this file.)*

Net across all 168: 10 gate-failures → 5 (all genuine skew), plus 2 count-invisible wrong-city bugs fixed (La Paz, Valencia). Changes uncommitted pending user review.

---

## 🆕 2026-07-23 session (generic disambiguation pipelines) — geocode + Wikivoyage rewrites, OSM data-loss guard, all 21 stragglers now pass

Triggered by the user flagging Cappadocia's failure as likely a spelling/pronunciation geocoding issue, then explicitly asking for the fix class to be made **generic** rather than another one-off override — "like if city name not found, search hub towns, check alternative spellings, check whether its a country, etc." This became the whole session's mandate: two services were rewritten around reusable disambiguation pipelines (used by every caller — ingestion, real-time chat, best_time, comparison — not just batch scripts), not just patched for the specific failing names.

- **✅ `services/geocode.py` rewritten around a generic disambiguation pipeline.** New helpers: `_is_country_like`, `_needs_second_opinion` (triggers on low importance, small-settlement types, or "no genuine `class=place` hit found" — added after Patagonia's Nominatim hits were all `class=boundary`), `_wikipedia_disambiguate` (cross-checks Nominatim's top hit's country against the same-name Wikipedia article's country — catches wrong-country collisions like Cappadocia→Italy or genuinely-unfindable names), `_hub_town_in_bbox` (Overpass-based hub-town lookup for country/region-sized hits, e.g. Ladakh/Maldives-class names, bbox-guarded at `_MAX_HUB_TOWN_BBOX_DEGREES=6.0` after Tokyo's country-sized admin bbox reliably 504'd Overpass unguarded). The old `GEOCODE_QUERY_OVERRIDES` list is kept only as a small fast-path escape hatch (ladakh/spiti/andaman/coorg/maldives/fiji/hawaii/cartagena) for genuinely irresolvable same-name-different-country ties (e.g. Cartagena, Colombia vs Spain — both real, comparably prominent, no algorithmic heuristic picks the travel-context-intended one). 14 new unit tests (`tests/unit/test_geocode.py`), all offline/mocked.
- **✅ `scrapers/wikivoyage.py` rewritten around a generic Wikivoyage disambiguation pipeline.** New: `_wikivoyage_search_title` (404 fallback via Wikivoyage's own fuzzy search API — fixed Washington DC/Rio de Janeiro, which 404'd due to Python `.title()` mis-casing "Washington_Dc"/"Rio_De_Janeiro"), `_resolve_disambiguation` (detects genuine Wikivoyage disambiguation pages via the reliable MediaWiki `pageprops.disambiguation` signal — much more robust than pattern-matching page text — then parses "Name (Qualifier)" links and cross-references the destination's geocoded country to pick the right one; a `_REGION_QUALIFIERS` set deprioritizes state/region/province-type qualifiers when two candidates share a country, e.g. "Oaxaca (state)" vs "Oaxaca (city)"). Both new checks are triggered **only when the initial scrape yields zero docs** (not on every call) — deliberate, both to avoid extra network load on the vast majority of non-ambiguous destinations and because an "always cross-check" first draft broke 3 existing tests by shifting which call `mock_client.get.await_args` captured. 4 new test classes (`tests/unit/test_wikivoyage_scraper.py`).
- **✅ Fixed a real OSM data-loss regression.** `ingest_osm_pois()`'s delete-then-upsert only guarded against a *fully empty* fetch — a non-empty-but-severely-thin result (Overpass silently returning 1 truncated POI without raising) sailed through and overwrote a previously-good 60-POI dataset for both Las Vegas and Tulum. Added `core/qdrant.py::count_destination_points()` (native Qdrant `.count()` with a destination filter) and a second guard in `ingest_osm_pois()`: after the existing radius-expansion retry, if the result is still thin/dominated, compare against the existing Qdrant point count and skip the overwrite (log a warning, return the existing count) if existing data is more substantial. 2 new dedicated tests plus updated mocks in 4 existing tests that needed `count_destination_points` stubbed.
- **Live-verified and re-ingested to production, all 21 stragglers now pass:**
  - **Cappadocia** — was geocoding to an obscure Italian village (Nominatim's top hit, importance 0.52 vs the correct Turkish region's 0.16 — importance alone would've picked the wrong one). Now 60 OSM POIs.
  - **Queenstown, Washington DC, Oaxaca, Cartagena, Rio de Janeiro** (`wiki_chunk_count=0`) — all fixed via the Wikivoyage pipeline above (wiki chunks 26/18/13/39/32 respectively).
  - **Las Vegas, Tulum** (data-loss regression, `osm_poi_count=1`) — re-ingested to 60 POIs each after the guard fix. Bonus catch: both had a **second latent geocoding bug** live-surfaced during this re-ingestion — "Las Vegas" was resolving to Colombia and "Tulum" to Turkey — corrected by the same Wikipedia cross-check.
  - **Kolkata, Cancun, São Paulo, Bora Bora** (OSM restaurant-category-share >50%) — root-caused as **stale data predating the `_prioritize_landmarks` round-robin balancing fix** from an earlier session, not a new bug: live re-fetches came back well-balanced on the first try (Kolkata 60 POIs/13% top category, Cancun 60/22%, São Paulo 60/20%, Bora Bora 53/40%). Plain re-ingestion cleared all 4. Bora Bora's Overpass fetch needed a retry after transient rate-limiting; also caught a third bonus geocoding fix — "Bora Bora" was resolving to Indonesia, corrected to French Polynesia.
- **Tests:** full suite green — 451 passed, 6 skipped (same pre-existing unrelated `test_budget_estimator.py` Python-3.9 collection error, always `--ignore`d). +20 tests this session (14 geocode + 4 wikivoyage + 2 osm data-loss guard).
- **Not yet done — natural next step:** re-audit the full remaining ~74-destination international backlog (168 `KNOWN_DESTINATIONS` total, minus India tier-2/3 + the ~95 already re-ingested across prior sessions) with `eval/run_data_completeness_check.py` to find the next batch — the generic pipelines above should silently fix a good fraction of any new spelling/disambiguation-class failures without further manual overrides. Also worth spot-checking a handful of already-"passing" destinations against the new geocode pipeline (Las Vegas/Tulum/Bora Bora each turned out to have a latent wrong-country geocode bug that the completeness gate itself can't detect — it only checks POI *count*, not *correctness* — so there may be more silently-mis-geocoded passing destinations still undiscovered).

---

## 🆕 2026-07-23 session (later still) — dev.db Alembic drift fixed + item 2: 7 more international OSM-zero holdovers re-ingested

**✅ Fixed local `dev.db` Alembic drift.** Root cause: `alembic_version` was empty (unstamped) while migrations 0001-0003's tables (`users`/`refresh_tokens`/`events`/`password_reset_tokens`/`admin_requests`) already existed from before Alembic was wired into this repo — so `alembic upgrade head` tried to re-run 0001 and hit a pre-existing-table conflict, exactly the failure mode the prior session's try/except resilience wrapper worked around. Fixed via `alembic stamp 0003_admin_requests` (matches the tables actually present) then `alembic upgrade head`, which cleanly applied only `0004_destination_ingestion_state`. `dev.db` now has all 7 expected tables and `alembic_version` correctly at head. `tests/unit/test_destination_ingestion.py` still green (10 passed). The prior session's try/except wrapper stays in place as defense-in-depth for other local devs' out-of-sync DBs.

**✅ Item 2 continued — re-ingested the 7 named still-OSM-zero holdovers** (Istanbul, Reykjavik, Warsaw, Seattle, Maldives, Fiji, Hawaii) via a new `apps/api/scripts/reingest_intl_osm_zero_holdovers.py` (same pattern as the prior two re-ingestion scripts). A live geocode pre-check found Maldives/Fiji/Hawaii resolve to a country/archipelago-sized Nominatim hit (`is_country=True`) rather than any city — same root cause as the earlier India region-name fix (Ladakh/Spiti/Coorg/Andaman). Fixed generally via three new `services/geocode.py::GEOCODE_QUERY_OVERRIDES` entries pointing to the real hub city travellers base themselves in: `maldives → "Male, Maldives"` (plain `"Male"` alone ambiguously resolved to a village in Ukraine — needed the country qualifier to disambiguate), `fiji → "Nadi"`, `hawaii → "Honolulu"`. Istanbul/Reykjavik/Warsaw/Seattle geocoded fine to real city points in the pre-check, so their prior OSM-zero result was presumed rate-limit noise, not a geocoding issue.

**Result: all 7 fully pass the completeness gate** (Istanbul 60 OSM/12 wiki, Reykjavik 60/15, Warsaw 60/25, Seattle 60/20, Maldives 60/14, Fiji 60/15, Hawaii 60/37 — live-verified via `eval/run_data_completeness_check.py::check_destination`). Fiji and Hawaii both came back `osm=0` in the batch run after exhausting 3 Overpass-504 retries each (Overpass under sustained load from the back-to-back batch); both individually re-run in isolation a few seconds later came back healthy (60 POIs each) — confirms rate-limit noise, not a real bug, same pattern as Amsterdam/Berlin in the prior session.

**Not yet done — natural next step:** continue item 2 with the next slice of the ~95-destination remaining international backlog (Paris is a good cheap next pick — only fails on OSM category-dominance already, not wiki).

---

## 🆕 2026-07-23 session (item 2 continuation) — 9 international POC-magnet cities re-ingested

Continued item 2 per the explicit next-step named in the prior session: the top POC-magnet international cities (Tokyo, Rome, Barcelona, Amsterdam, Berlin, Dubai, Singapore, Kyoto, Vienna).

**First, a live read-only audit** of all 134 non-India `KNOWN_DESTINATIONS` (reusing `eval/run_data_completeness_check.py::check_destination`) found **111 failing** the gate — almost all `wiki_chunk_count=0`, many also OSM restaurant/category-dominated, a handful (`Maldives`, `Istanbul`, `Reykjavik`, `Warsaw`, `Seattle`, `Fiji`, `Hawaii`) still fully OSM-zero from earlier sessions. Full per-destination failure reasons captured in this session's transcript — worth re-running `eval/run_data_completeness_check.py`-style scroll before picking the next batch rather than trusting this list to still be accurate after further re-ingestion.

New script: **`apps/api/scripts/reingest_international_poc.py`** (same pattern as `reingest_india_tier23.py` — `ingest_osm_pois()`/`ingest_wikivoyage()` reused as-is, delete-then-upsert, retry/backoff, JSON summary to gitignored `scripts/out/`), targeting just these 9 cities (kept intentionally small — popular metros hit Overpass rate limits harder than the India tier-2/3 towns did).

**Result: all 9 re-ingested and, after two individual retries below, all 9 fully pass the completeness gate** (60 OSM POIs + healthy wiki chunk counts each: Tokyo 48, Rome 30, Barcelona 31, Amsterdam 23, Berlin 40, Dubai 33, Singapore 34, Kyoto 16, Vienna 38).
- **Transient Overpass 504s hit Amsterdam and Berlin mid-batch** (concurrent OSM+wiki fetches for both landed on Overpass at the same time as a burst) — Amsterdam's OSM fetch partially succeeded with a stale/thin 11-POI result and Berlin's wiki fetch returned 0 chunks for one run. Both were individually re-run in isolation (no concurrent contention) and came back healthy on retry — confirms this was rate-limit noise, not a real bug (Berlin's wiki scrape alone returned 40 chunks first try when isolated).
- **Found and fixed a resilience gap in the new script while running it**: the local dev SQLite DB (`dev.db`) has out-of-sync Alembic migrations and is missing the `destination_ingestion_state` table (confirmed via `alembic upgrade head` hitting a pre-existing-table conflict, unrelated to this session's changes — a real but separate local-dev-environment issue, not touched further). This crashed the original script mid-run even though the actual Qdrant writes had already succeeded. Fixed by wrapping both `_upsert_state_row` (scheduler-freshness bookkeeping) and `_category_breakdown` (reporting-only) in try/except so a transient/local-only failure in either never discards or blocks the real ingestion writes.

**Not yet done — natural next step:** continue item 2 with the next slice of the ~102-destination remaining backlog. Good next-batch candidates from this session's audit: the still-OSM-zero holdovers (`Istanbul`, `Reykjavik`, `Warsaw`, `Seattle`, `Maldives`, `Fiji`, `Hawaii` — some of these may be region/area-name geocoding issues fixable via the same `GEOCODE_QUERY_OVERRIDES` pattern used for the India batch, worth checking before assuming they're just rate-limited) and/or the next tier of major metros (Paris only fails on OSM category-dominance already, not wiki — cheap partial fix; London/New York already pass).

**✅ Fixed this session — local `dev.db` Alembic drift.** Root cause: `alembic_version` was empty (unstamped) while `users`/`refresh_tokens`/`events`/`password_reset_tokens`/`admin_requests` (migrations 0001-0003) already existed from before Alembic was wired in — so `alembic upgrade head` tried to re-run 0001 and hit a pre-existing-table conflict, exactly as the resilience-fix try/except in the prior session worked around. Fixed by `alembic stamp 0003_admin_requests` (matches the tables actually present) then `alembic upgrade head`, which cleanly applied only `0004_destination_ingestion_state`. `dev.db` now has all 7 tables (including `destination_ingestion_state`) and `alembic_version` correctly at `0004_destination_ingestion_state`. `tests/unit/test_destination_ingestion.py` still green (10 passed) after the change. The try/except resilience wrapper added last session stays in place as defense-in-depth for other local devs' out-of-sync DBs.

---

## 🆕 2026-07-23 session (later) — items 3/4/1 + general radius-expansion fix

Closed all 4 follow-ups from the same-day India tier-2/3 session, in the user-requested order (3 → 4 → 1), then continued to a related generalization the user asked for.

- **✅ Item 3 — deleted `Skeleton Test City`.** Confirmed live (224 points in `osm_pois`, 0 in `wiki`/`reddit`/`itinerary_corpus`), deleted via a `FilterSelector` delete on the `destination` payload field, verified 0 remaining post-delete.
- **✅ Item 4 — `Medellín`/`Medellin` accent mismatch resolved.** Cluster already holds real data (60 OSM POIs, 20 wiki chunks) under unaccented `Medellin`; re-keyed all 3 `KNOWN_DESTINATIONS`-style lists (`scrapers/reddit.py`, `scripts/retry_osm_ingest.py`, `scripts/retry_osm_ingest_pass2.py`) to the unaccented form to match the existing data rather than re-ingesting under the accented spelling.
- **✅ Item 1 — all 5 India OSM-zero destinations fixed, live-verified.**
  - **Ladakh/Spiti/Andaman/Coorg** (region/area names with no city-level OSM entity — Nominatim's only hit is a district/state-sized administrative boundary whose centroid lands nowhere useful): added `services/geocode.py::GEOCODE_QUERY_OVERRIDES` (same pattern as `WIKIVOYAGE_TITLE_OVERRIDES`) substituting the real hub town for the Nominatim query only — Ladakh→Leh, Spiti→Kaza, Andaman→Port Blair, Coorg→Madikeri. The destination is still stored/displayed under its original name; only the geocoding query changes.
  - **Nainital/Jaisalmer root-caused** (not a per-destination override — a general Nominatim result-selection bug): both are real towns, but Nominatim's hit #1 for a plain city-name query is the *encompassing district/tehsil's administrative boundary* (`class=boundary, type=administrative`), not the town itself (`class=place, type=city`) — confirmed live via raw Nominatim JSON. The boundary's centroid is a district-sized average, far from the actual town's OSM density. Fixed generally in `services/geocode.py::geocode_city`: request `limit=5` (was 1) and added `_pick_best_hit()` to prefer the first `class=place`/`type in (city,town,village)` hit over an administrative-boundary hit, falling back to hit #1 only if no place-level hit exists (e.g. a genuine country/region search). This is a general fix, not specific to these two names — will silently help any other town with the same Nominatim quirk.
  - Live-verified all 6 individually re-geocode correctly (Ladakh→Leh 34.16/77.58, Spiti→Kaza 32.22/78.07, Andaman→Port Blair 11.66/92.74, Coorg→Madikeri 12.42/75.74, Nainital 29.39/79.46 (town point, not the 28.98–29.61/78.85–79.98 district bbox), Jaisalmer 26.91/70.91 (town point, not the 26.02–28.04/69.48–72.34 district bbox)) and all 6 re-ingested cleanly (Ladakh 60, Andaman 60 POIs — passed immediately at 5km; Spiti/Nainital/Coorg/Jaisalmer needed the radius-expansion fallback below).
- **✅ New: general adaptive radius-expansion fallback (`ingest_osm_pois`)**, added per explicit user request after Coorg/Jaisalmer (category-dominated, >50% restaurant) and Spiti/Nainital (thin, <20 POIs) didn't fully clear the gate from the geocoding fix alone. Small towns/hidden-gem hill-stations commonly have their few landmark/nature POIs spread wider than the default 5km radius even though restaurants cluster densely near the centre point — a wider radius rebalances the mix as well as raising the count, not just one or the other. `scrapers/osm.py::_is_thin_or_dominated()` mirrors the eval gate's `MIN_OSM_POIS=20`/`MAX_CATEGORY_SHARE=0.5` thresholds; `ingest_osm_pois` now retries once at a new `settings.osm_poi_radius_expanded_m = 15000` (3x default) when the default-radius result trips either check, keeping the wider result only if it's an actual improvement (never discards a working default-radius result for a failed expanded retry — e.g. a fresh Overpass rate-limit). Live-verified: Spiti 16→23 POIs, Nainital 15→43, Coorg 33→45, Jaisalmer 60→60 (same count, rebalanced mix) — **all 4 now pass the gate**, so **all 6 of this session's target destinations pass** (was 0/6 OSM POIs at session start). This fallback isn't India-specific — it will trigger for any future destination with the same thin/dense-core shape.
- **Tests:** 4 new tests in `tests/unit/test_osm_scraper.py::TestRadiusExpansionForThinOrDominatedResults` (expansion on thin, expansion on category-dominance, no expansion when already healthy, falls back to original when the expanded retry itself comes back empty/still-bad). Full `tests/unit/test_osm_scraper.py` + `test_wizard_budget_geocode.py` + `test_destination_ingestion.py` + `test_data_completeness_check.py` suites green (38+13 passed) after the geocode.py/osm.py changes.

---

---

## 🆕 2026-07-23 session — item 2: India tier-2/3 re-ingestion (34 towns, live cluster)

Ran a read-only audit of the live cluster first (rather than trusting old session counts): **~150 of the now-168 `KNOWN_DESTINATIONS` fail the data-completeness gate** (`MIN_OSM_POIS=20`, `MIN_WIKI_CHUNKS=1`, `MAX_CATEGORY_SHARE=0.5`) — bigger than the previously-noted "126" because the 2026-07-22 India seed-list expansion added 35 towns that were never ingested. User chose the **India tier-2/3 towns** as the first batch (highest value for the India-first cohort, lowest Overpass rate-limit risk).

New script: **`apps/api/scripts/reingest_india_tier23.py`** (parallel to `reingest_pilot_batch.py`, 12s inter-destination delay, writes a JSON summary to gitignored `scripts/out/`). Reuses the existing `ingest_osm_pois()`/`ingest_wikivoyage()` (round-robin categories + retry/backoff + delete-then-upsert cleanup all already built in). All counts below are post-write scroll reads of the real `osm_pois`/`wiki` collections (persistence confirmed). Retry/backoff visibly worked — the log shows many Overpass `429`/`504`s retried through successfully.

**Result: all 34 towns now have Wikivoyage data (was zero everywhere), 29/34 have real OSM POIs (~1,400 new OSM points + ~830 wiki chunks written).**
- **✅ 21 fully healthy** (pass the gate): Rishikesh, Manali, Shimla, Leh, Mussoorie, Srinagar, Amritsar, Udaipur, Jodhpur, Ooty, Mysuru, Hampi, Darjeeling, Gangtok, Shillong, Port Blair, Aurangabad, Haridwar, Pondicherry, Munnar, Gokarna.
- **🟡 5 OSM slightly category-dominated (top cat >0.5) but good data + wiki** — real-world skew, not a bug: Dharamshala (place-of-worship 0.53), Pushkar (restaurant 0.63), Alleppey (place-of-worship 0.78), Varkala (place-of-worship 0.62), Khajuraho (restaurant 0.77).
- **🟡 3 thin OSM (<20)**: Coorg (2), Mahabaleshwar (16), Lonavala (19).
- **🔴 5 OSM-zero (wiki still populated)**: Ladakh, Spiti, Andaman (region/area names — Nominatim returns a huge/wrong bbox → Overpass yields nothing; Coorg's near-zero is the same cause) and **Nainital, Jaisalmer** (real cities that geocoded fine and Overpass returned `200` but 0 POIs — a genuine bbox-pick anomaly, NOT rate-limiting; worth investigating).

### Follow-up TODOs from this session

1. ~~**Fix the 5 India OSM-zeros.**~~ ✅ Done 2026-07-23 (later) — see "2026-07-23 session (later)" above.
2. **Continue item 2 — next batch: top POC-magnet international cities** (Tokyo, Rome, Barcelona, Amsterdam, Berlin, Dubai, Singapore, Kyoto, Vienna, etc.) — all still `wiki=0` / food-dominated in the audit. Higher Overpass rate-limit risk; expect some to need a retry pass. ~120 destinations still remain in the overall backlog after this India batch. **Next up.**
3. ~~**Prod data-quality cleanup #1 — delete `Skeleton Test City`**~~ ✅ Done 2026-07-23 (later).
4. ~~**Prod data-quality cleanup #2 — `Medellín` vs `Medellin` accent mismatch**~~ ✅ Done 2026-07-23 (later) — re-keyed to unaccented `Medellin`.

---

## 🆕 2026-07-22 session (batch) — items 1/3/4/9/10/11 + a new regression finding

Completed six previously-open items in one pass:

- **✅ Item 1 — eval golden anchors regenerated.** Re-ran `estimate_bare_minimum_budget()` against all 5 BC cases in `eval/budget_comparison_dataset.json` (via one-off `scripts/_regen_budget_anchors.py`). Regenerating **all five** (not just the two flagged) caught that **BC-002 (Bengaluru→London) had also drifted** and wasn't on the original list. New anchor totals: BC-001 ₹68,400 (unchanged), BC-002 ₹534,100 (was ₹323,600), BC-003 ₹70,600 (unchanged), BC-004 ₹69,000 (was ₹51,100), BC-005 ₹503,800 (was ₹293,300). All five confirmed flat-`_COST_MATRIX`-based (no grounding fired → deterministic). `docs/eval-set.md` §10C-pre both caveats marked resolved.
- **✅ Item 10 — DNS-rebinding SSRF gap closed.** `chains/extract_trip_chain.py::_assert_public_host` now returns `(host, pinned_ip)` and `_fetch_url_text` connects to that pre-validated literal IP via a new `_pinned_get` (httpx `copy_with(host=ip)` + `sni_hostname` extension + `Host` header override), so httpx can't independently re-resolve to a private/metadata IP in the TOCTOU window between validation and connect. TLS cert verification still checks the real hostname (verified live against example.com). 22 new tests (`tests/unit/test_ssrf_ip_pinning.py`). This closes the residual gap flagged in the 2026-07-20 security pass.
- **✅ Item 3 — re-ingested the 23 still-zero international destinations** (live, production Qdrant writes, user-confirmed scope). 14 fully populated (60 OSM POIs + wiki); **22 of 23 now have wiki data**. Residual: 8 still OSM-zero (Maldives, Istanbul, Reykjavik, Warsaw, Seattle, Tulum[osm=1], Fiji, Hawaii — city-level ones are transient Overpass rate-limits, region/country-level ones are a geocoding-area issue), and Bangkok wiki=0 (hub-article gotcha — content is in district sub-articles; `WIKIVOYAGE_TITLE_OVERRIDES` candidate but no single canonical city sub-article). A targeted longer-backoff retry pass for the 4 rate-limited cities (Istanbul/Warsaw/Seattle/Reykjavik) is the obvious follow-up.
- **✅ Item 4 — India seed-list expansion** (pure data, no quota, no eval-data dependency). `scrapers/reddit.py::KNOWN_DESTINATIONS` +35 India tier-2/3 towns/hill-stations/heritage circuits (Rishikesh, Udaipur, Leh, Munnar, Hampi, Pondicherry, Darjeeling, Andaman, etc.) — 134→168 total, so organically-mentioned domestic destinations stop falling into `"general"`. `scrapers/itinerary_corpus.py::WIKIVOYAGE_ITINERARY_TITLES` +2 **live-verified** India itineraries ("Kerala Backwaters" 13k chars, "Rail travel in India" 57k chars), India-specific coverage 1→3. Deliberately did NOT wire YouTube ingestion into the scheduler (auto quota spend) or tune gems.py thresholds (needs eval data) — both explicitly deferred-by-design.
- **✅ Item 11 — data-completeness pre-flight check run live (first time)** against the real cluster: **5/16 golden destinations passed (31%)**. Passed: London, Delhi, Mumbai, Jaipur, Bengaluru. Failed: Edinburgh/Tokyo/Kyoto/Rome/Barcelona/Liverpool/LA/Singapore/Goa/Amritsar (wiki=0 for most — pre-Wikivoyage-fix, never re-ingested), plus category-dominance failures (Paris train-station 58%, LA place-of-worship 100%, Singapore/Barcelona restaurant ~58%), plus zero-data (Liverpool, Amritsar) and thin-OSM (Goa 15). **Concrete takeaway: the refinement-eval golden destinations are themselves largely data-incomplete** — the published fidelity numbers were measured against degraded data for many of them (already asterisked in `eval-set.md`), and this is the priority re-ingestion list before any eval rerun.
- **✅ Item 9 — grounding verified live after re-ingestion.** See item A immediately below — this verification surfaced a real regression.

### ✅ Item A (found + FIXED this session) — re-ingestion activated a latent food-grounding UNDER-ESTIMATION bug

Item 9's whole point was to verify grounding and "confirm the extracted numbers look sane." They don't. **For the first time, food grounding now fires** for some re-ingested destinations (Venice, Quito) off the fresh Wikivoyage "Eat" data — but it produces **systematically too-LOW** food estimates, because Wikivoyage "Eat" listing prices are per-dish/per-meal, not a full day's food budget (the same "nominal listing prices run much lower than real spend" gap the stay-pricing work already documented, now hitting food). Concrete, live, via `estimate_bare_minimum_budget()`:
- **Venice** (premium tier): food grounding fires → food component ₹11,900 for 2 adults/5 days = **₹1,190/day/person**, vs the flat premium fallback of ₹6,546/day/pp — a **5.5x under-estimate**, far too low for Venice dining.
- **Quito** (moderate tier): grounded ₹500/day/pp vs flat ₹2,200/day/pp.
- Stay grounding correctly stays a no-op everywhere (Wikivoyage hotel prose rarely has an extractable per-night figure).

**Why this is newly-live and harmful:** before this session's re-ingestion these destinations had no wiki data → grounding returned `None` → safe flat fallback. Now grounding fires and **under-estimates in the harmful direction** (a user under-budgets for a "bare minimum" and gets a bad surprise). This is now live in production for the re-ingested destinations that happen to have extractable Eat prices.

**Fix applied this session (user chose the food floor):** `core/budget_estimator.py::_grounded_or_flat()` gained a `floor` param; the food call site passes `floor=True`, so a grounded food figure *below* the flat `_COST_MATRIX` bare-minimum is discarded in favour of the flat value (and honestly reported as `food_community_based=False`) — grounding can still *raise* the food estimate, never undercut it. Mirrors `feasibility_chain.py`'s `max(llm_estimate, deterministic_floor)`. Stay deliberately keeps no floor (a below-flat grounded stay can legitimately reflect a genuinely cheap destination). Live-verified post-fix: Venice food back to ₹78,600 flat (was the ₹11,900 under-estimate), `food_community_based=False`. 4 new tests in `tests/unit/test_airbnb_stay_estimate.py::TestFoodGroundingFloor`.

**✅ The "proper" fix — DONE 2026-07-24 (per-meal→per-day reconciliation).** `core/price_extraction.py` now optionally reconciles per-meal/per-dish prices to a per-day figure: `extract_price_mentions_inr`/`median_price_inr` gained a `per_day_meal_multiplier` param, threaded through `core/cost_grounding.py::community_median_price_inr` and `core/budget_estimator.py::_grounded_or_flat`; the food call site passes `_FOOD_MEALS_PER_DAY = 3.0`. Crucially it's **unit-aware** — a new `_iter_raw_amounts()` tags each extracted amount as per-day (e.g. "₹1500 per day") vs per-meal/unspecified (the dominant Wikivoyage "Eat" case), and only the latter is scaled, so an already-daily mention isn't double-counted. Masking switched from single-space to equal-length spaces so the trailing-unit check reads correct offsets (existing extraction results unchanged — verified by the full pre-existing test set still green). Bounds now apply to the *reconciled* per-day value (so a ₹50 street snack ×3 = ₹150 is kept; a ₹4000 "dish" ×3 = ₹12000 is dropped). **The food floor is KEPT** as a safety net — the meals/day factor is a principled default (3 meals/day), not calibrated against real per-day spend data, so grounding can still only ever *raise* food above the flat bare-minimum, never undercut it; the win is that a genuinely food-expensive destination's real per-day figure can now clear the flat and flip `food_community_based=True` (before, a single meal's price almost never did). +12 tests (6 in `test_price_extraction.py`, 2 more in `test_airbnb_stay_estimate.py::TestFoodGroundingFloor`, plus stale-mock signature fixes in `test_budget_estimator.py`/`test_airbnb_stay_estimate.py`). **Follow-up when data allows:** calibrate `_FOOD_MEALS_PER_DAY` against real daily food-spend anchors (it's currently the standard 3, floor-protected) — and once calibrated, the floor could be relaxed to let food grounding legitimately go *below* flat for genuinely cheap destinations.

> **Note (2026-07-24): `tests/unit/test_budget_estimator.py` is NOT actually uncollectable on the current Python (3.12 venv) — it collects and runs fine (12 pass).** The long-standing "always `--ignore` it, Python-3.9 collection error" note in this doc/other test-file headers is stale for this environment; the file had gone silently stale (its `community_median_price_inr` mock was missing the `context_keywords` kwarg added 2026-07-21) because nobody was running it. Mock signature now fixed. Worth dropping the blanket `--ignore` and the "pre-existing broken" caveats elsewhere.

---

## 🆕 2026-07-22 session — decision: allow ToS-restricted sources pre-commercial; tracked for removal at launch

**Decision:** this project is pre-revenue/pre-commercial, so sources whose ToS only restrict *commercial* reuse (Numbeo, budgetyourtrip.com) are fine to use now. Reverted the 2026-07-21-later "remove Numbeo/budgetyourtrip" direction:
- `core/budget_estimator.py`'s premium-tier `food_per_day_pp` **stays Numbeo-sourced** (₹4,245/₹6,546/₹9,300, unchanged) — the planned Wikivoyage substitution was researched but not applied (see below).
- `stay_per_night_pp` (moderate/premium mid_range) **reverted to direct budgetyourtrip.com figures** (₹7,968/₹29,050, restoring the pre-2026-07-22 values) — the Wikivoyage-multiplier reconstruction from the licensing-fix session is kept in the docstring as a documented compliant fallback (numbers are within ~1 INR either way), not removed.
- Wikivoyage and Inside Airbnb stay fully wired in as-is (both are already compliant — CC BY-SA 3.0 / CC BY 4.0 — no reason to remove either regardless of commercial status).

**⚠️ Pre-commercial-only data sources — MUST remove/re-source before any commercial launch:**
1. **Numbeo** (numbeo.com) — `core/budget_estimator.py`'s premium-tier `food_per_day_pp`. ToS requires a paid commercial "Data License" beyond personal/academic use.
2. **budgetyourtrip.com** — `core/budget_estimator.py`'s moderate/premium `stay_per_night_pp`. ToS prohibits commercial use outright.

Both are now flagged directly in `core/budget_estimator.py`'s module docstring (search "PRE-COMMERCIAL-ONLY DATA SOURCES") as well as here — check both spots are updated together if either source's status changes.

**Research done this session, not applied (kept as reference for whenever Numbeo actually needs replacing):** live-compared Wikivoyage "Eat" section listings (Budget/Mid-range/Splurge categorization) against fresh Numbeo data for Paris, Bangkok, and Tokyo, and tried deriving a single Wikivoyage→Numbeo multiplier the same way the stay-pricing fix did for hotels. **Finding: it doesn't generalize.** Paris gave a consistent ~1.12x multiplier (economical 1.13x/mid_range 1.09x/premium 1.15x), but Bangkok's ratios came out 2.37x/1.53x/1.30x (Wikivoyage's Bangkok "Budget" tier is genuine street-food/night-market pricing, ~2x cheaper than Numbeo's "inexpensive restaurant" category — different real-world category despite the same label), and Tokyo/Shinjuku's Wikivoyage listings were too sparse/format-inconsistent (single-dish vs. all-you-can-eat vs. no-price-listed) to compute a ratio at all. Also found: Numbeo has **zero coverage** for smaller destinations (confirmed live: Rishikesh returns "Cannot find city id"), while Wikivoyage has at least some price data there (Chotiwala "from ₹100," Ganga View "₹10-200") — so the two sources' density/reliability trade off in opposite directions depending on destination tier. Full detail in `core/budget_estimator.py`'s premium-tier `food_per_day_pp` docstring. **If Numbeo is dropped later, don't reuse a single global multiplier — derive one per destination, same caution already applied to the stay-pricing Wikivoyage multiplier (Paris-only, "needs a second anchor" caveat).**

---

## 🆕 2026-07-21 session (latest) — ⚠️ licensing fix: budgetyourtrip.com → Wikivoyage + Inside Airbnb, plus new Airbnb-based stay estimates

**Why this session happened:** the "finally recalibrated" `stay_per_night_pp` note two sections below (budgetyourtrip.com-sourced) turned out to have a real problem — **budgetyourtrip.com's ToS prohibits commercial use**, and while auditing that, **Numbeo's ToS was also found to require a paid commercial "Data License"** for anything beyond personal/academic use. Both sources had already been merged into `_COST_MATRIX`.

**Fixed — `stay_per_night_pp` (moderate/premium mid_range) recalibrated onto compliant sources:**
- Replaced budgetyourtrip.com anchors with **Wikivoyage** (CC BY-SA 3.0, already the license basis for this app's `wiki` RAG collection) real per-listing hotel prices scraped from district "Sleep" sections via raw wikitext (`curl .../action=raw`, not the lossy rendered-page fetch tool — see `_COST_MATRIX`'s docstring for the full technique and city-specific gotchas, e.g. large "hub" articles like Bangkok/Paris/Tokyo have no inline pricing, it's in per-district sub-articles).
- Wikivoyage's own nominal listing prices are **much lower** than budgetyourtrip's self-reported "average traveller spend" figures (a real methodology gap, not just a licensing swap) — reconstructed the same dollar figures via an empirically-derived multiplier (moderate tier 3.08x, avg of Bangkok 3.10x/Athens 3.06x, independently cross-checked; premium tier 4.31x, Paris-only, flagged as needing a second anchor next time a premium-tier city is scraped).
- Net numeric change is tiny (moderate mid_range ₹7,968→₹7,916; premium mid_range ₹29,050→₹29,049) — the fix is about **provenance**, not the number itself.
- Applied via `scripts/recalibrate_pricing.py`; full sourcing math + multiplier derivation rewritten into `_COST_MATRIX`'s docstring, replacing the budgetyourtrip citation.

**New — Inside Airbnb (CC BY 4.0) wired in for two specific cases, not as the default hotel source:**
- User explicitly asks for an Airbnb/vacation-rental stay (`wants_airbnb_stay()` keyword detector: "airbnb", "air bnb", "air b&b", "vacation rental", "self-catering", "self catering") → applies `_AIRBNB_STAY_DISCOUNT_MULTIPLIER = 0.30` (derived from Bangkok 0.262x / Paris 0.339x Inside Airbnb-vs-Wikivoyage ratios) on top of the normal hotel figure.
- Wikivoyage has no usable inline hotel pricing for a destination (confirmed real case: **Istanbul**) → falls back to a new `core/airbnb_pricing.py` seeded lookup (`airbnb_hotel_equivalent_pp_inr()`, currently only `"istanbul": 10757`, computed from a live Inside Airbnb CSV + live FX rate) between the community-RAG-grounding rung and the flat `_COST_MATRIX` default. **Extend this seed dict via the new `scripts/ingest_airbnb_pricing.py`** as more Inside-Airbnb-covered cities need it (~100 cities globally, mostly Europe/Americas/some Asia-Pacific — confirmed zero India coverage).
- Both compose correctly (explicit Airbnb request on a fallback city applies the discount to the real Airbnb-derived rate, not double-discounted — verified live for Istanbul).
- `estimate_bare_minimum_budget()`'s return dict gained `stay_airbnb_based`/`stay_airbnb_fallback_used` flags; `budget_estimate_prompt_hint()` message logic updated to mention whichever applies.

**Tests:** 14 new tests in `tests/unit/test_airbnb_stay_estimate.py` (kept separate from the pre-existing broken `test_budget_estimator.py` — unrelated Python 3.9 collection error, always excluded via `--ignore`). Full suite green: 430 passed, 6 skipped. Committed as `b65e3cd`.

**⚠️ Still open, top priority for next session — Numbeo-sourced premium food figures are NOT yet fixed.** The v10.31/2026-07-21-earlier premium-tier `food_per_day_pp` recalibration (economical ₹4,245 / mid_range ₹6,546 / premium ₹9,300) used real Numbeo cost-of-living data — same commercial-license problem as budgetyourtrip, just not yet remediated. Needs the same treatment as the stay-pricing fix above: find a compliant substitute source (Wikivoyage prose sometimes mentions meal-price ranges; general web research citing primary compliant sources is another option) and either reconstruct the same figures via a multiplier or accept a fresh recalibration. **This was raised to the user mid-session and not yet resolved** — flag it explicitly before treating the premium food figures as settled/compliant in any future doc or decision.

**Also open:** `docs/eval-set.md` §10's BC-004/BC-005 stored `anchor_low_inr`/`anchor_high_inr` golden values (computed 2026-07-21, before this session's stay-pricing changes and the earlier premium-food recalibration) are now stale relative to what `estimate_bare_minimum_budget()` actually returns for those exact trip configs (spot-checked this session: BC-004 now computes ₹68,800 vs. the stored ₹51,100 anchor; BC-005 now computes ₹503,800 vs. the stored ₹293,300 anchor) — the dataset needs regenerating, but that's an eval/data decision (not a doc-only fix) left for next session.

---

## 🆕 2026-07-21 session (planned, not yet built) — domestic rail/bus/cab alternative + Kaggle-grounded flight/hotel pricing

**Status: Workstreams A and C now BUILT and shipped (v10.70, this session).** B and D remain planned only. Full plan confirmed with user via a plan-mode session; action items below are the next-session to-dos. See prior recalibration section (item 10, just below) for context on what's already been recalibrated.

**Confirmed scope:**
1. Rail/bus/cab as an intercity alternative — **only for domestic (India-internal) routes**. International routes stay flight-only. When domestic, compute both the flight estimate (existing `distance_pricing.py` bands) and a rail/bus/cab estimate, compare them, and call out the cheaper option only when it's >15% cheaper (avoid noisy "consider the bus" nudges on trivial savings).
2. Free vs. paid data sourcing — intentionally left undecided; the plan lays out trade-offs (cost/freshness/effort) for the user to decide from, not baked into a recommendation.
3. Kaggle account/API token setup is a user (human) action — the agent's deliverable is a runbook + ingestion script, not live credential setup.
4. Two independent multipliers (NOT merged with the existing general `_PEAK_SEASON_MULTIPLIER = 1.25` in `core/budget_estimator.py`):
   - **Inflation multiplier**: scales with how stale a dataset is (e.g. ~1.05–1.08x per year elapsed, compounding — exact rate to be sourced from a CPI/travel-inflation reference at implementation time).
   - **Peak-time multiplier**: dataset-specific, derived from within-dataset seasonal fare variance (e.g. the Kaggle flight data's date-of-journey column) — stacks multiplicatively on top of both the inflation multiplier and the existing general 1.25x multiplier, with an explicit precedence guard so datasets already peak-adjusted don't get double-counted.

**Workstream A — Domestic rail/bus/cab alternative:** ✅ **DONE (v10.70).** New module `core/domestic_transport_pricing.py` shipped (13 unit tests). `core/budget_estimator.py` wired: `scope="domestic"` + known coordinates → `cheaper_alternative` field, surfaced via `budget_estimate_prompt_hint()` into `chains/wizard_chat_chain.py`'s system prompt (only fires domestic + ≥15% savings; 5 unit tests). Full detail: `TECHNICAL_DOCUMENTATION.md` §14 v10.70.0, `docs/eval-set.md` §10D.

**Workstream B — Kaggle dataset integration:**
- Runbook `docs/kaggle-data-runbook.md`: account creation → API token generation → token placement → `pip install kaggle` → download commands. ⚠️ **Updated 2026-08-03 (#55):** `kaggle.json` is now the *legacy* path. Kaggle CLI 2.2.4 resolves auth in order: access token (`KAGGLE_API_TOKEN` env / `~/.kaggle/access_token`) → `kaggle.json` → OAuth (`kaggle auth login`) → anonymous. Token page moved to `https://www.kaggle.com/settings/api`. Lead the runbook with the access token. **Also document the corporate-TLS trap:** Netskope interception makes Python fail with `CERTIFICATE_VERIFY_FAILED` while `git`/`gh`/`curl` still work (they use the system keychain; Python uses bundled `certifi`) — needs a merged CA bundle via `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE`, rebuilt after every `certifi` upgrade.
- **Flights (India domestic):** `shubhambathwal/flight-price-prediction` (Kaggle, 300K rows, CC0, EaseMyTrip, 6 metros, Feb–Mar 2022) as primary; MachineHack 2019 set as secondary cross-check. No dataset found for India-origin *international* flight routes — those stay on the existing manually-anchored `DISTANCE_BANDS`.
- **Hotels (international):** **Inside Airbnb** (insideairbnb.com) — verified live this session: NOT a Kaggle dataset, a standalone free project, no account/API token needed, direct CSV download, CC BY 4.0, genuinely continuously refreshed (quarterly per-city, saw June 2026 data live) — much better freshness than any static Kaggle CSV. **Verified gap: no India coverage** (checked Mumbai and Goa directly, both 404 — Inside Airbnb only covers US/Europe/select global cities).
- **Hotels (India domestic) — the weakest link, no clean source found:**
  - Kaggle: ✅ **verified live on 2026-08-03 (#55, closed)** — this line previously said "could not verify (JS-rendered search)". That was only true of the *website*; `kaggle datasets list --search` hits the REST API and reaches the same corpus. 10 queries run, every candidate with a plausible price column **downloaded and its headers verified**. The guess above was right: all India hotel data is small single-day MakeMyTrip/Goibibo/OYO scrapes. Two structural blockers, neither fixable by finding a better dataset:
    - **No date dimension.** Every candidate but one is an undated snapshot — no check-in date, no room type, no stay length. Only `viveknakrani/goa-hotels-dataset` has a `Month` column, and it covers Feb–Jul only (misses Goa's Nov–Jan peak) with prices that aren't even rupees (median 58 — undocumented USD/EUR).
    - **Segment mix swamps inflation.** Measured: MMT 6-metro median ₹3,812 (2023-08) vs OYO median ₹1,599 (2025-02) = **2.38x**, despite OYO being 18 months *newer*. Inflation over that gap is ~1.10x and points the other way. Segment mix is a **~2.2x larger error source than staleness**, so pooling these and applying an inflation multiplier yields a confidently wrong number — worse than the manual anchors, because it looks data-backed. Third confound: OYO prices are post-discount (its `Discount` column reads 64–65%). Full table + licences in #55.
  - India OTA aggregators checked (MakeMyTrip, Goibibo, OYO, Cleartrip, Yatra): all JS-rendered SPAs, no public/free pricing API — same blocker class as Booking.com/Skyscanner, would need paid partner/affiliate API access.
  - `data.gov.in` (Ministry of Tourism): free hotel count/star-classification datasets by state — inventory/tier-availability signal only, not per-night ₹ pricing.
  - Google Places API (paid, cheap per-call): returns a `price_level` (0–4 ordinal scale) per hotel — not exact ₹ figures, but real, India-covering, always-fresh. Flagged as the most realistic paid upgrade path specifically for this gap.
  - **Recommendation:** continue the manual Numbeo/screenshot-anchor approach (as already done for the premium tier) as the near-term fix for India hotels.
- Ingestion script `scripts/ingest_kaggle_pricing.py`: loads raw CSV(s), groups by route/distance-band, computes median/percentile fares, applies the inflation multiplier by dataset age, emits a JSON "calibration proposal" diff for human review — does **not** auto-write into `_COST_MATRIX`/`DISTANCE_BANDS`, mirroring `recalibrate_pricing.py`'s existing "propose, don't auto-apply" convention.

**Workstream C — Multiplier design:** ✅ **DONE (v10.70)** — shipped as `inflation_multiplier()`, `dataset_peak_multiplier()`, `combined_multiplier()`, 11 unit tests. Note: not yet wired into a live caller (waiting on Workstream B's ingestion pipeline to actually need it) and uses a placeholder 6%/year inflation rate, not yet sourced from a real CPI reference — the segment-mix/rack-vs-discount concerns below remain open scope for Workstream B's dataset descriptor design. Original plan: new `core/pricing_multipliers.py`, shared by flight bands and the new domestic-transport bands — `inflation_multiplier(dataset_year, reference_year)` and `dataset_peak_multiplier(dataset, month)`, stacking multiplicatively with documented precedence rules. ⚠️ **Scope input from #55 (recorded on #53):** inflation alone is not sufficient. Measured segment mix (2.38x) is ~2.2x larger an error source than elapsed-time inflation (1.10x over the same span), and rack-vs-discounted rate adds a further 1.45x spread *within a single dataset* (`yashkakadiya021` Gujarat: median ₹1,733 discounted vs ₹2,519 actual). Multipliers should take a full dataset descriptor (`scrape_date`, `currency`, `segment`, `price_basis`) and **fail loudly on unknown fields** rather than silently defaulting. Note the flight dataset is now **~4.4 years stale**, putting its inflation multiplier near 1.35x at 7%/yr — large enough that the rate choice materially moves output, so source it rather than defaulting.

**Workstream D — Long-term data-freshness strategy (decision doc, not code):** new `docs/data-freshness-strategy.md` comparing manual Kaggle re-download (free, low effort, matches current philosophy), scheduled re-pull (free, unpredictable cadence risk), Inside-Airbnb-style continuously-refreshed open data (free, proves the pattern works but coverage-dependent — no India), Google Places `price_level` (low-cost paid, best fit for the India-hotel gap specifically), and a full paid live-fare API (best freshness, real cost/integration effort) — final call deliberately left to the user.

**Action items for next session:**
1. Build `core/domestic_transport_pricing.py` + rail/bus band data.
2. Wire domestic alternative comparison into `budget_estimator.py` + surface call-out copy in chat/itinerary chains.
3. Write `docs/kaggle-data-runbook.md`.
4. Build `scripts/ingest_kaggle_pricing.py` (propose-only, human-reviewed diff).
5. Build `core/pricing_multipliers.py` (inflation + dataset-peak multiplier, with precedence guard vs. existing general peak multiplier).
6. Write `docs/data-freshness-strategy.md` comparison table; get user's free-vs-paid decision recorded.
7. Add unit tests for all new modules; extend the existing budget-comparison eval with a domestic case asserting the cheaper-alternative call-out.
8. Update this doc to reflect execution progress once started.
9. ~~**User action:** once Kaggle account/token is set up, re-search Kaggle live for **both India hotel pricing and international hotel pricing** datasets~~ — ✅ **DONE 2026-08-03 (#55, closed).** Token set up; searches run from the CLI, not the JS UI. Result: **nothing usable for India**, and **nothing beats Inside Airbnb internationally**. Note `raj713335/tbo-hotels-dataset` (MIT, 1M+ hotels) advertises *"rates, reviews, amenities"* but its real 16-column schema has **no price column** — it's a hotel directory. Don't trust Kaggle descriptions for schema; assert on real headers.
10. Spot-check `data.gov.in` Ministry of Tourism hotel classification datasets as an auxiliary (non-pricing) signal for India hotel tier availability.

**Open risks:** domestic vs. international detection needs a reliable signal (check for an existing city/country lookup before building a new one); the Kaggle flight dataset is Feb–Mar 2022 only (no full-year seasonality, limits `dataset_peak_multiplier` confidence — may need a festival/holiday-calendar fallback instead) **and is now ~4.4 years stale**; India hotel pricing remains genuinely unresolved — now **confirmed against the live Kaggle corpus (#55)**, not merely assumed.

---

## 🆕 2026-07-21 session (later) — budget-estimator premium-tier recalibration + budget-comparison eval (item 5/10)

Recalibrated `core/budget_estimator.py`'s `_COST_MATRIX['premium']` food figures against real Numbeo cost-of-living data for Paris (all 3 spending styles independently sourced — economical ₹2,000→4,245, mid_range ₹3,800→6,546, premium ₹6,500→9,300 — a 1.4-2.2x undershoot, worse at lower spending styles, same shape as the 2026-07-20 Sri Lanka fix). Spot-checked the `moderate` tier against real Bangkok Numbeo data too and found it already close (~3%) — left unchanged. `stay_per_night_pp` for both tiers still needs a real anchor (Numbeo doesn't track hotels; Booking.com/Skyscanner are JS-rendered and can't be scraped by this repo's tooling). Full source figures + math in `_COST_MATRIX`'s updated docstring. See item 10 below for full detail.

Also built `eval/run_budget_comparison.py` + `eval/budget_comparison_scoring.py` + `eval/budget_comparison_dataset.json` (docs/eval-set.md §10): compares WanderPlanner's own (now-recalibrated) deterministic budget estimator against asking GPT-4o-mini/Claude-3.5-Haiku/Gemini-2.5-Flash/Kimi (Moonshot, newly added as a 4th eval-only provider) the identical budget question a real user would type directly into a chatbot — no system prompt, no RAG context, no forced JSON. Scores anchor adherence (directional only — see the dataset's own caveat), no-answer rate, whether the model asks for info it's already been given (a false-positive stall, since WanderPlanner's own estimator's discipline is refusing to quote *until* that info is missing, not after), breakdown rate, hedge-language use, and run-to-run variance (WanderPlanner's estimator is exactly 0.0 by construction; LLMs asked the same question 3x are not). Smoke-tested live end-to-end against Gemini (works correctly); not yet run against the full 4-model set — needs `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`MOONSHOT_API_KEY`. 24 new unit tests, fully offline (`tests/unit/test_budget_comparison_scoring.py`); full backend suite still green (335 passed, 6 skipped, same 1 pre-existing unrelated collection error in `test_budget_estimator.py` as prior sessions).

---

## 🆕 2026-07-21 session — item 2 pilot re-ingestion (9/136 destinations) + item 3 YouTube pipeline live-verified

**Item 2 (OSM refresh):** User chose a pilot batch over the full 136-destination backlog — the 6 India-domestic metros (Mumbai, Delhi, Bengaluru, Kochi, Varanasi, Agra) + 2 major zero-data international cities (Paris, New York), plus Jaipur (added later, to give item 3's live YouTube verification real landmark data to match against). All 9 now fully populated with balanced OSM data (60 POIs each, category-balanced per v10.27.0's round-robin fix) and real Wikivoyage chunks. **New script**: `apps/api/scripts/reingest_pilot_batch.py` — reusable for the next batch, just edit the `DESTINATIONS` list. Two real bugs found and fixed along the way (see v10.30.0 for full detail): a Wikimedia User-Agent policy 403 (our UA had no contact info — fixed to `WanderPlannerBot/1.0 (https://github.com/kunalsmathur-gif/wanderplanner)`, affects Nominatim/Overpass too), and a Wikivoyage state-vs-city article ambiguity for "New York" specifically (`scrapers/wikivoyage.py::WIKIVOYAGE_TITLE_OVERRIDES` — not exhaustive, watch for more silent-zero cases like this in the remaining 127). **Remaining 127 destinations (105 stale + 22 still zero) intentionally not touched this session** — still tracked as `osm-poi-live-reingest`, same "confirm scope with user first" caution applies.

**Item 3 (hidden gems):** Zero-cost fixes shipped (IndiaTravel subreddit added to `reddit.py::SUBREDDITS`, Hinglish sentiment lexicon added to `gems.py`). YouTube transcripts/comments engineering — `scrapers/youtube_comments.py`, new `youtube_comments` Qdrant collection, `services/gems.py` generalized to blend `reddit` + `youtube_comments` with per-source provenance — was built and unit-tested (mocked), then the user supplied a real `YOUTUBE_API_KEY` mid-session and it was **live-verified end-to-end for Jaipur**: real videos found, 29 real comments pulled (including Hinglish), 131 chunks persisted to the real Qdrant Cloud cluster. Also re-ingested Jaipur's OSM+Wikivoyage data (60 POIs, 10 wiki chunks) to give the blended scoring something fresh to match against. **Real finding**: `compute_gem_intel_sync("Jaipur")` still returns zero gems/crowd-favourites — the one name match found (Hawa Mahal, 8 mentions) falls between `_GEM_MAX_MENTIONS` (6) and `_CROWD_MIN_MENTIONS` (12) in `services/gems.py` — a genuine threshold-tuning question once more destinations have both OSM+YouTube data to test against, not touched this session without real eval data behind it. **Not yet done**: wiring `ingest_youtube_comments()` into `services/destination_ingestion.py`'s cold-start gatekeeper or `core/scheduler.py`'s refresh loop — deliberately left standalone/manually-invokable so quota isn't spent automatically on every new destination; revisit once there's a sense of real quota usage patterns. Also not yet done: extending `itinerary_corpus.py`'s YouTube transcript video-discovery (still uses the static `YOUTUBE_ITINERARY_VIDEO_IDS` list) to reuse the new `search_travel_videos()` — separate from the comments path, not touched this session.

---

## 🆕 2026-07-20 — POI-pinning ("Harry Potter test") investigation: 3 real bugs found and fixed, plus what's still incomplete

**What we were trying to verify:** the London pinned-POI end-to-end path (item 5 below) — a user says "I'm a huge Harry Potter fan" mid-chat, the app should pin real, verified places to the trip (not hallucinated ones) and show which candidate places couldn't be verified. First attempt returned **zero pinned places and zero dropped candidates** — the feature was silently doing nothing. Root-caused three separate, stacked bugs (not one):

### Bug 1 — OSM POI ingestion was 100% food/drink, 0% landmarks, for already-ingested cities
`scrapers/osm.py` unions ~14 tag categories (museums, monuments, restaurants, cafes, bars, etc.) into one Overpass query with a single flat result cap. In any dense city center, food/drink venues vastly outnumber tourist landmarks, so the flat cap filled entirely with restaurants/cafes/bars before Overpass ever returned a museum or monument. **Live-confirmed:** London's already-ingested 58 POIs were 58/58 food & drink, zero attractions.
- ✅ **Fixed:** over-fetch from Overpass (up to 400 raw results instead of 60), then select the final 60 via a **round-robin across every category present** (not just "landmarks before food/drink" — see Bug 1b) so no single tag type can crowd out the others.
- ✅ Expanded the tag list from 14 → ~28 categories (added heritage/historic sites, arts/science/entertainment venues, sports venues, parks/nature/viewpoints, transportation landmarks) so the pool itself is broader before any prioritization happens.
- **Bug 1b (found while checking if the fix generalizes to other cities):** a plain "food/drink last" sort isn't sufficient — it just relocates the same starvation bug to whichever *non-food* category happens to be locally dense. Live-verified: with only that simpler fix, central Paris returned 51/60 "train station" nodes (Paris's metro is very dense) and Tokyo returned 40/60 "place of worship" nodes (shrines/temples are everywhere), in both cases still crowding out museums/attractions/theatres almost entirely. Switched to round-robin selection across all categories, which measurably improved things (Paris train-stations 51→35, Tokyo places-of-worship 40→28, with every other category's count roughly doubling) but **did not fully equalize them** — see "Still incomplete" below.

### Bug 2 — Wikivoyage scraper was broken for every destination, not just London
The "wiki fallback" verification path (`services/poi_pinning.py`) is supposed to confirm a candidate place is real by checking if it's mentioned in that city's Wikivoyage guide text, when it's not a separately-tagged OSM node. **Live-confirmed the entire `wiki` Qdrant collection had 0 points, for every destination, across the whole app** — this exact gap had already been flagged in the 2026-07-20 budget-estimator session above ("verified live against the real Qdrant Cloud cluster that `wiki`/`reddit` collections have 0 points") but not yet root-caused.
- **Root cause:** MediaWiki's current skin wraps each section heading in `<div class="mw-heading">` instead of leaving `<h2>` as a direct sibling of the paragraph/list content that follows it. `scrapers/wikivoyage.py::scrape_wikivoyage()` walked `h2.find_next_siblings()`, which — once the wrapper div was introduced — only ever found the wrapper's own (empty) children, never the real content, silently returning 0 chunks for every page.
- ✅ **Fixed:** walk siblings of the heading's wrapper div when present, falling back to the `<h2>` itself for older/other markup, and stop at the next heading (wrapper or bare) so section content doesn't bleed across sections.
- ✅ **Verified this generalizes**, not London-specific: re-ran the scraper (read-only, no data written) against Paris (32 chunks), Tokyo (48 chunks), and New York City (20 chunks) — all previously would have silently returned 0.

### Bug 3 — combined effect: the pinning feature had never actually worked
With both the OSM and wiki data sources broken/starved, `services/poi_pinning.py`'s matching logic (which itself was already correct/previously fixed) had nothing real to verify candidates against — so it always fell through to "couldn't verify, don't invent" for every candidate, for every destination. This is why the feature looked completely inert rather than just imperfect.
- ✅ **Verified fixed, live, end-to-end:** re-ingested London's OSM POIs and Wikivoyage text with both fixes in place, then replayed the exact "I'm a huge Harry Potter fan" chat-refine call. Result: `pinned_pois` is no longer empty — **Borough Market** was correctly verified (via the wiki fallback) and pinned, while genuinely unverifiable/hallucinated-sounding candidates (Warner Bros. Studio Tour — actually ~30km outside London, outside the ingestion radius; Platform 9¾ — not a separately OSM-tagged node) were correctly listed as "couldn't verify" rather than invented.

### Still incomplete — real follow-up TODOs, not yet done

- **No per-category cap, only round-robin fairness.** Round-robin guarantees every category gets a turn, but if one category (e.g., Paris's metro stations) has far more raw nodes within the ingestion radius than every other category combined, it still fills most of the *leftover* slots after the others are exhausted. A harder rule (e.g., "no category may exceed N% of the final result") would cap this further, at the cost of sometimes returning fewer than the target total. Worth prototyping once there's real eval data on whether this actually hurts itinerary quality, rather than guessing.
- **No popularity/notability signal.** Within a category, whichever nodes Overpass happens to return first survive — there's no preference for globally-famous landmarks over minor same-tagged ones. This is why highly-recognizable places like Leadenhall Market and Millennium Bridge didn't survive London's truncation even after both fixes. A future refinement could weight by OSM `wikidata`/`wikipedia` tag presence (a reasonable proxy for "this place is notable") ahead of untagged nodes in the same category.
- **Stale point accumulation in Qdrant.** OSM ingestion upserts by hash of `(destination, name)` — safe for re-running the *same* logic, but when the category weighting/tag list changes (as it did this session), places dropped by the new logic are never deleted from Qdrant, only new ones added. Confirmed live: London's `osm_pois` count went from 58 (old, all food/drink) to 100 (60 new + ~40 orphaned old entries that share no name with the new set). Over repeated ingestion-logic changes this will quietly bloat the collection and dilute fuzzy-name matching. Needs a delete-then-upsert (or explicit orphan-cleanup) strategy per re-ingestion.
- **No retry/backoff on transient upstream failures.** Both `fetch_osm_pois` (Overpass) and `scrape_wikivoyage` (Wikivoyage) silently return an empty list on any request failure, including the public Overpass instance's frequent transient `504 Gateway Timeout` under load (hit repeatedly during this session's live testing, resolved just by retrying seconds later). In a scheduled/background ingestion job this could silently produce a city with zero data and no visible error. Should add a small retry-with-backoff and a WARNING/ERROR log when a first-time ingestion for a destination comes back with zero OSM *and* zero wiki data (currently an observability blind spot).
- **Every already-ingested destination likely has the same problem this session found for London**, and — because of Bug 1b — even destinations re-ingested with only the simpler "food/drink last" fix (if that had shipped instead of the round-robin version) would still have it in a different form. Re-ingesting existing destinations with the current fix is recommended before wider testing, budget/traffic permitting (each Overpass+Wikivoyage pair is a handful of outbound HTTP calls plus one Gemini-free embedding pass — cheap, but real production Qdrant writes, so worth confirming with the user per-destination the way London's was this session).

### In layman's terms — what this means, and why it's not "just use ChatGPT"

If you ask a general-purpose chatbot (ChatGPT, Claude, etc.) directly "plan me a Harry-Potter-themed trip to London," it will happily invent a confident-sounding list: Warner Bros Studio Tour, Diagon Alley, Platform 9¾, maybe a "wizarding pub crawl" that doesn't exist. It has no way to check any of that against reality — it's pattern-matching on what *sounds* plausible for the topic, not looking anything up. Most of the time that's fine for atmosphere, but the moment you try to actually build a walkable day around it, you find out some of it's fictional, some of it's real but an hour outside the city, and there's no way to tell which is which without doing your own research.

What we found and fixed this session is exactly the plumbing that makes WanderPlanner different from that: before the app lets the AI mention a "themed" place by name, it checks that place against two independently-verifiable real data sources — actual mapped locations (OpenStreetMap) and real destination-guide text (Wikivoyage) — and only pins it to your itinerary if it survives that check. If it doesn't survive, the app tells you honestly "couldn't verify this one" instead of inventing it anyway. That check was quietly broken (both of its data sources were empty or badly skewed) since before this session, so the feature *looked* like it was being appropriately cautious, but was actually just failing silently. It's fixed and live-verified now: ask it about Harry Potter in London today and it correctly pins something *real* (no more silent failure) — though see the new section below: "real" and "actually relevant to Harry Potter" turned out to be two different checks, and today's pin (Borough Market) is a known example of the second one still having a gap. That's still a meaningfully more honest system than a chatbot that can't distinguish real-and-relevant from real-but-irrelevant from fully invented, but it's not "solved," and the section below is about being upfront that it isn't.

### 🆕 Eval-criteria implications (2026-07-20 addendum, answering "does this change our honesty/hallucination/accuracy eval criteria?")

Short answer: **the metric definitions in `apps/api/eval/refinement_scoring.py` don't need to change**, but two things do, and both are now done:

1. **Docstring/doc clarification (done — see `eval/refinement_scoring.py` top-of-file caveats and `docs/eval-set.md` §4V's new "structural limitations" subsection):** made explicit that `honest`/`pin_precision` measure *existence*, not *thematic relevance* to the named interest, and that offline-mode scores say nothing about real production data quality (fixtures are self-contained by design). Neither of these is a new problem — they were always true — but this session is the first time both blind spots actually manifested in a way worth calling out by name: existence≠relevance via the recurring Borough Market/Harry-Potter false-positive pin, and offline-score≠data-health via the OSM/wiki bugs this session fixed (which no offline eval run would ever have flagged).
2. **New, not-yet-built recommendation — a data-completeness pre-flight check against the *real* Qdrant cluster** (non-zero wiki chunks per destination, minimum OSM POI count, no OSM category over some dominance threshold), tracked as its own gate separate from fidelity/honesty. This directly targets the class of bug found this session and the offline harness structurally cannot detect. Not yet implemented — added as TODO item below.

**Also still open, not yet fixed (code, not docs) — tracked as its own TODO item:** the Borough Market/Harry-Potter pin is a **known, previously-flagged, still-recurring** precision miss (flagged in the 2026-07-13 live run, partially addressed via a candidate-proposal-side prompt tweak in v10.23.0, reproduced again live today via the *verification*-side wiki fallback, which has no thematic-relevance check at all — see `eval/refinement_scoring.py` caveat #1 for the full mechanism). This is a real bug, not just a docs/measurement gap, and should be fixed in `services/poi_pinning.py` or `chains/interest_expansion_chain.py`, not just documented.

**Should existing published live eval numbers (0.958-0.983 recall etc.) get an asterisk?** Yes — flagged in `docs/eval-set.md`: those numbers were measured before this session's OSM/wiki fixes, i.e., against data that (for at least some destinations) was silently degraded the whole time. They're not necessarily wrong, but they should be treated as "measured against then-current production data quality, which has since improved" rather than a permanent baseline, and a live rerun is recommended once budget/traffic allows (folds into item 0 below, which was already open).
**Context:** A routine dependency-bump task (`google-genai` 1.2.0→2.10.0, dependabot PR #8) led to discovering that Qdrant Cloud has been silently rejecting every `destination`-filtered RAG query since the Cloud migration (2026-07-15) — meaning real research context has likely not been reaching the live LLM prompt at all, degrading itinerary quality invisibly (the failure was swallowed by the fallback chain, never surfaced as an error). **This is fixed in code but needs a Railway redeploy/restart to actually take effect in production** — see "Do this first" below. The user is targeting a POC round of real testers soon; items 1-3 in the "Remaining items" list below are what came out of a 2026-07-16 discussion about what's actually needed before that.

---

## 🆕 This session (2026-07-20) — Security pass before any real traffic (item 1)

Reviewed `docs/scaling-tech-challenges.md`'s "Now (any traffic)" risk bucket against current code. Most items were already solid from prior sessions; found and fixed real gaps in two of them:

- ✅ **Rate limiting gap**: `/travel-tips` calls Gemini (`_generate_gemini_tips`) but had **no rate limit at all** — added `LLM_RATE_LIMIT` (`core/rate_limit.py`). Also added `DEFAULT_RATE_LIMIT` to four previously-unprotected endpoints (`/best-time/{destination}`, `/geocode`, `/search`, `/reddit-highlights`) per the doc's own "blunt brute-force/enumeration" guidance for read-mostly endpoints.
- ✅ **Observability gap**: structured JSON logging + PII redaction (`core/logging_config.py`) already existed, but no error-tracking/APM. Added optional Sentry integration (`sentry-sdk==2.19.2`, `SENTRY_DSN`/`SENTRY_ENVIRONMENT`/`SENTRY_TRACES_SAMPLE_RATE` in `core/config.py` + `.env.example`) — a no-op unless `SENTRY_DSN` is set, so safe by default in dev/CI; just needs a DSN once a Sentry project exists.
- ✅ **Dependency hygiene**: pinned the one unpinned line in `requirements.txt` (`eval_type_backport==0.4.0`).
- ✅ **CI scanning gaps**: added `gitleaks-action` (secret scanning) as a new CI job, and `npm audit --audit-level=high` (advisory, matching the existing `pip-audit` job's non-blocking posture) to the frontend CI job.
- ✅ Already solid, verified not touched: SSRF protection on `/extract-trip`'s URL-fetch path (`chains/extract_trip_chain.py::_assert_public_host` — validates scheme, resolves DNS, rejects private/loopback/link-local/reserved/multicast IPs, manually walks redirects re-validating each hop, caps response size/content-type); `core/errors.py::sanitize_error()` — audited every router, no raw exception text (`str(e)`/`repr(e)`) reaches any client response; `dependabot.yml` already covers pip/npm/github-actions weekly.
- ⚠️ **Residual gap found, not fixed this session**: `_assert_public_host`'s DNS-rebinding window — it resolves+validates the hostname, then `httpx` re-resolves DNS independently when actually connecting. An attacker with control of a malicious domain's DNS (low TTL, swap answer between validation and connect) could theoretically bypass the private-IP check. Closing this properly needs IP-pinning at the transport layer (resolve once, connect to that literal IP, preserve TLS SNI/hostname verification) — non-trivial with `httpx`'s stable API, deliberately not risked under time pressure without dedicated tests. Worth a focused follow-up session.
- Verified: full backend suite still green after changes (284 passed, 6 skipped — the 8 failures seen locally are pre-existing/unrelated: missing optional `sentence-transformers` ML extra, and the already-documented stale `test_signup_rejects_duplicate_email` test, item 9 below). Ruff clean.

**Not done — user explicitly deferred, needs credentials**: OSM POI refresh for big cities (item 2) and the YouTube-transcripts/India-specific hidden-gems fallback (item 3) both require live external calls / a new `YOUTUBE_API_KEY` the user doesn't have on hand yet — revisit once available.

---

## 🆕 2026-07-20 — Budget estimator overhaul + production auth fix

Two live-user-reported bug investigations, both root-caused and fixed. Full detail in `TECHNICAL_DOCUMENTATION.md` §14 v10.26.0.

**Budget estimator:**
- ✅ Flight cost now requires departure city (previously never asked) and uses a real haversine-distance band (`core/distance_pricing.py`) instead of one flat number per destination tier — recalibrated against a real ₹27,000 Bengaluru→Colombo fare the user found.
- ✅ Stay/food now attempt real per-destination community-reported data via the existing free RAG collections (`core/price_extraction.py` + `core/cost_grounding.py`, deterministic regex extraction, no LLM call) before falling back to the flat table.
- ✅ Food's flat fallback recalibrated ~2-2.5x upward per real research (was undershooting real mid-range dining costs); stay's flat fallback checked against research and left unchanged (was already close).
- ✅ 27 new tests; full backend suite green (258 passed, 6 skipped).

**Production auth loop (signed-in users asked to sign in again; signup then "already have an account"; sign-in appeared to loop):**
- ✅ Root cause: `COOKIE_SAMESITE=lax` on a cross-origin (Vercel + Railway) deployment silently drops session cookies on every credentialed request. Fixed by setting `COOKIE_SAMESITE=none` in Railway's env — **confirmed working in production.**
- ✅ Added a `core/config.py` startup validator so this can't silently regress again (refuses to boot in production with the wrong value).
- ✅ Added the missing token-refresh-on-401 flow client-side (`lib/authApi.ts::refreshSession()`, wired into `authStore.hydrate()` and `api.ts::streamItinerary()`) — a second, independent bug (15-min access token, working backend `/auth/refresh` endpoint, nothing on the frontend ever called it).

**Not done yet — carry forward (see new items 9-11 below):**
- The RAG-grounding path for stay/food is real but currently a no-op everywhere — verified live against the real Qdrant Cloud cluster that `wiki`/`reddit` collections have 0 points. Re-verify it actually fires once Reddit/Wikivoyage ingestion is unblocked (item 4 below).
- Only the "budget" destination-tier / mid_range flight+food figures have a real research anchor. The other distance bands (regional/long-haul/ultra-long-haul) and destination tiers (moderate/premium) were extrapolated, not independently verified — recalibrate the same way (find a real fare/cost data point, anchor to it) as more come up.
- Found (not caused) a **pre-existing stale test**: `tests/integration/test_auth.py::test_signup_rejects_duplicate_email` expects a generic error message; the actual code intentionally returns a more specific one per an existing product-decision comment in `routers/auth.py`. Needs either the test or the comment/behavior reconciled — wasn't in scope to fix this session.

---

## 🆕 2026-07-18 — Eval infrastructure hardening

Reviewed the existing eval harnesses against the standard "Quality Flywheel" methodology (dataset → inference → grading → failure analysis → optimize) and closed all 6 gaps found:

- ✅ `eval/run_wizard_eval.py` + `wizard_dataset.json` + `wizard_checks.py` — first automated coverage of the Anya wizard multi-turn flow; live-verified 10/10 turns passing, regression-checks the exact 2026-07-18 budget/pace chip-mismatch bug (`wizard_chat_chain.py` fix).
- ✅ `eval/judge_metrics.py` — LLM-as-judge tone/personalization/coherence scoring wired into `run_model_comparison.py`, judge fixed independent of model-under-test.
- ✅ `eval/compare_results.py` + `eval/analyze_results.py` — baseline-vs-candidate diff and failure clustering, tested against real wizard output and synthetic red-team/model-comparison data. Both harness runners now write timestamped output.
- ✅ `eval/eval_config.json` + `config_loader.py` — externalizes wizard checks-to-run, judge model/toggle, default run params, and analyze thresholds.
- ✅ Docs: `docs/eval-set.md` §7 (process discipline), `docs/PRD.md` §10 (types of evals), `docs/system-design.md` §15A, `TECHNICAL_DOCUMENTATION.md` §8A, plus pointers in `docs/itinerary-generation-flow.md` and `docs/GTM_STRATEGY.md`.

**Not done yet — carry forward:**
- **Actually run `run_model_comparison.py`/`run_red_team_eval.py` live with the new judge metric enabled**, across real candidate models (still cost-gated, deliberately not run this session beyond the tooling's own synthetic/live-wizard verification — see item 0 below, now updated to reflect the judge/compare/analyze additions).
- **No unit tests yet for the new eval tooling itself** (`compare_results.py`, `analyze_results.py`, `config_loader.py`, `judge_metrics.py`) — only ad hoc manual verification (synthetic fixtures + one live wizard run) was done this session. Worth a `tests/unit/test_eval_tooling.py` pass if these become load-bearing for CI gating later.
- **`eval_config.json`'s `metrics_to_run` lists are currently descriptive, not yet enforced** — `run_rag_eval.py`/`run_red_team_eval.py`'s scoring functions don't actually branch on them yet (only `wizard.checks_to_run` is wired to gate real behavior). Low priority unless a specific metric needs to be toggled off in practice.

---

## 🔴 Do this first — verify the production fix actually landed — ✅ verified 2026-07-21

1. ✅ **Confirmed via `railway logs -s api -e production`**: a fresh container start is visible (`Starting Container` → `_ensure_collections`-driven `GET /collections/*` calls for `wiki`/`reddit`/`osm_pois`/`itinerary_corpus`/`youtube_comments`, all `200 OK`) with **zero** `destination`/`Index required` 400s anywhere in the tail. The redeploy landed and the index-creation fix is confirmed live.
2. ✅ Same log tail also reconfirms item 4 (Reddit) is still blocked in prod: `GET reddit.com/r/*/top.json` → `403 Blocked` for all 5 subreddits on this boot.

## 🔧 Hygiene follow-ups closed out 2026-07-21

- **`FieldCondition` audit (from the "consider indexing other frequently-filtered payload fields" item below) — done, no gap found.** Every `FieldCondition` usage in the codebase (`core/qdrant.py`, `services/gems.py`, `services/rag_fallback.py`, `services/search.py`, `scripts/reingest_pilot_batch.py`) filters exclusively on `destination` — the same field `_ensure_collections()`'s `_DESTINATION_INDEXED_COLLECTIONS` loop already indexes across all 5 collections. No other filtered field exists yet, so no further indexing gap to close today; re-check this if a new `FieldCondition` on a different key is ever added.
- **`tests/unit/test_prompt_guard.py` added** (28 tests, fully offline/no mocks needed) — covers `looks_like_injection()` (known injection phrasings incl. case-insensitivity, legitimate travel text incl. a "Ignore the crowds..." false-positive check, empty/`None` input), `neutralize()` (redaction, untouched clean text, WARNING log emitted only on detection, context string included in the log), and `wrap_untrusted()` (delimiter fencing, neutralization-before-fencing, label→tag slugging, default label). Full suite still green.
- **Item 11 (RAG grounding path) re-spot-checked live** against the real Qdrant Cloud cluster (`wiki`: 224 points now vs. 21 pre-re-ingestion, `reddit`: still 0). Ran `core/cost_grounding.py::community_median_price_inr()` live for London/Paris/Jaipur/Mumbai (all recently re-ingested) — **still returns `None` for both stay and food on every destination tested**, confirming the grounding path is still effectively a no-op even with real wiki content now present. Root cause is unchanged from the doc's existing note: Wikivoyage guide prose rarely contains extractable per-night/per-meal price mentions the way Reddit posts do, and Reddit remains at 0 points.

**🆕 2026-07-21 — `youtube_comments` wired into the grounding search path.** Live-checked the raw `youtube_comments` collection (131 points) and found real price mentions the default wiki+reddit-only search never saw — e.g. a Jaipur comment "Choki dani 700 per person". `services/search.py::semantic_search()` gained an optional `collections` param (defaults unchanged — wiki+reddit — for every other caller: itinerary RAG context, `/search` endpoint, `run_rag_eval.py`); `core/cost_grounding.py::community_price_snippets()` now explicitly passes `[wiki, reddit, youtube_comments]`. Full backend suite still green (397 passed, 6 skipped) after the change.

**Re-ran the live spot-check after wiring it in — still returns `None` for every destination.** Two independent gaps found, not yet fixed:
1. **Retrieval ranking**: even with the collection included and a widened query/limit, the exact "700 per person" comment doesn't surface in the top results — vector similarity doesn't rank a short, casually-phrased price mention highly against a price-flavored query.
2. **Extraction regex is too strict for the exact snippet that inspired this**: `core/price_extraction.py::_AMOUNT_RE` requires a currency symbol/code (`₹`/`$`/`Rs`/`INR`/etc.) immediately before the number — bare numbers like "700 per person" or "200" (very common in casual YouTube comments, vs. Reddit's more explicit `₹`/`$`-prefixed prose) are silently skipped.

**Conclusion: wiring is correct and live, but grounding is still a no-op pending a follow-up fix to either/both of the above** — not done this session since loosening the bare-number regex risks false positives (view counts, timestamps, phone numbers in comments) and needs care/testing rather than a quick tweak. This stays a real, scoped next-session item (separate from item 4/Reddit-approval, which was the previously-assumed sole blocker).

**🆕 2026-07-21 (later) — both follow-ups above were then built and live-verified in the same session:**
- **Bare-number extraction added** (`core/price_extraction.py`): a second, narrow pass that only fires when a symbol-less number is anchored to an explicit per-unit phrase ("per person/night/day/plate/thali", "pp") or an explicit price-reporting verb ("cost/paid/spent/charged/budget/rate") within 3 words — deliberately avoids misreading timestamps, view/subscriber counts, phone numbers, or dates as prices; also guards against misreading a foreign-currency amount ("5000 baht") as INR. 13 new unit tests.
- **Re-running the live spot-check after wiring this in surfaced a real, pre-existing false positive** (not caused by the new code): Paris "stay" grounding started returning ₹1575/night — traced to two nightclub cover-charge mentions ("Rex Club, about €15", "Pigalle, €20") in a Wikivoyage nightlife chunk. The *original* currency-symbol regex had no topic anchor at all — any ₹/$/€ amount within bounds counted regardless of whether the snippet was actually about a hotel rate.
- **Fixed same session**: added `STAY_CONTEXT_KEYWORDS`/`FOOD_CONTEXT_KEYWORDS` + an optional `context_keywords` param on `extract_price_mentions_inr()`/`median_price_inr()`, threaded through `community_median_price_inr()` and `budget_estimator.py`'s two `_grounded_or_flat()` call sites — a snippet must now contain at least one on-topic word before any amount in it counts. Omitted by default so no other caller's behavior changed. 6 more unit tests (27 total in `test_price_extraction.py`).
- **Re-verified live post-fix, both via the raw grounding function and the actual `estimate_bare_minimum_budget()` production entrypoint**: Paris (and London/Jaipur/Mumbai) now correctly return `None`/`stay_community_based=False` again — the false positive is gone. Grounding is still a no-op in prod today (real on-topic signal genuinely isn't there yet for these destinations), which is now the *correct*, honest behavior instead of confidently reporting a wrong number. Full backend suite green (416 passed, 6 skipped).
- **Still open**: the underlying "not enough real signal" gap remains — needs either more re-ingestion (item 2, more destinations/deeper wiki content), Reddit unblocking (item 4), or a wider YouTube-comments net (item 3's not-yet-built video-discovery extension) before grounding can flip `true` for real destinations. Retrieval ranking (bare-number pass finding the right snippet in the first place) also still isn't perfect — worth a follow-up look once there's more ingested content to test against.

## ⏭️ Remaining items (in suggested order — items 1-3 are POC-readiness priorities per 2026-07-16 discussion)

### 0. Run the new LLM model-selection + red-team evals live (harnesses now include a judge metric + compare/analyze tooling, built 2026-07-16 → hardened 2026-07-18, still not run live end-to-end)

In response to a "should we use MMLU/GPQA to pick the LLM?" discussion, two eval harnesses were built 2026-07-16 but **deliberately not run** (live API calls cost real money): `apps/api/eval/run_model_comparison.py` (accuracy/hallucination/latency/cost — and, as of 2026-07-18, LLM-as-judge tone/personalization/coherence — across candidate models on the real production itinerary prompt, see `docs/eval-set.md` §8) and `apps/api/eval/run_red_team_eval.py` (injection/exfiltration/kids-safety-bypass/cost-abuse robustness per model — §9). Both were import/smoke-tested against synthetic data only; the 2026-07-18 session additionally live-verified the new wizard harness and the judge metric individually, but did **not** run a full multi-model sweep with either harness.

To actually run them next session:
- Add `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` to `.env` for whichever of OpenAI/Anthropic should be in the comparison (Gemini + Groq already have keys configured).
- `pip install -r requirements-ml.txt` (adds the new optional `groq`/`openai`/`anthropic` SDKs).
- Run both: `python -m eval.run_model_comparison --models <ids>` and `python -m eval.run_red_team_eval --models <ids>` from `apps/api` (each prints a cost estimate and asks to confirm — pass `--yes` to skip).
- Review the timestamped `eval/out/model_comparison_report_<ts>.md` and `eval/out/red_team_report_<ts>.md` (or the `_latest`-aliased fixed filenames), decide whether to switch `gemini_model`/`llm_provider` based on the results — the judge's tone/personalization/coherence sub-scores now sit alongside the deterministic accuracy/hallucination numbers, so a cheaper model that's structurally "accurate" but reads generically won't look artificially good.
- Once a second run exists, try `python eval/compare_results.py <first-run>.json <second-run>.json` and `python eval/analyze_results.py <run>.json` — this session verified both tools against real wizard-eval output and synthetic red-team/model-comparison fixtures, but neither has been exercised against a real multi-model run yet.
- Related gap surfaced while building this: ~~**no unit test exists for `core/prompt_guard.py`**~~ **✅ done 2026-07-21** — `tests/unit/test_prompt_guard.py` added (28 tests covering `looks_like_injection`/`neutralize`/`wrap_untrusted`).

### 1. Security checks before any real (even POC) traffic — ✅ done 2026-07-20

Done this session — see "🆕 This session (2026-07-20) — Security pass before any real traffic" above for the full list of what was fixed (rate-limiting gap on `/travel-tips` + 4 other endpoints, optional Sentry wiring, pinned `eval_type_backport`, gitleaks + `npm audit` added to CI) vs. what was already solid (SSRF, `sanitize_error` coverage, dependabot). One residual gap flagged, not fixed: DNS-rebinding window in `_assert_public_host` (`chains/extract_trip_chain.py`) — needs transport-level IP pinning, a focused follow-up.

### 2. Refresh OSM POI data for big cities before POC (elevated priority — was "low priority," now tied to POC quality)

Paris, Mumbai, Delhi, Bangkok, New York, and ~28 others are still missing real OSM data (persistently Overpass-rate-limited even at 12s delay across two retry passes — see `apps/api/scripts/retry_osm_ingest_pass2.py`'s `STILL_ZERO` list in git history for the exact set). These are exactly the destinations POC testers are statistically most likely to try, and without real POI grounding those itineraries lean more on the LLM's own knowledge (still generates fine, just a weaker showcase of the "verified real places" value prop). Needs actual exponential backoff / longer delays (30s+, possibly a dedicated slower job run over a longer window) rather than more retries at the same 12s cadence, which already hit diminishing returns.

**⚠️ Updated 2026-07-20:** even destinations that *do* have OSM data (like London, which had "58 real POIs" per the note above) turned out to be near-useless — see the new "POI-pinning investigation" section at the top of this doc. The category-starvation bug found and fixed there (`scrapers/osm.py`) means **every already-ingested destination should be treated as suspect and likely worth re-ingesting** with the current fix, not just the ~28 still at zero. Re-ingesting is cheap (a handful of HTTP calls + one embedding pass) but is a real production Qdrant write — confirm per-destination with the user the way London's was this session, don't batch-run silently.

**✅ Prerequisite hygiene fixes done 2026-07-20 (code, not the actual re-ingestion run):**
- **Retry/backoff added** to `fetch_osm_pois` (Overpass) and `scrape_wikivoyage` — both now retry transient failures (429/504/timeouts) up to 3 attempts with linear backoff (5s/10s) before giving up, logging a warning on final exhaustion instead of silently returning `[]`.
- **Orphan cleanup added**: new `core/qdrant.py::delete_stale_destination_points()` scrolls a collection filtered by `destination`, deletes any point not in the freshly-ingested ID set, and is wired into both `ingest_osm_pois()` and `ingest_wikivoyage()` as a delete-then-upsert per destination. Fixes the bug where London's `osm_pois` count went 58→112 (not 58→60) after re-ingestion.
- **Observability blind spot closed**: `ensure_destination_ingested()` now logs a WARNING when a first-time ingestion returns zero OSM POIs *and* zero wiki chunks, instead of silently recording an empty destination.
- 15 new/updated unit tests across `test_osm_scraper.py`, `test_wikivoyage_scraper.py`, `test_destination_ingestion.py`, and new `test_qdrant_orphan_cleanup.py`. Full suite green (328 passed, 6 skipped — the `test_budget_estimator.py` collection error is the same pre-existing/unrelated Python 3.9 union-type issue noted elsewhere in this doc).

**🆕 Live prod Qdrant audit done 2026-07-20 (read-only, no writes)** — scrolled the real `osm_pois` collection (5,489 points across 105 destinations) to get the actual current state rather than guessing from old session notes:
- **105 destinations already ingested** (104 remaining as of 2026-07-21 — Jaipur done, see session note above), almost all still capped at ~50-60 points from the pre-fix logic and heavily food/drink-dominated (e.g. Copenhagen 100%, Dubai 100%, Bruges 93%, Budapest 95%, Zurich 90%) — every one of these needs re-ingestion with the round-robin fix to actually benefit from it.
- ~~**31 destinations never ingested at all**~~ **23 remaining** (0 points; 8 of the original 31 were done in the 2026-07-21 pilot batch — see session note above): Bangkok, Ho Chi Minh City, Phuket, Maldives, Abu Dhabi, Istanbul, Prague, Santorini, Oslo, Venice, Reykjavik, Warsaw, Granada, Amalfi, Seattle, Mexico City, Tulum, Medellín, Quito, Vancouver, Casablanca, Fiji, Hawaii. ✅ Done 2026-07-21: Mumbai, Delhi, Bengaluru, Kochi, Varanasi, Agra, Paris, New York.
- **Still not done — the remaining 127-destination re-ingestion run** (104 stale + 23 still-zero). `apps/api/scripts/reingest_pilot_batch.py` is ready to reuse for the next batch. Tracked as its own SQL todo (`osm-poi-live-reingest`).


### 3. Hidden gems — alternative data source if Reddit approval doesn't come through in time

Reddit's approval has no ETA (see item 4 below), so the "hidden gems" feature (`services/gems.py`) currently has zero real sentiment data to work with — it degrades gracefully (empty result) but isn't demo-able for a POC. **2026-07-16 follow-up session did the full research pass** (below) — this is no longer "candidate directions to evaluate," it's a scoped plan ready to build, gated only on the doc-commit step described at the end of this item.

**✅ Build now (free, reuses existing infra):**
- **YouTube transcripts** — extend the already-wired but empty `YOUTUBE_ITINERARY_VIDEO_IDS` list in `scrapers/itinerary_corpus.py` via live YouTube Data API v3 `search.list` calls per destination (100 units/query, free 10k-units/day quota) instead of manual curation. **Not yet built** (2026-07-21: `search_travel_videos()` below was built for the comments path; itinerary_corpus.py's transcript-discovery still uses the static list).
- ✅ **Built 2026-07-21, gated on `YOUTUBE_API_KEY` (user doesn't have one yet)** — **YouTube comments** — `scrapers/youtube_comments.py`: `search_travel_videos()` (`search.list`) discovers videos per destination, `fetch_video_comments()` (`commentThreads.list`, 1 unit/call, free) pulls comments, `ingest_youtube_comments()` embeds + upserts into the new `youtube_comments` Qdrant collection with delete-then-upsert orphan cleanup (same pattern as OSM/wiki). 11 unit tests (mocked HTTP), never run against the real API. Every function is a documented no-op when the key is unset.
- ✅ **Done 2026-07-21** — **Generalized `services/gems.py`** to blend `reddit` + `youtube_comments` mentions with per-source provenance (`sources` field, e.g. `"r/travel"` / `"YouTube"` — renamed from `subreddits`, confirmed safe since this dict is never exposed to the frontend). Ships working today off YouTube alone since Reddit is down in prod; Reddit signal layers back in for free whenever/if approval lands. **Not yet wired into `ensure_destination_ingested()`/the scheduler** — deliberate, to avoid auto-spending quota before the user's tested it once with a real key.
- ~~**Expand `scrape_all_travel_blogs()`'s RSS feed list** with 2-3 more blogs, ideally "hidden gems"-angled~~ **✅ done 2026-07-22** — added Two Wandering Soles and Y Travel Blog to `TRAVEL_BLOG_FEEDS` in `scrapers/itinerary_corpus.py`. Both feeds live-verified (real, full-body-fetchable posts). Two Wandering Soles had the best itinerary/gem-title hit rate of everything spot-checked (e.g. "Portugal's Best Hidden Gem", "The 2-day Kyoto Itinerary I'd Recommend" — 3/12 recent items); Y Travel Blog next-best ("Queensland's Best Kept Secret"). Not yet ingested against the real cluster.

**🕒 Roadmap — paid or needs a quick pricing/legal pass, not free/immediate:**
- **Google Places API** (`rating` + `userRatingCount` as a structured gem signal — low count + high rating = gem, no lexicon guesswork). Estimated one-time cost for a full destination-set refresh (~50 destinations × 300 POIs = 15,000 lookups): first 5,000/month free, then $17-32/1,000 depending on endpoint → **~$170-320 one-time**, near-zero after (ratings don't change fast). Deferred by cost decision, same bucket as BestTime.app/Booking.com. **Important limitation found**: the official API does **not** expose reviewer account age/review-count/Local-Guide level (that's Google Maps UI-only) — so "check how long this reviewer has been active" has no API equivalent; the feasible substitute when this gets built is rating-velocity/distribution-shape anomaly detection (sudden 5-star bursts, all-5-star or bimodal distributions) using data Place Details already returns.
- **TripAdvisor Content API** — correcting an earlier assumption: this is actually **self-serve** (sign up at tripadvisor.com/developers, generate a key immediately, no partner-approval gate found in current docs), pay-as-you-go, and includes real review *text* (Google's cheaper tiers don't). Exact per-call rate isn't published without signing up — 15-minute task next session to pull the real rate card before sizing. Treat as similar cost tier to Google Places until priced.
- **X/Twitter API v2** — priced (Basic ≈ $200/mo for ~10-15k reads, Pro ≈ $5,000/mo — last-published figures, re-verify at developer.x.com) but a flat subscription regardless of usage plus a noisy firehose needing heavy filtering. Documented as evaluated, but Google Places/TripAdvisor look like better spend for the same budget.
- **Foursquare** — public docs have pivoted almost entirely to enterprise geospatial products; the old consumer tips/ratings "Personalization API" is marked Deprecated with no public price found. Needs a founder-level sales inquiry, not an engineering spike.
- **Yelp Fusion** (free, but weak non-US/India coverage — parked until US traffic matters), **Pinterest API** (free, but images/boards not ratings/review text — weak signal fit), **Atlas Obscura** (best "hidden gems" editorial fit of anything evaluated, but no public API — needs a 15-min ToS/robots.txt check before a cautious RSS-only add).

**❌ Rejected — no viable access path, won't revisit:**
- **Instagram** — Graph API only covers content you own; scraping public posts/hashtags/locations violates ToS and Meta actively pursues scrapers legally.
- **TikTok** — "Research API" is restricted to approved academic researchers only, not commercial products; scraping is blocked by heavy obfuscation and prohibited by ToS.
- **Zomato** — API closed to new developers since ~2019.
- **Swiggy** — no public API, no developer program.
- **MakeMyTrip / Yatra / Goibibo / Cleartrip** (India OTAs) — no self-serve developer APIs, consumer apps only.
- **Quora** (India travel Q&A volume is huge) — no content API, ToS prohibits scraping.

**Authenticity-scoring design** (applies to Reddit/YouTube now, Google Places later — the underlying concern: low review-count + high rating is equally the signature of a paid-review farm, not just a hidden gem): build a composite 0-1 weight per mention (not a binary include/exclude) from whatever each source's *official API* genuinely exposes — Reddit account age/karma via `/user/{username}/about.json` (free, one extra call per unique author, long-TTL cached), YouTube commenter channel age/subscriber count via batched `channels.list` (free, in-quota), plus temporal-clustering and duplicate-text penalties computed from data already retrieved (bounded CPU, same pattern as today's lexicon scan). No source — not even Google's official Places API — exposes reviewer tenure/review-history as a clean field; that's a Maps-UI-only feature, not worth scraping to replicate.

**India domestic-travel coverage findings** (main user cohort is Indian — checked the actual scraper code for gaps, not just the abstract source list above):
- ✅ **Fixed 2026-07-21**: `gems.py`'s sentiment source (`reddit.py`'s `SUBREDDITS` list) had **no India subreddit at all** — added `"IndiaTravel"`. (Consider city-specific subs as a future follow-up.)
- ✅ **Fixed 2026-07-21**: `gems.py`'s `_POSITIVE_WORDS`/`_NEGATIVE_WORDS` lexicon was English-only — added a small romanized Hindi/Hinglish supplement (`badhiya`, `zabardast`, `mast`, `bekar`, `ganda`, `bakwas`, etc., deliberately small/low-ambiguity, not exhaustive).
- YouTube video discovery (above) needs India-specific query phrasing (e.g. "hidden places to visit in Jaipur") to actually surface India's large domestic vlog ecosystem, not just generic English queries.
- **Popularity-capped seed lists that should carry a deliberately larger India-specific subset** (OSM/Wikivoyage per-destination ingestion is already fully demand-driven/uncapped regardless of country — no change needed there): `KNOWN_DESTINATIONS` in `reddit.py` has only **11 India entries out of ~134 total** (missing Rishikesh, Udaipur, Jodhpur, Hampi, Leh, Manali, Pondicherry, and other tier-2/3 domestic-tourist towns that fall into `"general"` today and lose their signal); `WIKIVOYAGE_ITINERARY_TITLES` in `itinerary_corpus.py` has only 1 of 5 India-specific; any future YouTube discovery seed list should start with a larger India set from day one. Sequence this *after/alongside* the already-tracked `osm-poi-refresh-big-cities` fix (Mumbai/Delhi already hit the Overpass rate-limit wall) so newly-added domestic destinations don't hit it too.
- **LBB (Little Black Book)** — India-specific urban "hidden gems" discovery publication, closer editorial fit than Atlas Obscura for domestic trips, no public API — same ToS-check treatment as Atlas Obscura. **Thrillophilia** (India experiences/activities, review-driven) looks partner-gated like Viator/GetYourGuide — fold into the existing founder-blocked affiliate outreach rather than a new thread.

**Sequencing — hard gate, per explicit direction**: none of the above gets built yet. First step is folding this into the docs (this entry, plus targeted pointers added to PRD/system-design/rag-strategy/GTM/eval-set/STARTUP_EVALUATION — 2026-07-16), committing to `main`, then applying the same doc commit to `feat/frontend-scaffold`. Only after both are pushed does any engineering work start.

### 4. Reddit ingestion — blocked on Reddit's approval, no ETA

Confirmed broken in production too (403 on every scheduled run since the Cloud migration), not just a sandbox-network quirk. Reddit's API access process has tightened — no more instant self-serve script key. A dedicated bot account was registered and a written app-review request submitted 2026-07-16 covering both ingestion flows (6-hourly sentiment mining across r/travel, r/solotravel, r/digitalnomad, r/backpacking; monthly itinerary-example search additionally across r/IndiaTravel, r/JapanTravel). **Check if approval came through.** If yes: get the `client_id`/`client_secret` from the app's Developers-portal page, rewire `scrapers/reddit.py::ingest_reddit()` to OAuth2 (check what Reddit's approval response specifies — password-grant with the dedicated bot account vs. client-credentials).

### 5. E2E pinned-POI positive path — ✅ verified working 2026-07-20 (after fixing 2 real bugs first)

This was blocked on bad data, not just "not yet run" — see the "POI-pinning investigation" section at the top of this doc for the full story. Short version: London's OSM data was 100% food/drink (a landmark-starvation bug in `scrapers/osm.py`) and the Wikivoyage scraper was silently broken for every destination (a MediaWiki markup change broke `scrapers/wikivoyage.py`). Both fixed and live-verified; re-ran London trip → "I'm a huge Harry Potter fan" → `pinned_pois` correctly non-empty (Borough Market, verified via wiki), unverifiable candidates correctly listed as dropped rather than invented. **Not yet done:** the visual part (📌 pins render on screen, in-place regen, diff chips) — Chrome DevTools MCP isn't configured in this environment, so only the backend API contract was verified, not the actual browser rendering. Needs either a manual check or a Playwright test addition as a follow-up. Also still not run: the themes-backstop path ("add some zen gardens to my trip").

### 6. E2E gems check — still blocked on Reddit (or unblocked by item 3's alternative source)

Crowd dial = Hidden Gems → 💎 with provenance requires real sentiment data, currently only from Reddit (item 4). If item 3's alternative source ships first, re-scope this check to that source instead.

### 7. Itinerary corpus — ✅ source pool expanded 2026-07-20

Was thin (1 doc after the previous rerun; Planet D RSS had started failing with a connection-reset error). **This session:** dropped the broken Planet D feed, added `Uncornered Market` (general adventure/hiking, good itinerary-title hit rate) and `Bruised Passports` (India-focused — Indian bloggers, day-count itinerary titles like "10 day trip to Australia", "4-Day Guide to Doha" — closes the gap noted elsewhere in this doc that the blog-feed pool had zero India-specific coverage even though `ITINERARY_SUBREDDITS` already lists `r/IndiaTravel`). Live-verified against the real feeds before wiring in (all three return real, itinerary-shaped, full-body-fetchable posts — Planet D still fails, confirmed dead). Ran `ingest_itinerary_corpus()` live against the real Cloud cluster (user confirmed): itinerary_corpus collection went from 1 → 4 real docs (Nomadic Matt/Madrid, Bruised Passports/Australia, /Doha, /Kyrgyzstan). One Uncornered Market/Cyprus doc failed LLM extraction (`json.JSONDecodeError`, unterminated string) after 2 retries — a separate LLM-extraction robustness issue, not a source-pool problem; worth a follow-up if it recurs. Reddit trip-report search is still fully blocked (403 across all 6 subreddits, tracked as item 4). 46 corpus-related unit tests still green; full backend suite green (304 passed, 6 skipped).

### 8. Affiliate tracking — blocked on founder

Register Viator / GetYourGuide / Skyscanner affiliate programs and supply IDs. Link formats fixed since v10.20.0, so the code side is a small param-append in `BookingLinksSection.tsx` + `cityCodes.ts` coverage check.

### 9. Fix stale duplicate-signup test — ✅ done 2026-07-20

Confirmed: the test predated the product decision. `routers/auth.py::signup()` intentionally returns `"An account with this email already exists. Try logging in instead."` (per an explicit product-decision comment). Fixed `tests/integration/test_auth.py::test_signup_rejects_duplicate_email` to assert the correct message. 8 tests passing.

### 10. Recalibrate the rest of the budget-estimator's hand-authored figures as real data points turn up — ⚠️ further progress 2026-07-21 (`_COST_MATRIX` premium tier now recalibrated; `DISTANCE_BANDS` unchanged this session)

**🆕 2026-07-21 session:** `core/budget_estimator.py`'s `_COST_MATRIX['premium']['food_per_day_pp']` row recalibrated against real Numbeo cost-of-living data for Paris (all three spending styles — economical/mid_range/premium — each independently sourced, not one anchor + proportional scaling like prior fixes): ₹2,000→4,245 / ₹3,800→6,546 / ₹6,500→9,300, an undershoot of 1.4-2.2x, worse at the lower spending styles (same shape as the 2026-07-20 Sri Lanka food fix). The `moderate` tier's food figures were spot-checked against real Numbeo Bangkok data too and found already close (within ~3%) — left unchanged, verified-not-broken. `stay_per_night_pp` for both tiers is still NOT recalibrated — Numbeo doesn't track hotel rates and no free, non-JS-rendered hotel-pricing source was found this session either; still needs a real anchor (see `scripts/recalibrate_pricing.py`'s docstring for candidate sources — Booking.com/Skyscanner are both JS-rendered and can't be scraped by this repo's fetch tooling, same blocker as before). Full reasoning + exact per-meal source figures documented in `core/budget_estimator.py`'s `_COST_MATRIX` docstring.

**🆕 2026-07-21 — also built: `eval/run_budget_comparison.py`** (docs/eval-set.md §10) — compares WanderPlanner's own recalibrated estimator against asking GPT-4o-mini/Claude/Gemini/Kimi the same budget question directly, as an ordinary chatbot user would. Smoke-tested live against Gemini (works end-to-end); not yet run against the full model set (needs `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`MOONSHOT_API_KEY`). Added Moonshot/Kimi as a fourth eval-only provider (`eval/llm_providers.py`, `core/config.py`'s new `moonshot_api_key`, `core/llm_client.py` pricing table) — same "eval-only, not wired into production" scope as the OpenAI/Anthropic keys already there. See docs/eval-set.md §10 for the full metric list and the important caveat about what its anchor bounds do/don't prove (they're our own estimator's output, not independent ground truth — the real citations are what should be trusted).

Two more real anchors landed this session on top of the Bengaluru→Colombo one from v10.26.0: a Bengaluru→London long-haul round-trip fare (₹67,327, screenshot-sourced) recalibrated the long-haul band via the full anchor+nudge algorithm, and a Delhi↔Goa peak-season (Dec 25–31) round-trip fare (~₹18,157–20,389) manually lowered the regional band's low end only (the high end still covers pricier international-regional routes a domestic anchor says nothing about — user's explicit call, see `core/distance_pricing.py`'s comment block for the full reasoning). `core/budget_estimator.py`'s `_COST_MATRIX` (moderate/premium stay/food tiers) remains fully unrecalibrated — no real data point has been applied to it yet.

**New this session — public dataset research (not yet applied to code):** three background research passes, citation-backed:
- **India-domestic flights**: best pick is Kaggle "Flight Price Prediction" (shubhambathwal, 300K rows, CC0, 6-metro EaseMyTrip data, Feb–Mar 2022); no dataset found for India-origin international routes. Recommends ~1.15–1.25× nominal uplift for 2022→2026 pricing; relative distance-band ratios likely still stable. Requires a Kaggle account/API token (no anonymous download).
- **Indian Railways fares**: no official downloadable per-km table exists (CRIS/PRS uses a private telescopic slab lookup). Back-calculated approximate ₹/km slabs from real seat61.com fares (LOW-MEDIUM confidence, ±15–20%); HIGH-confidence surcharges (reservation charge, superfast surcharge, 5% GST on AC only, Tatkal 10%/30%, train-type multipliers, Rajdhani/Shatabdi flexi-fare ladder) are solid. Recommends validating against `erail.in/train-fare` before use.
- **World flight/hotel datasets**: candidate sources identified (US DOT/BTS DB1B, an Expedia-scrape "Flight Prices" dataset, Kaggle "Hotel Booking Demand", Inside Airbnb per-city listings) as a path to a worldwide fare-band model and a global/Indian hotel cost-tier model.

None of this dataset research has been downloaded or applied to `_COST_MATRIX`/`DISTANCE_BANDS` yet — most of it is gated on setting up Kaggle API access, and none of it has been cross-checked the way the 3 screenshot anchors were. Treat as reference material for the next recalibration pass, not yet-verified numbers. Full detail in `TECHNICAL_DOCUMENTATION.md` §14 v10.28.

**✅ Built earlier this session — `apps/api/scripts/recalibrate_pricing.py`:** a documented helper with (a) ready-to-open Google Flights/Skyscanner search links for one route per remaining flight band (regional/long-haul/ultra-long-haul) and Booking.com/Numbeo links for one destination per remaining cost-matrix tier (moderate/premium), and (b) a CLI that takes whatever real number you found and does the same "anchor + nudge neighbours just enough to stay monotonic" recalibration the Bengaluru→Colombo fix did by hand, printing a diff + a ready-to-paste updated table. Doesn't edit source files itself (recalibration is worth a glance before landing). 11 unit tests cover the monotonicity-preserving arithmetic in both directions and confirm it never mutates the real tables it reads.

**Still needed (updated 2026-07-21):** `_COST_MATRIX`'s premium-tier food figures are now recalibrated (via real Numbeo data, not this script — Numbeo isn't JS-rendered so it could actually be fetched, unlike Booking.com/Skyscanner) — see the top of item 10 below. `stay_per_night_pp` for both moderate and premium tiers is still unrecalibrated (no free, scrapeable hotel-pricing source found yet), and a decision on whether to pursue Kaggle API access for the dataset research above is still open.

**🆕 2026-07-21 (later, later) — `stay_per_night_pp` recalibrated for moderate/premium, then re-sourced again for licensing (⚠️ superseded).** Originally recalibrated via **budgetyourtrip.com** ($96/day Bangkok, $350/day Paris → ₹7,968/₹29,050). **This source was found mid-session to prohibit commercial use in its ToS** — see the "licensing fix" section at the very top of this file for the full remediation (replaced with Wikivoyage + an empirically-derived multiplier, ending at ₹7,916/₹29,049 — numerically almost identical, now compliantly sourced). Treat this paragraph as historical context only; the top section is the current state. **Remaining gap, still open**: economical-style stay anchors for both tiers still need their own anchors, and the premium-tier food figures below were Numbeo-sourced and have the **same unresolved licensing problem** — see the top section's "still open" callout.

### 12. Fix the Borough Market / Harry Potter recurring precision miss — ✅ done 2026-07-20

Was a real bug in `services/poi_pinning.py`'s wiki-fallback verification (`verify_candidates_sync`), which confirmed a candidate name is *mentioned* in a destination's general Wikivoyage text but did zero thematic-relevance checking against the named interest — why "Borough Market" kept getting pinned for "Harry Potter" in London. **Fixed:** the wiki fallback now requires the matched chunk to also contain a keyword from the named interest (`_interest_keywords`, `_INTEREST_STOPWORDS`) before counting as verified; a wiki mention with no thematic tie is now dropped rather than force-pinned. Named regression tests added in `tests/unit/test_interest_pinning.py` (`test_wiki_match_without_thematic_relevance_is_dropped`, `test_wiki_match_with_thematic_relevance_in_different_chunk_still_dropped`, `test_wiki_fallback_without_source_interest_keeps_existence_only_check`). Full backend suite green (304 passed, 6 skipped, 1 pre-existing unrelated collection error in `test_budget_estimator.py`). **Scope note:** only the wiki path was touched — the OSM path still has no thematic check (narrower risk, exact-name match against curated map nodes), so "verified" ≠ "relevant" is still a live distinction in general.

### 13. Build a data-completeness pre-flight eval check against the real Qdrant cluster — ✅ done 2026-07-20

Added `eval/data_completeness_scoring.py` (pure scoring: `MIN_WIKI_CHUNKS`, `MIN_OSM_POIS`, `MAX_CATEGORY_SHARE` thresholds) + `eval/run_data_completeness_check.py` (runner — scrolls the real `wiki`/`osm_pois` collections for the same 16 destinations the refinement-fidelity dataset already exercises, via `services.gems._scroll_destination`). Checks per destination: non-zero wiki chunk count, a minimum OSM POI count, no single OSM tag category exceeding a dominance share (the exact shape of this session's category-starvation bug). Tracked as its own pass-rate gate, not folded into `fidelity`/`honest`. Run with `cd apps/api && .venv/bin/python -m eval.run_data_completeness_check` — exits non-zero on any failing destination; refuses-to-be-meaningful warning if `QDRANT_URL=:memory:`. 12 new unit tests (mocked Qdrant). **Not yet done:** wiring into CI/a scheduled job, or actually running it against the real production cluster (recommended next session, same "confirm before batch action" caution as item 2's re-ingestion).

### 11. Verify the stay/food RAG-grounding path actually fires once Reddit/Wikivoyage ingestion is unblocked

`core/budget_estimator.py`'s `_grounded_or_flat()` (via `core/cost_grounding.py::community_median_price_inr()`) is wired up and tested, but as of 2026-07-20 it's mostly a no-op in production — verified live against the real Qdrant Cloud cluster that `reddit` collection has 0 points (`itinerary_corpus` has 1). **Updated 2026-07-20:** the `wiki` collection's 0-points state is now root-caused and fixed (see the new section at the top of this doc — a MediaWiki markup change had silently broken `scrapers/wikivoyage.py` for every destination); London now has 21 real wiki chunks after re-ingestion. Once other destinations are re-ingested (item 2) and item 4 (Reddit approval) lands, spot-check a few real wizard budget-recommendation conversations and confirm `stay_community_based`/`food_community_based` actually flip to `true` for at least some destinations, and that the extracted numbers look sane (not a regex false-positive from an unrelated dollar amount in a Reddit post).

## 🔧 Operational / hygiene items (carried over)

- **Implement Reddit destination-matching widening** (design in `docs/scaling-tech-challenges.md` §8 item 4, not yet done): `scrapers/reddit.py::_extract_destination()` still only recognizes names in the static `KNOWN_DESTINATIONS` list — should match against `destination_ingestion_state` instead now that it exists, so organically-mentioned destinations outside the curated set aren't silently dropped. Low priority until Reddit ingestion itself is unblocked (item 4).
- **Rate-limit new-destination cold starts** — ✅ done 2026-07-22: `services/destination_ingestion.py` now enforces a process-global sliding-window cap (`_MAX_COLD_STARTS_PER_HOUR = 5`) on first-ever-request ingestions via `_cold_start_budget_available()` — exhausted-budget requests are skipped (not persisted, so they're retryable once the window clears) and logged at WARNING. Scoped as global rather than per-IP/session: no caller identity reaches this function today (would need request-context plumbing through `chains/itinerary_chain.py`, a bigger change). 4 new unit tests in `tests/unit/test_destination_ingestion.py`.
- ~~**Consider indexing other frequently-filtered payload fields**~~ **✅ audited 2026-07-21** — every `FieldCondition` usage across the codebase (`core/qdrant.py`, `services/gems.py`, `services/rag_fallback.py`, `services/search.py`) filters on `destination`, already indexed everywhere `_ensure_collections()` runs. No further gap found.
- **Retry/backoff on `fetch_osm_pois` (Overpass) and `scrape_wikivoyage` — ✅ done 2026-07-20** (found 2026-07-20, same day): both used to silently return `[]` on any request failure including Overpass's frequent transient `504 Gateway Timeout` under load. Both now retry up to 3 attempts with linear backoff (5s/10s), logging a WARNING on final exhaustion. `ensure_destination_ingested()` also now logs a WARNING when a first-time ingestion returns zero OSM *and* zero wiki data (the observability blind spot is closed). See item 2 above for full detail + tests.
- **Clean up stale/orphaned Qdrant points on re-ingestion — ✅ done 2026-07-20** (found 2026-07-20, same day): `ingest_osm_pois()`/`ingest_wikivoyage()` now delete-then-upsert per destination via new `core/qdrant.py::delete_stale_destination_points()`, instead of only ever adding new points. See item 2 above for full detail + tests. (Note: the actual live re-ingestion run that benefits from this fix is still pending — tracked separately as `osm-poi-live-reingest`.)
- **No popularity/notability signal in OSM POI selection (found 2026-07-20)**: within a tag category, whichever nodes Overpass happens to return first survive truncation — there's no preference for globally-recognizable landmarks over minor same-tagged ones. This is why highly-known places (Leadenhall Market, Millennium Bridge) didn't survive London's truncation even after the round-robin fix. Future refinement: weight by OSM `wikidata`/`wikipedia` tag presence (a reasonable free proxy for "this place is notable") ahead of untagged nodes in the same category.
- **No hard per-category cap in OSM POI round-robin (found 2026-07-20)**: round-robin (`scrapers/osm.py::_prioritize_landmarks`) guarantees every category gets a turn, but if one category has far more raw nodes within the ingestion radius than every other category combined (e.g. Paris's metro stations), it still fills most of the leftover slots after others are exhausted. A harder rule (e.g. "no category may exceed N% of the final result") would cap this further, at the cost of sometimes returning fewer than the target total — worth prototyping once there's real eval data on whether this actually hurts itinerary quality, rather than guessing at a threshold now.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists.
- ~~optional §4U: point `run_rag_eval.py` at `retrieve_context()`~~ **✅ done (issue #50)** — `eval/run_rag_eval.py` now calls `retrieve_context(trip_config, enable_reranking=True)` instead of the isolated `semantic_search()` path. Schema mismatch solved via `build_trip_config()`: synthesizes a minimal `TripConfig` per golden-dataset case, with 9/20 cases now carrying `personas`/`purpose`/`crowd_preference` overrides that map to the same query-expansion keywords production uses (see `docs/eval-set.md` §4U for the full writeup, including a real finding — MRR/nDCG dropped materially once measured through the real 3-query RRF-fused production path vs. the old single-query harness, and `q_rome_scam` now returns zero relevant results). New regression test `tests/unit/test_run_rag_eval.py` guards against drifting back to the isolated path. `ruff` clean; 952 passed/6 skipped on the full unit suite.
- Windows gotcha: `git commit -m` with embedded double quotes breaks in PowerShell 5.1 — write message to a file, use `git commit -F`.
- Gotcha: always verify `settings.qdrant_url` isn't `:memory:` before trusting a local ingestion script's results — check `get_qdrant().get_collection(name).points_count` against the real cluster rather than assuming from prior session notes.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate accommodation pricing** — blocked on partner approval.
- 🎙️ **Anya's own branded voice** (ElevenLabs or equivalent) — **founder decision 2026-07-28: long-term,
  gated on traction.** Full write-up in `docs/GTM_STRATEGY.md` §5 Phase 3. Short version: Anya has a
  written personality but no voice of her own — the Web Speech API means she is whatever voice the
  user's device happens to have, which on most Windows desktops is *no Hindi voice at all* and on
  Android is a voice we cannot even identify the gender of. A cloud voice fixes device fragmentation,
  makes the persona ownable, and stops Hindi speech being a device lottery. It also flips voice from
  free/offline/zero-latency to per-character billing plus a network round trip on the latency-critical
  reply path, and adds a third production key to a project that has already shipped two features which
  silently no-opped in prod because their key was never set on Railway. **Do not start with the
  integration — start with the measurement:** nothing currently instruments voice-mode activation, so
  the usage number that would justify the spend does not exist yet.

## 📋 Phase 2 preview (publish is done — Phase 2 can start once founder signs off on the piece)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
