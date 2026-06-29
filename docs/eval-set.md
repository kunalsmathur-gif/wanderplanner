# WanderPlan — Evaluation Set
**Version:** 4.0 · **Date:** June 29, 2026  
**Scope:** All AI, API, and integration surfaces across WanderPlan v5.2  
**Purpose:** Manual and automated regression testing for correctness, safety, tone, cost and reliability

RAG eval coverage: **RAG-001 to RAG-081** (81 cases — 61 implemented ✅, 20 pending ❌)  
Non-RAG coverage: **ANYA-W, ANYA-V, ITN, CITIES, CMP, CHAT, SCORE, EXT, COST, BOOKING, WIKI, MOB, THEME** (160+ cases)

---

## How to Use This Document

Each section maps to one system component. Every test case has:

| Field | Meaning |
|---|---|
| **ID** | Unique test identifier (e.g. `ANYA-W-001`) |
| **Input** | Exact input to send |
| **Expected output** | What a correct response looks like |
| **Pass criteria** | Measurable / binary assertion |
| **Failure signal** | What a bad response looks like |
| **Priority** | P0 = ship-blocker · P1 = high · P2 = nice-to-have |

---

## Section 1 — Anya Wizard Chatbot (`POST /api/wizard-chat`)

These tests exercise `wizard_chat_chain.py`. Send via the `/api/wizard-chat` endpoint with the exact `messages` and `partial_config` shown.

### 1A — Field Extraction

| ID | Input message | partial_config sent | Expected config_patch | Pass criteria | Priority |
|---|---|---|---|---|---|
| ANYA-W-001 | `"I want to go to Bali for 7 days"` | `{}` | `{destination: {city:"Bali",...}, dates: {duration_days: 7}}` | Both fields extracted in one turn | P0 |
| ANYA-W-002 | `"yaar 5 din ki Bali trip, budget 1 lakh types"` | `{}` | `{destination: {city:"Bali",...}, dates:{duration_days:5}, budget:{amount:100000, currency:"INR"}}` | Hinglish parsed; budget parsed from "1 lakh" correctly | P0 |
| ANYA-W-003 | `"honeymoon trip"` | `{}` | `{purpose: "honeymoon"}` | Purpose extracted | P0 |
| ANYA-W-004 | `"2 adults, 1 kid aged 4 and my parents"` | `{}` | `{group: {adults:2, kids:[4], seniors:2}}` | All 4 group sub-fields extracted; kids is `[4]` not `[{"age":4}]` (LLM format) | P0 |
| ANYA-W-005 | `"budget trip, around 25-30k"` | `{}` | `{budget: {amount: ~27500, currency:"INR"}}` | Amount in reasonable range (25000–30000) | P1 |
| ANYA-W-006 | `"4 lakh budget"` | `{}` | `{budget: {amount: 400000, currency:"INR"}}` | "4 lakh" → 400000, not 4000 or 40000 | P0 |
| ANYA-W-007 | `"I want a relaxed trip"` | `{purpose:"leisure"}` | `{pace: "relaxed"}` | Pace extracted; existing purpose not overwritten | P1 |
| ANYA-W-008 | `"packed itinerary, lots to do"` | `{}` | `{pace: "packed"}` | Pace = packed | P1 |
| ANYA-W-009 | `"Sri Lanka"` | `{}` | `{destination_mode: "country", destination_country: "Sri Lanka"}` or cities follow-up | Either extracts country mode OR asks which cities | P0 |
| ANYA-W-010 | `"exploring Southeast Asia"` | `{}` | `{destination_mode: "exploring"}` | Mode = exploring, NOT fixed destination | P1 |

### 1B — Field Validation & JSON Schema

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| ANYA-W-011 | Response JSON must parse | Call `/api/wizard-chat` with any valid input | `json.loads(response.text)` succeeds | `reply`, `chips`, `config_patch`, `ready_to_generate`, `summary` all present | P0 |
| ANYA-W-012 | `config_patch` never empty when user gave info | Send "Japan 10 days" | `config_patch` is non-empty `{}` | `len(config_patch) > 0` | P0 |
| ANYA-W-013 | `ready_to_generate` only true when all 6 fields present | Send with partial_config missing budget | `ready_to_generate: false` | Must be false | P0 |
| ANYA-W-014 | `ready_to_generate` true when all 6 fields present | Send partial_config with purpose, destination (fixed city), dates, budget, group, pace | `ready_to_generate: true` | Must be true | P0 |
| ANYA-W-015 | Response under 200 words | Any single-turn message | `reply` word count ≤ 200 | `len(reply.split()) <= 200` | P1 |
| ANYA-W-016 | `chips` is a JSON array, never `{...}` inline text | Any pace/purpose question | `chips` is `list`, not embedded in `reply` | `isinstance(chips, list)` | P0 |

### 1C — Thought-Process & Tone Safety

| ID | Input | Forbidden in `reply` | Pass criteria | Priority |
|---|---|---|---|---|
| ANYA-W-017 | Any input | `config_patch`, `destination_mode`, `missing field`, `partial_config`, `required field`, `slot` | None of these strings appear in `reply` | P0 |
| ANYA-W-018 | Any input | Internal JSON fragments (`{"reply":`, `"config_patch":`) | No raw JSON visible in `reply` | P0 |
| ANYA-W-019 | Any input | `thought_process` key | `"thought_process"` not present in response object | P0 |
| ANYA-W-020 | `"What is the capital of France?"` | Off-topic answer | Anya politely redirects to travel planning | Reply mentions travel or redirects | P1 |

### 1D — Chips

| ID | Scenario | Expected chips | Pass criteria | Priority |
|---|---|---|---|---|
| ANYA-W-021 | First turn, purpose unknown | `["Leisure 🏖️", "Adventure 🏔️", "Honeymoon 💑", "Family 👨‍👩‍👧", "Business 💼", "Solo 🎒"]` (any subset) | chips array non-empty, human-readable labels | P0 |
| ANYA-W-022 | Pace question asked | `["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"]` (or similar) | chips array has 3 pace options | P0 |
| ANYA-W-023 | Stage 2 checkpoint ("anything else?") | Contextual optional add-ons (themes, dietary, etc.) | chips present, not purpose/pace chips again | P1 |

### 1E — Stage 2 → Stage 3 Flow

| ID | Scenario | partial_config | Expected | Priority |
|---|---|---|---|---|
| ANYA-W-024 | All 6 fields filled → checkpoint message | All 6 required fields present, `_checkpoint_asked` absent | Anya sends a trip summary and asks "Shall I generate?" | P0 |
| ANYA-W-025 | User confirms after checkpoint | All 6 fields + `_checkpoint_asked: true`, user says "yes, go ahead" | `ready_to_generate: true` in response | P0 |
| ANYA-W-026 | `summary` field populated at ready state | All 6 filled, `_checkpoint_asked: true`, user confirms | `summary` is a human-readable trip description | P0 |

---

## Section 2 — Anya Voicebot (Browser Web Speech API)

These tests are **manual** (browser-only). Voice uses `window.SpeechRecognition` (STT) and `window.SpeechSynthesis` (TTS) — no server component.

### 2A — Speech-to-Text (Input)

| ID | Test scenario | Steps | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| ANYA-V-001 | Basic STT trigger | Click mic button in wizard | Mic icon turns active; input placeholder changes to "Listening…"; text input is disabled | UI feedback updates immediately | P0 |
| ANYA-V-002 | Spoken message captured | Say "I want to go to Tokyo for 10 days" clearly | Transcript appears in chat as user message | Transcript contains "Tokyo" and "10 days" (or close) | P0 |
| ANYA-V-003 | Auto-submit on silence | Speak naturally, then pause 2–3 seconds | Message auto-sent after silence (no manual Enter needed) | Chat shows user message and Anya responds | P0 |
| ANYA-V-004 | Hinglish STT | Say "yaar Bali trip chahiye 7 din ka" | Transcript in chat approximately matches spoken words | Key words (Bali, 7, din) captured | P1 |
| ANYA-V-005 | STT stop on X click | Activate voice, then click X (close) | `speechSynthesis.cancel()` called; mic stops; no orphan recognition | No crash; wizard closes cleanly | P1 |
| ANYA-V-006 | Mic unavailable (deny permission) | Block microphone in browser, click mic button | Graceful error message displayed | No silent failure; UI shows feedback | P1 |
| ANYA-V-007 | STT in non-Chrome browser (Firefox) | Open in Firefox, click mic | `webkitSpeechRecognition` fallback used or feature disabled gracefully | No JS crash in console | P2 |

### 2B — Text-to-Speech (Output)

| ID | Test scenario | Steps | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| ANYA-V-008 | TTS on Anya response | Enable voice mode, send any message | Anya's reply is read aloud after appearing in chat | Speech starts within 1s of reply appearing | P0 |
| ANYA-V-009 | en-IN female voice preferred | Enable voice, send message on a device with en-IN voices | Voice used is Indian-English female if available | Voice name contains "female" or lang is `en-IN` | P1 |
| ANYA-V-010 | Long reply truncation | Trigger a verbose Anya reply (>100 words) | TTS speaks the reply fully (or at minimum the first sentence) | No speech synthesis crash; text still visible | P1 |
| ANYA-V-011 | TTS cancelled on X close | While Anya is speaking, click close (X) button | Speech stops immediately | `speechSynthesis.cancel()` invoked; silence | P0 |
| ANYA-V-012 | No double-speak | Send a second message while Anya is still speaking | Previous speech cancelled before new speech starts | Only one voice plays at a time | P1 |
| ANYA-V-013 | TTS disabled in text mode | Voice mode off; send a message | No speech synthesis occurs | Silent operation when voice mode is off | P0 |

---

## Section 3 — Itinerary Generator & Mini LLMs

### 3A — Itinerary Generator (`POST /api/generate-itinerary`)

| ID | Input config | Expected output | Pass criteria | Priority |
|---|---|---|---|---|
| ITN-001 | 5 days Phuket, 2 adults, ₹3L budget, relaxed, leisure | 5 days × 3–4 items each | `len(days) == 5`; each day has 3–4 items | P0 |
| ITN-002 | 3 days Tokyo, 1 adult, packed pace | 3 days × 5–6 items each | `len(days) == 3`; each day has 5–6 items | P0 |
| ITN-003 | Group with kid aged 3 (has_young_kids) | No bars, nightclubs, extreme sports | No item tags contain `nightclub`, `bar`, `extreme` | P0 |
| ITN-004 | `digital_nomad` persona | At least 1 Work Block per day | Each day has an item with `work_block` tag | P1 |
| ITN-005 | `sports_fitness` persona | At least 1 Training Window per day | Each day has an item with `training_window` tag | P1 |
| ITN-006 | `pet_parent` persona | All venues dog-friendly | All items have `pet_friendly` or `dog_friendly` tag | P1 |
| ITN-007 | Budget ₹80,000, 2 adults, 5 days Bali | `expense_breakdown.total_inr` ≤ ₹80,000 or LLM flags over-budget | Total does not wildly exceed stated budget (max 20% over) | P0 |
| ITN-008 | Multi-hop: destination=Paris, hops=[Amsterdam] | Days distributed across both cities | Day themes mention both Paris and Amsterdam | P1 |
| ITN-009 | `flexible: true, duration_days: 7` | 7 days generated | `len(days) == 7` | P0 |
| ITN-010 | Response JSON schema | Any valid config | All required fields present per `ItineraryResponse` model | `ItineraryResponse(**response)` parses without error | P0 |
| ITN-011 | `time_start` / `time_end` format | Any config | All times are `HH:MM` format | `re.match(r'^\d{2}:\d{2}$', time)` for all items | P1 |
| ITN-012 | `location.lat` / `location.lon` plausible | Tokyo trip | Lat ≈ 35.x, Lon ≈ 139.x | Coordinates within country bounding box | P1 |
| ITN-013 | `expense_breakdown` all 8 fields present | Any config | All keys present: flights, visa, accommodation, activities, food, local_transport, shopping, emergency_buffer | No missing keys | P0 |
| ITN-014 | `alignment_score` range | Any item | Each item's `alignment_score` between 0 and 100 | `0 <= score <= 100` | P1 |
| ITN-015 | No raw JSON or markdown in item descriptions | Any config | `description` field is plain prose | No `{`, `}`, `**` or `#` in descriptions | P0 |
| ITN-016 | `transit_warnings` field present | Any config | Each `ItineraryDay` has a `transit_warnings` array (may be empty) | `isinstance(day.transit_warnings, list)` for all days | P1 |
| ITN-017 | `local_name` populated for non-English destinations | Tokyo trip | At least 1 item has a non-null `local_name` in Japanese script | `any(item.local_name for item in items)` | P1 |
| ITN-018 | `youtube_search_query` present | Any item with a tour/activity | `youtube_search_query` is non-empty string | `len(item.youtube_search_query) > 0` | P1 |

### 3B — Itinerary SSE Streaming Protocol

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| ITN-019 | SSE `status` events during generation | Stream includes progress events before final result | At least 1 `event: status` with `{message, step, total}` received | `step >= 1` and `total > 0` | P1 |
| ITN-020 | SSE `result` event contains valid JSON | Final event is `event: result` | `json.loads(data)` succeeds and parses as `ItineraryResponse` | Schema validates | P0 |
| ITN-021 | SSE `error` event on Gemini failure | Simulate all 5 model attempts failing (blank API key) | `event: error` emitted with `{code, message, retryable}` | `retryable == true`; no unhandled exception | P0 |
| ITN-022 | 5-model retry chain exhausted | Block Gemini key; call `/api/generate-itinerary` | 5 attempts logged; SSE error event emitted | Logs show 5 distinct model attempts | P1 |

### 3C — City Recommender Mini-LLM (`POST /api/recommend-cities`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| CITIES-001 | country=`Japan`, budget ₹1.5L, 5 days, leisure | 4–6 cities including Tokyo, Kyoto, Osaka | `len(cities)` between 4 and 6; at least 2 major Japanese cities present | P0 |
| CITIES-002 | country=`Sri Lanka`, group with kids, relaxed | Family-friendly cities (Colombo, Galle, Kandy) | All city `reason` fields mention family or kids-friendly | P1 |
| CITIES-003 | country=`Thailand`, budget ₹50,000 total (budget tier) | More affordable cities (Chiang Mai, Pai) over expensive ones | `reason` mentions budget or affordable | P1 |
| CITIES-004 | Response schema | Any valid input | `RecommendCitiesResponse(**response)` parses | All cities have name, country, reason, lat, lon | P0 |
| CITIES-005 | `lat`/`lon` plausibility | Japan | All city coordinates within Japan bounding box (24–46°N, 123–148°E) | No (0,0) or out-of-range coordinates | P1 |

### 3D — Destination Comparison (`POST /api/compare-destinations`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| CMP-001 | `destinations=["Bali","Goa"]`, leisure trip, ₹1L | Both destinations scored on 10 parameters | All 10 params present for each destination | `len(params) == 10` per destination | P0 |
| CMP-002 | Any 2 destinations | `overall_score` in 0–100 range | `0 <= overall_score <= 100` for each | Score bounds check | P0 |
| CMP-003 | Group with kids | `family_fit` score reflects kid-friendly constraint | Bali/Goa `family_fit` ≥ 60 (both known family destinations) | `family_fit >= 60` | P1 |
| CMP-004 | Budget tier trip (₹50k) | `budget_fit` reflects affordability | Budget-friendly destination scores higher on `budget_fit` | Relative ordering sensible | P1 |
| CMP-005 | Schema validation | Any valid input | `ComparisonResponse(**response)` parses | All required fields present | P0 |

### 3E — Anya Post-Gen Chat (`POST /api/chat-refine`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| CHAT-001 | `"What's the best time to visit Bali?"`, action=`none` | Factual reply about Bali travel seasons | `action_type == "none"`; `config_patch == null` | No config mutation on factual question | P0 |
| CHAT-002 | `"Can you make it more relaxed?"` with `trip_config.pace="packed"` | `patch_config` action with `{pace:"relaxed"}` | `action_type == "patch_config"`; `config_patch.pace == "relaxed"` | Small change without regeneration | P0 |
| CHAT-003 | `"Change destination to Tokyo"` | `regenerate` action with destination patch | `action_type == "regenerate"`; `major_change == true` | Destination change triggers confirm dialog | P0 |
| CHAT-004 | Budget change >20% | `regenerate` action with new budget | `action_type == "regenerate"`; `major_change == true` | 20%+ budget change is major | P1 |
| CHAT-005 | Non-travel question: `"What's 2+2?"` | Redirect reply | `reply` contains "travel" redirect; `action_type == "none"` | No travel info provided; stays on-topic | P0 |
| CHAT-006 | JSON schema | Any valid message | `json.loads(response)` succeeds | `reply`, `action_type`, `config_patch`, `major_change` all present | P0 |
| CHAT-007 | `action_type` values | Any message | `action_type` is one of `"none"`, `"patch_config"`, `"regenerate"` | `action_type in VALID_TYPES` | P0 |

### 3F — Alignment Scoring (`scoring.py`)

| ID | Scenario | Input | Expected score range | Pass criteria | Priority |
|---|---|---|---|---|---|
| SCORE-001 | Perfect persona match | Item tags = `["work_block","wifi"]`, persona = `["digital_nomad"]` | ≥ 85 | `score >= 85` | P1 |
| SCORE-002 | No persona set | No personas, neutral item | ~85 (neutral default) | `75 <= score <= 95` | P1 |
| SCORE-003 | Negative keyword penalty | Description contains "avoid scam" | Lower score than same item without negative keywords | `score_with_penalty < score_without` | P1 |
| SCORE-004 | Score bounds | Any item | 0 ≤ score ≤ 100 | `0 <= score <= 100` | P0 |

---

## Section 4 — RAG System: Embeddings & Vectorised Search

### 4A — Embedding Service (`core/embeddings.py`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| RAG-001 | Single text embed | `embed(["Bali beach"])` | Returns `list` of 1 vector, dim = 384 | `len(result) == 1 and len(result[0]) == 384` | P0 |
| RAG-002 | Batch embed | `embed(["Tokyo temples", "Kyoto food", "Osaka nightlife"])` | Returns 3 vectors, all dim 384 | `len(result) == 3` | P0 |
| RAG-003 | Empty input | `embed([])` | Returns `[]` | No error; empty list | P1 |
| RAG-004 | Semantic similarity | `embed(["beach holiday"])` vs `embed(["seaside vacation"])` | Cosine similarity > 0.7 | `cosine_sim > 0.7` | P1 |
| RAG-005 | Semantic dissimilarity | `embed(["beach holiday"])` vs `embed(["business conference"])` | Cosine similarity < 0.4 | `cosine_sim < 0.4` | P1 |
| RAG-006 | Deterministic output | `embed(["Tokyo"])` called twice | Both calls return identical vectors | `result_a == result_b` | P1 |

### 4B — Qdrant Collections (`core/qdrant.py`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| RAG-007 | Collections created on startup | Call `get_qdrant()` on fresh in-memory instance | Collections `wiki`, `reddit`, `osm_pois` all exist | All 3 collection names present | P0 |
| RAG-008 | Collection vector dimension | Inspect created collections | Each has `vectors_config.size == 384` | Correct dim — avoids insert errors | P0 |
| RAG-009 | Insert + search round-trip | Insert a test document with `embed(["Bali sunset"])` vector; search for "Bali evening views" | Top result is the inserted document | `hits[0].id == inserted_id` | P0 |
| RAG-010 | Score threshold respected | Search with `score_threshold=0.7` against unrelated content | Returns 0 results | `len(hits) == 0` | P1 |

### 4C — Reddit Highlights Search (`GET /api/reddit-highlights`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| RAG-011 | `destination=Bali&limit=5` (empty Qdrant) | Returns 0 posts or mock posts | No crash; `posts` is a list | `isinstance(posts, list)` | P0 |
| RAG-012 | `destination=Bali&limit=5` (seeded Qdrant) | Top 5 posts about Bali travel | All posts have `title`, `text_preview`, `post_url`, `subreddit`, `score` | Schema validates | P0 |
| RAG-013 | `limit=1` | Exactly 1 post | `len(posts) == 1` | Limit respected | P1 |
| RAG-014 | Deduplication | Seed same post twice; query | Only 1 copy returned | `len({p.post_url for p in posts}) == len(posts)` | P1 |

### 4D — Context Retrieval for Itinerary (`services/search.py`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| RAG-015 | `retrieve_context(trip_config)` with empty Qdrant | Returns empty list | No crash; `summarise_context([])` returns `""` and itinerary still generates with fallback context | P0 |
| RAG-016 | Retrieved context injected into Gemini prompt | Seed wiki content for "Bali"; generate itinerary for Bali | Itinerary mentions at least 1 seeded landmark name | Manual spot check | P2 |

---

### 4E — Wikivoyage Sentence-Boundary Chunking (`scrapers/wikivoyage.py`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-017 | Single section → multiple chunks | Long Wikivoyage "See" section (>500 chars) | N ≥ 2 chunks, each ≤ ~600 chars | `len(chunks) > 1` and `all(len(c) <= 600 for c in chunks)` | P0 |
| RAG-018 | No mid-word cuts | Any long text | Each chunk ends at a sentence boundary (`.`, `!`, `?`) or is the last remaining text | No chunk ends with a partial word | P1 |
| RAG-019 | Minimum length filter | Many short sentences | Chunks < 80 chars dropped or accumulated | `all(len(c) >= 80 for c in chunks)` | P1 |
| RAG-020 | Empty input returns empty list | `""` | `[]` | `chunks == []` | P0 |
| RAG-021 | All content preserved across chunks | Full section text | Joining all chunks contains all unique sentence fragments | `" ".join(chunks)` contains key terms from original text | P1 |

### 4F — Reddit Destination Tagging (`scrapers/reddit.py → _extract_destination`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-022 | Destination in title | `"7 days in Tokyo was amazing"` | `"Tokyo"` | Exact match | P0 |
| RAG-023 | Destination in body (not title) | title=`"Trip report"`, body=`"We visited Bali"` | `"Bali"` | Extracted from body fallback | P0 |
| RAG-024 | Title takes priority over body | title=`"Tokyo guide"`, body=`"also saw Osaka"` | `"Tokyo"` | Title matched first | P1 |
| RAG-025 | No match → `"general"` | `"Pack light and stay hydrated"` | `"general"` | `result == "general"` | P0 |
| RAG-026 | Word-boundary guard | `"Balinese culture"` | `"general"` — NOT `"Bali"` | Partial word does not match | P0 |
| RAG-027 | Multi-word destination | `"What to do in New York for 3 days"` | `"New York"` | Full multi-word match | P0 |
| RAG-028 | Case-insensitive | `"BANGKOK street food"` | `"Bangkok"` | Case mismatch handled | P1 |

### 4G — Reddit Paragraph Chunking (`scrapers/reddit.py → _chunk_reddit_post`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-029 | Multi-paragraph post splits correctly | Body with 3 `\n\n`-separated paragraphs (each ≥ 80 chars) | 3 chunks | `len(chunks) == 3` | P0 |
| RAG-030 | Each chunk prefixed with title | Any multi-paragraph post | Every chunk starts with `"{title}. "` | `all(c.startswith(title) for c in chunks)` | P0 |
| RAG-031 | Empty selftext → title only | `selftext=""` | `[title]` | `chunks == [title]` | P0 |
| RAG-032 | Short paragraphs (< 80 chars) fall back to single chunk | Body with only short paragraphs | 1 chunk = title + full body (first 800 chars) | `len(chunks) == 1` | P1 |
| RAG-033 | Published date stored | Mock post with `created_utc` | `payload["published_date"]` is ISO date string | `re.match(r'^\d{4}-\d{2}-\d{2}$', date)` | P1 |

### 4H — Reciprocal Rank Fusion (`services/search.py → _rrf_merge`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-034 | Result in all 3 lists ranks highest | One chunk appears across all 3 query result lists | That chunk is ranked #1 in merged output | `merged[0].text == shared_chunk.text` | P0 |
| RAG-035 | Deduplication by text prefix | Same chunk in 2 lists | Merged output contains 1 copy | `len(merged) < len(list1) + len(list2)` | P0 |
| RAG-036 | Empty lists return empty | `_rrf_merge([[], []])` | `[]` | No crash, returns empty list | P0 |
| RAG-037 | RRF scores are positive | Any inputs | All merged scores > 0 | `all(r.score > 0 for r in merged)` | P1 |
| RAG-038 | Output sorted descending by RRF score | 3 lists with varying overlap | Scores monotonically decreasing | `scores == sorted(scores, reverse=True)` | P0 |
| RAG-039 | Best semantic score preserved on dedup | Same text at score 0.92 (list 1) and 0.55 (list 2) | Retained result has higher semantic score | `merged[0].score_raw == 0.92` (before RRF override) | P1 |

### 4I — Time-Decay Scoring (`services/search.py → _time_decay_score`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-040 | Recent content retains high score | 7 days old, score=1.0 | Decayed score > 0.95 | `score > 0.95` | P0 |
| RAG-041 | 1-year-old content moderately decayed | 365 days, score=1.0 | 0.70 < score < 0.85 | Within range | P1 |
| RAG-042 | 3-year-old content significantly decayed | 1095 days, score=1.0 | 0.40 < score < 0.65 | Within range | P1 |
| RAG-043 | Score floor enforced | 2000-01-01 (very old), score=1.0 | score ≥ 0.40 | `score >= 0.40` | P0 |
| RAG-044 | Unknown date = moderate penalty | `published_date=None` | `score ≈ 0.85 × base_score` | `abs(score - 0.85) < 0.01` | P0 |
| RAG-045 | Monotonically decreasing with age | 4 dates: 30, 180, 365, 730 days | Scores strictly decreasing | `scores == sorted(scores, reverse=True)` | P0 |
| RAG-046 | Invalid date string handled gracefully | `"not-a-date"` | Falls back to 0.85 penalty | No exception; `score == base × 0.85` | P1 |

### 4J — `summarise_context` end-to-end (`services/search.py`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-047 | Output within token budget | 5 docs totalling 10,000 chars | Output ≤ 2400 chars | `len("".join(result.split("\n\n"))) <= 2400` | P0 |
| RAG-048 | Low-score chunks filtered | 1 doc score=0.2, 1 doc score=0.9 | Only high-score doc in output | Low-score text absent from result | P0 |
| RAG-049 | Fallback when all below threshold | All docs score < 0.35 | All docs returned (no empty context) | `len(result) > 0` | P0 |
| RAG-050 | Near-duplicate deduplication | Two docs sharing > 60% words | Only 1 copy in output | Repeated phrase appears exactly once | P0 |
| RAG-051 | Higher-scored chunk kept after dedup | Dup pair: scores 0.9 and 0.5 | 0.9-scored version in output | Unique phrase from higher-score chunk present | P1 |
| RAG-052 | Stale content outranked by fresh lower-score content | Old high-score vs recent low-score | Recent content appears first | `result.index(fresh_text) < result.index(stale_text)` | P1 |
| RAG-053 | Empty input returns empty string | `[]` | `""` | `result == ""` | P0 |
| RAG-054 | Budget truncation at word boundary | 1 doc of "word " × 200 | Output ends at a complete word | Last char is not mid-word | P1 |

---

### 4K — Query Variant Construction (`services/search.py` §2)

Covers: `retrieve_context()` fires exactly 3 distinct query strings and passes destination through to all of them.

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| RAG-055 | `TripConfig(destination="Barcelona", personas=["culture"])` | `semantic_search` called 3 times | `len(captured_queries) == 3` | P0 |
| RAG-056 | Same config | All queries are distinct | `len(set(queries)) == 3` | P0 |
| RAG-057 | Same config | Destination in every query | `"Barcelona" in q for q in queries` | P0 |
| RAG-058 | 3 queries each returning same duplicate chunk | Output contains chunk exactly once | `texts.count(chunk.text) == 1` (RRF dedup) | P1 |

---

### 4L — Metadata Schema Completeness (`models/common.py`, `§11`)

Covers: every ingested `SearchResult` carries the required metadata fields.

| ID | Field | Source | Expected value | Pass criteria | Priority |
|---|---|---|---|---|---|
| RAG-059 | `published_date` format | Reddit `created_utc` epoch | ISO-8601 date string e.g. `"2023-11-14"` | `datetime.fromisoformat(published_date)` succeeds | P0 |
| RAG-060 | `published_date` not future | Any Reddit post | Date ≤ today | `date <= date.today()` | P0 |
| RAG-061 | Wikivoyage chunk IDs unique within same section | 2 chunks from `("Paris","See")` | Different MD5 hashes | `id_a != id_b` | P0 |
| RAG-062 | Wikivoyage chunk IDs unique across sections | Same text in different sections | Different MD5 hashes | `id_see != id_do` | P1 |
| RAG-063 | `retrieve_context` output dict keys | Any config | Returned dicts contain `text`, `source`, `url`, `score`, `published_date` | All keys present | P0 |

---

### 4M — RAG Fallback Chain (`§4`) ❌ NOT YET IMPLEMENTED

Covers: 3-tier fallback when Gemini fails: cache lookup → RAG skeleton → enhanced mock.

| ID | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-064 | Gemini fails; `itinerary_cache` has cosine ≥ 0.88 match | Return cached JSON | Response matches cached itinerary | P0 | ❌ Pending |
| RAG-065 | Cache miss; `osm_pois` + wikivoyage data exists | Return RAG-skeleton itinerary without LLM | Structured itinerary with seeded POIs, no Gemini call | P0 | ❌ Pending |
| RAG-066 | Both cache + skeleton fail | Return enhanced mock with RAG context | Response includes at least 1 landmark from Qdrant | P1 | ❌ Pending |
| RAG-067 | All 3 tiers fail | Return standard mock itinerary | No crash; valid JSON response | P0 | ❌ Pending |

---

### 4N — Use Case Evals (`§6`) — Partial

| ID | Use Case | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|---|
| RAG-068 | UC1: Itinerary grounding | Qdrant seeded with Louvre docs, request Paris 3-day trip | Louvre appears in day plan | `"Louvre" in itinerary_text` | P0 | ❌ Requires live Qdrant+Gemini |
| RAG-069 | UC3: Traveller sentiment | Reddit doc with "unsafe at night" injected | Safety warning in output | `"avoid" or "caution"` in response | P1 | ❌ Requires live pipeline |
| RAG-070 | UC2: Wizard destination chips | Request `destination_mode="exploring"` | Chips include wiki/OSM sourced locations | Chip labels match known destinations | P1 | ❌ OSM POI not implemented |
| RAG-071 | UC4–UC10 | — | — | — | P2 | ❌ Not yet scoped |

---

### 4O — Itinerary Corpus Pipeline (`§9`) ❌ NOT YET IMPLEMENTED

| ID | Schema Field | Expected type / constraint | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-072 | `source` | non-empty string | `len(source) > 0` | P1 | ❌ Pending |
| RAG-073 | `destination` | matched city name | destination in `KNOWN_DESTINATIONS` | P1 | ❌ Pending |
| RAG-074 | `published_date` | ISO-8601 or `null` | parseable or null | P1 | ❌ Pending |
| RAG-075 | `content_type` | one of `["wiki","reddit","blog","osm"]` | value in allowed set | P1 | ❌ Pending |
| RAG-076 | `quality_score` | float 0–1 | `0 <= quality_score <= 1` | P1 | ❌ Pending |
| RAG-077 | Dual embedding strategy | Config + content vectors | `len(embedding) == 384` for both vectors | P1 | ❌ Pending |

---

### 4P — Generated Itineraries / Persona Fingerprint (`§10`) ❌ NOT YET IMPLEMENTED

| ID | Feature | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|---|
| RAG-078 | `_persona_fingerprint()` | `TripConfig(personas=["solo"], pace="packed")` | Deterministic 8-token string | Same config → same fingerprint | P1 | ❌ Pending |
| RAG-079 | Quality score × cosine re-rank | Two candidates: cosine 0.9/quality 0.3 vs cosine 0.7/quality 0.9 | Second candidate ranked first | `results[0].quality_score == 0.9` | P2 | ❌ Pending |

---

### 4Q — Agentic Router (`§12`) ❌ NOT YET IMPLEMENTED

| ID | Query type | Expected routing | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-080 | Static: `"best restaurants in Rome"` | Qdrant only; no live web call | `router.route(q).source == "qdrant"` | P1 | ❌ Pending |
| RAG-081 | Dynamic: `"flight prices to Tokyo this week"` | Live web search | `router.route(q).source == "web"` | P2 | ❌ Pending |

---

### 5A — Nominatim Geocoding (`GET /api/geocode`)

| ID | Query | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-001 | `q=Tokyo` | `{lat: ~35.68, lon: ~139.69, country_code: "jp"}` | Lat/lon within Japan bounding box | P0 |
| EXT-002 | `q=Sri Lanka` | `{is_country: true, country_code: "lk"}` | `is_country == true` | P0 |
| EXT-003 | `q=Colombo&countrycodes=lk` | City in Sri Lanka | `country_code == "lk"` | P1 |
| EXT-004 | `q=xyzzy_nonexistent_place` | 404 or empty result | No crash; graceful error response | P1 |
| EXT-005 | Rate limiting (1 req/sec) | Two rapid sequential calls | Both succeed; no 429 error | Nominatim ToS compliant | P0 |
| EXT-006 | `display_name` populated | `q=Paris` | `display_name` is non-empty string | `len(display_name) > 0` | P1 |

### 5B — Travel Tips (`GET /api/travel-tips`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-007 | `destination=Kyoto&limit=5` | 5 tips about Kyoto | `len(tips) == 5`; each has title, text_preview, source, post_url | P0 |
| EXT-008 | `source` field values | Any destination | Each tip's `source` is one of: `r/travel`, `r/solotravel`, `TripAdvisor`, `Travel Blog`, `Lonely Planet`, `Nomadic Matt` | `source in ALLOWED_SOURCES` | P1 |
| EXT-009 | Cache hit on second call | Call same destination twice | Second call faster (< 50ms) and returns same results | Response is cached | P1 |
| EXT-010 | `text_preview` length | Any tip | ≤ 250 characters | `len(text_preview) <= 250` | P1 |

### 5C — Gemini API (wizard + itinerary + refine)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-011 | API key missing | Start API with blank `GEMINI_API_KEY`; call `/api/wizard-chat` | Mock fallback returns valid response; no 500 crash | HTTP 200; mock reply served | P0 |
| EXT-012 | Gemini 503 transient error | Simulate 503 response (mock or block key temporarily) | 3 retries attempted with backoff; falls back to smart mock | No 500 to frontend; valid mock reply | P0 |
| EXT-013 | Response within timeout | Any wizard message | Response within `llm_timeout_seconds` (default 30s) | Latency ≤ 30s | P0 |
| EXT-014 | Token limit respected | Send wizard message designed to trigger verbose response | `reply` field ≤ 200 words; JSON not truncated | `json.loads()` succeeds; reply under limit | P0 |
| EXT-015 | No raw JSON leak in reply | Any wizard message | `reply` does not start with `{` or contain `"config_patch":` | Leak detection regex fails | P0 |

### 5D — Deep-Link Integrity (Frontend, Manual)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-016 | Skyscanner link opens | Click any flight deep-link in itinerary | Skyscanner opens with origin + destination pre-filled | URL contains `origin` and `destination` params | P1 |
| EXT-017 | Booking.com link opens | Click accommodation link | Booking.com opens with destination + dates | URL contains city slug and checkin/checkout | P1 |
| EXT-018 | Viator link opens | Click activity booking link | Viator opens on correct destination page | No 404 on link destination | P1 |
| EXT-019 | YouTube search link | Click YouTube icon on activity | YouTube search opens with `youtube_search_query` | URL contains encoded search query | P1 |

### 5E — Start Anywhere: Extract Trip (`POST /api/extract-trip`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-020 | `"Planning a 7-day trip to Kyoto, budget ₹1.5 lakh"` (plain text) | `destination="Kyoto"`, `duration_days=7`, `budget_inr≈150000` | All 3 fields extracted correctly | P0 |
| EXT-021 | URL `https://www.lonelyplanet.com/articles/bali-trip` (valid travel URL) | `destination="Bali"` extracted from fetched page content | `destination` is non-null and matches page content | P0 |
| EXT-022 | Non-travel text: `"Meeting agenda for Q3 planning"` | `destination=null`, `duration_days=null` | Both nulls; no crash; `summary` explains extraction failure | P0 |
| EXT-023 | `"themes: beach, culture"` in text | `themes=["Beach","Culture"]` or similar | `len(themes) >= 1`; items are human-readable strings | P1 |
| EXT-024 | Gemini fails (all 3 retries) | All-null `ExtractedTrip` with summary "Could not extract..." | No crash; 200 response with null fields | P0 |
| EXT-025 | Response schema | Any valid input | All 6 fields present: `destination`, `destination_country`, `duration_days`, `themes`, `budget_inr`, `summary` | `json.loads()` + schema check succeeds | P0 |
| EXT-026 | URL input → HTML stripped | `input` starts with `https://` | Backend fetches URL; Gemini receives text, not raw HTML tags | Extracted data is coherent travel content | P1 |

### 5F — Share Trip (`POST /api/share` + `GET /api/share/{slug}`)

| ID | Test | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| EXT-027 | Slug generation | Valid `POST /api/share` body | Response contains `slug` (8 hex chars) and `url` (`/t/{slug}`) | `re.match(r'^[a-f0-9]{8}$', slug)` | P0 |
| EXT-028 | Round-trip data integrity | Share → retrieve | `GET /api/share/{slug}` returns exact same payload | `stored == retrieved` (itinerary, trip_config, labels) | P0 |
| EXT-029 | Unknown slug returns 404 | `GET /api/share/deadbeef` (not stored) | HTTP 404 response | Status code 404; graceful error body | P0 |
| EXT-030 | URL path format | Any share response | `url` field is `/t/{slug}` | `url.startswith("/t/")` | P0 |
| EXT-031 | Read-only view renders | Open `http://localhost:3000/t/{valid_slug}` | Day-by-day itinerary visible; no edit controls; "View-only" badge shown | Manual: UI renders without errors | P1 |
| EXT-032 | Expired/missing slug page | Open `http://localhost:3000/t/ffffffff` | Error state: "This trip link has expired or doesn't exist." | Manual: error message visible | P1 |

### 5G — Best Time Endpoint (`GET /api/best-time/{city}`)

| ID | Input | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-033 | `/api/best-time/Bali` | `best_months` includes Oct–Apr; `avoid_months` includes Jun–Aug (rainy) | `len(best_months) >= 1`; no overlap between best and avoid lists | P0 |
| EXT-034 | `/api/best-time/Tokyo` | `weather_summary` is non-empty prose | `len(weather_summary) > 20` | P1 |
| EXT-035 | `events` field | Any known city | `events` is a list (may be empty) | `isinstance(events, list)` | P1 |
| EXT-036 | Unknown/obscure city | `/api/best-time/Nowhereville` | Graceful response (may return defaults or empty lists) | No 500 crash; valid JSON response | P0 |
| EXT-037 | Response schema | Any city | All fields present: `best_months`, `weather_summary`, `avoid_months`, `events` | `json.loads()` + schema check | P0 |

### 5H — Health Endpoint (`GET /health`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| EXT-038 | Startup readiness | `GET /health` after server start | `{"status": "ready", "version": "1.0.0"}` | `status == "ready"`; HTTP 200 | P0 |
| EXT-039 | No auth required | `GET /health` without any headers | Returns 200 without credentials | Unauthenticated request succeeds | P0 |

---

## Section 6 — Price Metering for Paid APIs

### 6A — Gemini API Cost Tracking

WanderPlan uses **Gemini 2.0 Flash** (default) or **Gemini 2.5 Flash** (configurable via `gemini_model` env var). Pricing as of June 2026 (verify at [ai.google.dev/pricing](https://ai.google.dev/pricing)):

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Threshold |
|---|---|---|---|
| Gemini 2.0 Flash | $0.075 | $0.30 | — |
| Gemini 2.5 Flash | $0.15 | $0.60 | ≤200k context |
| Gemini 2.5 Flash (thinking) | $3.50 | $10.50 | — |

#### Cost Benchmarks — Measure & Alert

| ID | Scenario | Tokens to measure | Budget threshold | Priority |
|---|---|---|---|---|
| COST-001 | Single wizard turn (one user message) | Input: system prompt (~4500 chars) + history + message; Output: reply JSON | Input ≤ 1800 tokens; Output ≤ 800 tokens | P0 |
| COST-002 | Full wizard conversation (6 turns to ready_to_generate) | Sum of all 6 turns | Total input ≤ 15,000 tokens; Total output ≤ 4,800 tokens | P0 |
| COST-003 | Itinerary generation (5-day trip) | Full prompt + output | Input ≤ 3,000 tokens; Output ≤ 8,000 tokens | P0 |
| COST-004 | Itinerary generation (10-day multi-hop) | Full prompt + output | Input ≤ 4,000 tokens; Output ≤ 14,000 tokens | P1 |
| COST-005 | City recommender | Prompt + output | Input ≤ 800 tokens; Output ≤ 600 tokens | P1 |
| COST-006 | Post-gen chat refine (single turn) | System + history + message | Input ≤ 2,000 tokens; Output ≤ 500 tokens | P1 |
| COST-007 | Travel tips (LLM path) | Prompt + output | Input ≤ 600 tokens; Output ≤ 1,000 tokens | P2 |

#### Cost Per Session Estimate

| Flow | Gemini 2.0 Flash est. | Gemini 2.5 Flash est. |
|---|---|---|
| Full wizard (6 turns) | ~$0.003 | ~$0.007 |
| Itinerary generation (5 days) | ~$0.003 | ~$0.006 |
| 5 post-gen chat turns | ~$0.001 | ~$0.002 |
| **Total per user session** | **~$0.007** | **~$0.015** |

#### Metering Tests

| ID | Test | Method | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| COST-008 | Log token usage per API call | Add `usage_metadata` logging to wizard chain | Each Gemini call logs `prompt_token_count`, `candidates_token_count` | Log line emitted on every call | P0 |
| COST-009 | Verbose response regression | Send a message that previously caused >1500 token output | Output stays ≤ 800 tokens | `candidates_token_count <= 800` | P0 |
| COST-010 | System prompt size stable | Print `len(WIZARD_SYSTEM_PROMPT)` before f-string substitution | ≤ 6,000 characters | Regression alert if prompt grows >10% | P1 |
| COST-011 | No "thinking" model accidentally used | Check `gemini_model` setting in production env | Value is `gemini-2.0-flash` or `gemini-2.5-flash` (not `-thinking` variant) | `"thinking" not in settings.gemini_model` | P0 |
| COST-012 | Retry cost multiplication | Simulate 2 retries before success | Total tokens ≤ 3× single call | Retries don't multiply unboundedly | P1 |

### 6B — Groq API (fallback LLM provider)

Groq is the default `llm_provider` in `config.py`. Pricing as of June 2026 (verify at [console.groq.com](https://console.groq.com)):

| Model | Input | Output |
|---|---|---|
| Llama 3.1 70B Versatile | $0.59/1M tokens | $0.79/1M tokens |

| ID | Test | Expected | Priority |
|---|---|---|---|
| COST-013 | Groq used for itinerary (llm_provider=groq) | Response from Llama 3.1 70B | Itinerary JSON valid; `json.loads()` succeeds | P1 |
| COST-014 | Groq token usage logging | Add `usage` logging to itinerary chain | Logs prompt + completion token counts | P1 |
| COST-015 | Groq rate limit handling | Exceed free tier (30 req/min) | 429 handled gracefully; mock fallback or retry | P1 |

### 6C — Nominatim (Free, Fair-Use Policy)

Nominatim is free but has a **hard limit of 1 req/sec** and requires a valid `User-Agent`.

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| COST-016 | User-Agent set | Inspect outgoing Nominatim request headers | `User-Agent: wanderplan/1.0` | `user_agent == "wanderplan/1.0"` | P0 |
| COST-017 | Rate limiter active | 3 rapid geocode calls | Min 1s between each outgoing HTTP call | No 403/429 from Nominatim | P0 |
| COST-018 | No excessive calls | User types in wizard destination input | Geocode only on submit/confirm, NOT on every keystroke | ≤ 1 geocode call per user action | P1 |

### 6D — OpenStreetMap / Wikivoyage (Free, Attribution Required)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| COST-019 | Attribution shown on map | Open full-screen map in itinerary | "© OpenStreetMap contributors" visible | Attribution text visible in map UI | P0 |
| COST-020 | Wikivoyage attribution | Travel tips sourced from Wikivoyage | Source credited in tip UI | Source label shown | P1 |

---

## Section 7 — Frontend Features (Manual / Browser Tests)

### 7A — BookingHub (`BookingHub.tsx` + `bookingStore.ts`)

| ID | Test | Steps | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| BOOKING-001 | Add a flight booking | Open BookingHub; select "Flight"; fill in name, confirmation, date, amount; save | Booking appears in list immediately | Row visible with correct type icon and data | P0 |
| BOOKING-002 | Remove a booking | Hover over booking row; click delete | Row disappears from list | Booking no longer visible | P0 |
| BOOKING-003 | BookingHub survives page refresh | Add booking; refresh page | Booking still visible after reload | `localStorage["wanderplan-bookings"]` persists entry | P0 |
| BOOKING-004 | Total tracked spend | Add 2 bookings: ₹20,000 and ₹35,000 | Total shown as ₹55,000 | Sum displayed correctly | P1 |
| BOOKING-005 | All 4 booking types selectable | Click each chip: Flight, Hotel, Activity, Transport | Each type selectable; icon changes per type | All 4 chips functional | P1 |

### 7B — Wikipedia Image Resilience (`useWikiImage.ts`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| WIKI-001 | Known city returns photo | `useWikiImage("Tokyo")` | Non-null string URL to Wikipedia image | URL starts with `https://` | P1 |
| WIKI-002 | Network failure returns null | Block Wikipedia API in browser network tab; load inspiration gallery | Gradient fallback shown for all cards; no JS error in console | No crash; gradient visible | P0 |
| WIKI-003 | Image cached for session | Call `useWikiImage("Paris")` twice | Second call instant (no HTTP request) | Only 1 network call per city per session | P1 |

### 7C — Mobile Layout (`ThreeColumnLayout.tsx`)

| ID | Test | Viewport | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| MOB-001 | Mobile bottom tab bar | < 1024px wide | 3 tabs visible at bottom: "Itinerary", "Overview", "Map & Tips" | All 3 tabs clickable and switch content | P0 |
| MOB-002 | Itinerary tab content | Mobile, "Itinerary" tab active | `ItineraryTimeline` visible; no 3-column layout | Single scrollable column | P0 |
| MOB-003 | Map tab renders | Mobile, "Map & Tips" tab active | Leaflet map visible + Column3 tips | No blank map tile | P1 |
| MOB-004 | Full-screen map on mobile | Tap "⤢ Full screen" in Map tab | Map expands full-screen with day-tab toolbar | Toolbar + close button visible | P1 |
| MOB-005 | Wizard full-screen on mobile | Open wizard on mobile | LLMWizard fills entire screen (no 3-column visible) | No horizontal scroll; input above keyboard | P0 |

### 7D — Theme Toggle (`ThemeToggle.tsx`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| THEME-001 | Toggle switches light ↔ dark | Click toggle | All CSS custom properties switch to dark/light values | No flash; colors update immediately | P0 |
| THEME-002 | Theme persists on reload | Set dark mode; refresh page | Dark mode active on reload (no flash) | `localStorage["wp-theme"] == "dark"` | P0 |
| THEME-003 | No FOUC (Flash of Unstyled Content) | Hard-refresh with dark mode saved | Page loads in dark mode with no white flash | Blocking `<head>` script applies theme before render | P0 |

---

## Appendix A — Regression Test Checklist (Run Before Each Release)

```
[ ] ANYA-W-011  JSON schema always parses
[ ] ANYA-W-013  ready_to_generate false when incomplete
[ ] ANYA-W-014  ready_to_generate true when all 6 fields present
[ ] ANYA-W-017  No system terms leak into reply
[ ] ANYA-W-018  No raw JSON in reply
[ ] ANYA-V-001  Voice mic activates correctly
[ ] ANYA-V-011  Voice stops on wizard close
[ ] ITN-001     5-day itinerary generates (correct day count)
[ ] ITN-003     Kids safety filter active
[ ] ITN-010     Itinerary JSON schema valid
[ ] ITN-013     expense_breakdown all 8 fields
[ ] ITN-020     SSE result event contains valid JSON
[ ] CHAT-001    chat-refine action_type=none for factual question
[ ] CHAT-006    chat-refine JSON schema always parses
[ ] EXT-020     extract-trip extracts destination from text
[ ] EXT-022     extract-trip returns nulls for non-travel content (no crash)
[ ] EXT-027     share creates valid 8-char slug
[ ] EXT-028     retrieved share payload matches stored data
[ ] EXT-029     unknown share slug returns 404
[ ] EXT-038     GET /health returns status=ready
[ ] RAG-007     Qdrant collections created on startup
[ ] EXT-001     Geocode returns correct coords for Tokyo
[ ] EXT-011     Mock fallback works with blank API key
[ ] EXT-012     Gemini 503 retried, doesn't crash
[ ] BOOKING-003 BookingHub survives page refresh
[ ] COST-009    Verbose response regression (≤800 tokens out)
[ ] COST-011    No thinking model in production
```

## Appendix B — How to Run Automated Cases

```bash
# Unit + integration tests (existing)
cd apps/api && .venv/bin/pytest tests/ -v

# Wizard chat — field extraction smoke test
curl -X POST http://localhost:8000/api/wizard-chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Tokyo 7 days, 2 adults, budget 2 lakh"}],"partial_config":{}}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('patch:', r['config_patch']); print('ready:', r['ready_to_generate'])"

# Ready-to-generate guard
curl -X POST http://localhost:8000/api/wizard-chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"yes go ahead"}],"partial_config":{"purpose":"leisure","destination":{"city":"Tokyo","country":"Japan","lat":35.68,"lon":139.69},"dates":{"start":"2026-11-01","end":"2026-11-07","flexible":false},"budget":{"amount":200000,"currency":"INR"},"group":{"adults":2,"kids":[],"seniors":0,"infants":0,"pets":0},"pace":"moderate","_checkpoint_asked":true}}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('ready_to_generate:', r['ready_to_generate'])"

# Extract trip — text input
curl -X POST http://localhost:8000/api/extract-trip \
  -H "Content-Type: application/json" \
  -d '{"input":"7 day trip to Kyoto, budget 1.5 lakh, we love temples and food"}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r)"

# Chat refine — action_type check
curl -X POST http://localhost:8000/api/chat-refine \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Make it more relaxed"}],"trip_config":{"pace":"packed","destination":{"city":"Bali"}}}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('action:', r['action_type'])"

# Share trip
curl -X POST http://localhost:8000/api/share \
  -H "Content-Type: application/json" \
  -d '{"itinerary":{"days":[],"alignment_score":80},"trip_config":{},"labels":{},"destination_label":"Bali, Indonesia"}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('slug:', r['slug'])"

# Health check
curl http://localhost:8000/health

# Geocode
curl "http://localhost:8000/api/geocode?q=Bali"

# Best time
curl "http://localhost:8000/api/best-time/Tokyo"

# Token usage (add to wizard_chat_chain.py logging)
grep "token_count" /tmp/api.log | tail -20
```

---

*Maintainer: Engineering · Review cycle: Before each release · Last updated: June 2026*
