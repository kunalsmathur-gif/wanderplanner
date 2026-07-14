# WanderPlanner — Evaluation Set
**Version:** 5.1 · **Date:** July 12, 2026 (adds §4V refinement-fidelity harness)  
**Scope:** All AI, API, and integration surfaces across WanderPlanner v5.3 (RAG Optimization Round 2)  
**Purpose:** Manual and automated regression testing for correctness, safety, tone, cost and reliability

RAG eval coverage: **RAG-001 to RAG-090** (90 cases — 74 implemented ✅, 1 partial ⚠️, 15 pending ❌)  
Also see: **Golden Dataset & Automated Retrieval Metrics** (§4U below) for the separate `run_rag_eval.py` scoring suite (not individually numbered test cases — a single automated harness with 12 labeled queries against a 40-chunk curated corpus).  
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

### 4M — RAG Fallback Chain (`§4`) ✅ DONE

Covers: 3-tier fallback when the LLM fails: cache lookup → RAG skeleton → enhanced mock. Implemented in `chains/itinerary_chain.py::_fallback_itinerary()`, `services/itinerary_cache.py`, `services/rag_fallback.py`.

| ID | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-064 | Gemini fails; `itinerary_cache` has cosine ≥ 0.88 match | Return cached JSON | Response matches cached itinerary | P0 | ✅ Done — `test_fallback_tier1_cache_hit` |
| RAG-065 | Cache miss; `osm_pois` data exists (≥3 POIs) | Return RAG-skeleton itinerary without LLM | Structured itinerary with seeded POIs, no Gemini call | P0 | ✅ Done — `test_fallback_tier2_rag_skeleton_builds_from_osm_pois` |
| RAG-066 | Both cache + skeleton fail (< 3 POIs) | Return enhanced mock with RAG context | Response includes at least 1 real tip spliced from retrieved wiki/reddit content | P1 | ✅ Done — `test_fallback_tier3_enhanced_mock_splices_real_tips` |
| RAG-067 | All 3 tiers fail (no Qdrant data at all) | Return standard mock itinerary | No crash; valid JSON response | P0 | ✅ Done — negative-path tests for all 3 tiers in `test_rag.py` |

---

### 4N — Use Case Evals (`§6`) — Partial

| ID | Use Case | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|---|
| RAG-068 | UC1: Itinerary grounding | Qdrant seeded with Louvre docs, request Paris 3-day trip | Louvre appears in day plan | `"Louvre" in itinerary_text` | P0 | ❌ Requires live Qdrant+Gemini |
| RAG-069 | UC3: Traveller sentiment | Reddit doc with "unsafe at night" injected | Safety warning in output | `"avoid" or "caution"` in response | P1 | ❌ Requires live pipeline |
| RAG-070 | UC2: Wizard destination chips | Request `destination_mode="exploring"` | Chips include wiki/OSM sourced locations | Chip labels match known destinations | P1 | ⚠️ Partial — OSM POI ingestor now built (`scrapers/osm.py`), but not yet wired into wizard destination-chip suggestions; currently only consumed by the RAG-skeleton fallback (§4M) |
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
| RAG-079 | Quality score × cosine re-rank (persona fingerprint based) | Two candidates: cosine 0.9/quality 0.3 vs cosine 0.7/quality 0.9 | Second candidate ranked first | `results[0].quality_score == 0.9` | P2 | ❌ Pending — **not the same as the cross-encoder reranker shipped this cycle** (see §4T); this is a separate, still-unbuilt persona-quality-score rerank over the `generated_itineraries` learning flywheel |

---

### 4Q — Agentic Router (`§12`) ❌ NOT YET IMPLEMENTED

| ID | Query type | Expected routing | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-080 | Static: `"best restaurants in Rome"` | Qdrant only; no live web call | `router.route(q).source == "qdrant"` | P1 | ❌ Pending |
| RAG-081 | Dynamic: `"flight prices to Tokyo this week"` | Live web search | `router.route(q).source == "web"` | P2 | ❌ Pending |

---

### 4R — Hybrid Search: BM25 + Semantic (`services/search.py`) ✅ DONE

| ID | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-082 | BM25 scores a proper-noun query higher for exact-match chunk | Query "Tanah Lot", corpus with & without "Tanah Lot" in text | Chunk containing the literal term ranks in the fused top-k | `TestHybridBM25Search` in `test_rag.py` | P1 | ✅ Done |
| RAG-083 | Hybrid search gated by `settings.hybrid_search_enabled` | Flag set `False` | Falls back to pure semantic search, no BM25 scroll call | Mocked flag, assert `_bm25_search_collection_sync` not called | P1 | ✅ Done |
| RAG-084 | RRF fusion of BM25 + semantic rankings | Both ranking lists provided | Fused order matches manual RRF calculation | Unit-tested via existing `_rrf_merge()` reused for this fusion | P1 | ✅ Done |

---

### 4S — HyDE Query Augmentation (`services/hyde.py`) ✅ DONE

| ID | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-085 | `generate_hypothetical_passage()` output is deterministic and non-empty | Same trip_config inputs called twice | Identical passage text both times | P1 | ✅ Done — `TestHyDEPassageGeneration` |
| RAG-086 | Persona hooks appear in the synthesized passage | `personas=["digital_nomad"]` | Passage mentions co-working/wifi-related language | P2 | ✅ Done |
| RAG-087 | HyDE applied only to the vibe query variant, not BM25 | Inspect `retrieve_context()` call args | BM25 receives the raw query text; semantic search receives the HyDE passage | P1 | ✅ Done |

---

### 4T — Cross-Encoder Reranking (`core/embeddings.py`, `services/search.py`) ✅ DONE (scoped)

| ID | Scenario | Expected | Pass criteria | Priority | Status |
|---|---|---|---|---|---|
| RAG-088 | Reranker reorders candidates by joint (query, doc) relevance | Candidates with misleading independent cosine scores | Reranked order matches cross-encoder ground truth ordering | P0 | ✅ Done — `TestCrossEncoderReranking` |
| RAG-089 | Reranker fails safe on exception | `rerank_scores` raises `RuntimeError` | Falls back silently to incoming RRF order, no crash | P0 | ✅ Done |
| RAG-090 | Reranking disabled by default; only enabled at itinerary-generation call sites | `settings.reranking_enabled` default `False`; `retrieve_context(enable_reranking=True)` only from `_gemini_itinerary()`/`_langchain_itinerary()` | Code inspection + config default assertion | P0 | ✅ Done |

---

### 4U — Golden Dataset & Automated Retrieval Metrics (`eval/golden_dataset.json`, `eval/run_rag_eval.py`) ✅ DONE

Unlike the manual/unit-test cases above, this is an **automated retrieval-quality harness**, not individually numbered test cases. It measures ranking quality directly, independent of LLM output variability.

**Corpus & queries:** `apps/api/eval/golden_dataset.json` — a curated 40-chunk corpus (mix of wiki-style and reddit-style travel content across several destinations/personas) plus 12 labeled queries, each with a hand-picked set of "expected relevant" chunk IDs.

**Seeding quirk:** because `semantic_search()`/`retrieve_context()` always query both the `wiki` and `reddit` collections, the same 40-chunk corpus is seeded into **both** collections at eval time. This means a query can legitimately surface the same underlying chunk twice (once from each collection). `run_rag_eval.py` deduplicates retrieved chunk IDs by first-occurrence before scoring — without this, Recall could exceed 1.0, which is nonsensical. If you're extending this eval script, preserve the dedup step.

**Metrics computed** (`run_rag_eval.py`):
- **Precision@k** — fraction of the top-k retrieved chunks that are actually relevant
- **Recall@k** — fraction of all relevant chunks that appear in the top-k
- **MRR (Mean Reciprocal Rank)** — 1 / rank of the first relevant result, averaged across queries
- **nDCG@k (normalized Discounted Cumulative Gain)** — rewards relevant results appearing higher in the ranking

**Current results** (against `semantic_search()` directly — see limitation below):

| Metric | Value |
|---|---|
| Recall@10 | 1.00 |
| MRR | ≈ 0.85 – 0.94 |
| nDCG@10 | ≈ 0.89 – 0.96 |
| Precision@10 | ≈ 0.18 – 0.21 (expected — hybrid search widens the candidate pool; low precision at k=10 is normal when only 1-4 chunks per query are truly relevant out of a 40-chunk corpus) |

**Known limitation:** `run_rag_eval.py` calls `semantic_search()` directly, which exercises the new hybrid BM25+semantic fusion (§4R) but does **not** exercise HyDE (§4S) or cross-encoder reranking (§4T) — those live only inside `retrieve_context()`, the higher-level function used by actual itinerary generation. A one-off manual smoke test of the full `retrieve_context()` pipeline (HyDE + hybrid + rerank) confirmed correct top-ranked results for a sample digital-nomad Bali query, but this is not part of the automated harness. Extending `run_rag_eval.py` to call `retrieve_context()` instead (with reranking forced on) is a natural follow-up if more rigorous end-to-end pipeline scoring is needed.

**Auth-gating regression note (July 2026):** the itinerary-generation system prompt itself is unchanged by the auth rollout. Code inspection confirms the same `SYSTEM_PROMPT` in `chains/itinerary_chain.py` is still formatted with `{context}` + `{trip_config}` exactly as before; the new work wraps the Gemini call with auth checks (`Depends(get_current_user)` in `routers/itinerary.py`) and post-call usage logging (`track_gemini_usage()` / `flush_llm_usage()`), but does **not** alter prompt content, model selection, or output schema.

**What changes for golden regressions:** this retrieval-only harness still runs in-process and therefore remains unauthenticated, but any **end-to-end** golden run that hits `POST /api/generate-itinerary` must now authenticate first and replay the session cookies. In practice the one-line invocation change is: **log in once, save cookies, then send `-b cookies.txt` (or equivalent session-cookie state) on every itinerary-generation request.** Example shell flow:

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"correct horse battery staple"}'
# then reuse: curl -b cookies.txt -N -X POST http://localhost:8000/api/generate-itinerary ...
```

**Expected outcome:** auth-gating is an access-control change only. Because the prompt, model, and JSON response contract are unchanged, golden-output quality/format expectations should remain the same once the request is made with a valid authenticated session.

**How to run:**
```bash
cd apps/api
python -m eval.run_rag_eval
```

---

### 4V — Refinement-Fidelity Eval Suite (`eval/refinement_fidelity_dataset.json`, `eval/run_refinement_eval.py`) ✅ DONE (v10.18)

The **GTM Phase 1 kill-criterion gate** (GTM_STRATEGY §5): automated scoring of the v10.17 refinement hard-constraints pipeline, plus the apparatus for the published "WanderPlanner vs ChatGPT" comparison. Like §4U this is an automated harness, not individually numbered cases.

**Dataset:** 20 named-interest refinement cases (`RF-001`–`RF-020`): 16 positive (expected verified POIs exist at the destination — London/Edinburgh Harry Potter, Tokyo anime, Kyoto zen, Paris Impressionism, Rome antiquity, Barcelona Gaudí, Liverpool Beatles, LA studios, Singapore hawker food, and six Indian cases: Delhi Mughal, Mumbai Bollywood, Jaipur Rajput, Goa Portuguese, Amritsar Sikh, Bengaluru palaces/gardens) + 4 negative honesty cases (e.g. Harry Potter in Goa) where the correct behaviour is pinning **nothing**. The fixture truth-set (76 real OSM POIs incl. per-destination distractors + 5 wiki chunks) is seeded into an **in-memory Qdrant** — real collections are never read or written. Each positive case carries one invented candidate that must be dropped, so the hallucination guard is itself scored.

**Metrics per positive case** (name matching = production `poi_pinning._names_match`):
- **pin_recall** — expected POIs that became pins
- **pin_precision** — pins that are on-interest
- **inclusion_rate** — pins appearing **exactly once** in the generated itinerary with the `pinned` tag (the hard-constraint contract)
- **stability_rate** — pins surviving an unrelated pace-change re-refinement + regeneration (diff fidelity)
- **fidelity** = 0.4·recall + 0.4·inclusion + 0.2·stability

Negative cases score **honesty**: zero pins and no unverified name leaked into the itinerary.

**Modes:**
- offline (default) — replays recorded expansion candidates through the real verification/pinning/generation (mock LLM) code. Deterministic, free, zero network. This is the regression gate: it scores **1.000 by construction** while the pipeline is intact (guaranteed by dataset-consistency unit tests in `tests/unit/test_refinement_eval.py`); any drop is a regression.
- `--live` — real Gemini detection + expansion + generation (~$0.02/case): produces the actual kill-criterion numbers.
- `--baseline eval/baselines/chatgpt_refinement.json` — scores manually recorded ChatGPT answers (protocol + paste-ready prompts in `chatgpt_refinement.template.json`) with the same matcher/truth-set: verified recall, unverifiable-suggestion rate, honesty. Renders the comparison table into `eval/out/refinement_fidelity_report.md`.

**How to run:**
```bash
cd apps/api
python -m eval.run_refinement_eval                 # offline regression gate
python -m eval.run_refinement_eval --live          # kill-criterion numbers (needs GEMINI_API_KEY)
python -m eval.run_refinement_eval --baseline eval/baselines/chatgpt_refinement.json
python -m eval.run_refinement_eval --results eval/out/refinement_fidelity_results.json --baseline <file>   # rescore a saved run against a baseline without re-running
```

**First live results (2026-07-13, v10.18.2):**

| Metric | WanderPlanner (live) | ChatGPT free tier | Claude Sonnet |
|---|---|---|---|
| Verified-POI recall | 0.750 | 1.000 | 0.979 |
| Unverifiable-suggestion rate | 0.000 (structural) | 0.747 | 0.786 |
| Strict honesty on impossible asks | 4/4 | 0/4 (incl. invented "Wizarding World Goa") | 0/4 strict — but all 4 answers explicitly stated the ask can't be served (raw responses in baseline file) |
| Inclusion / stability (itinerary follow-through) | 0.771 / 0.812 | n/a | n/a |

Known live defects dragging recall (fix before publishing): RF-004/RF-014/RF-016 produced zero pins (detection/expansion failure — diacritics + interest phrasing suspected); RF-007 pins under-honoured in generation; RF-001 pinned distractor Borough Market.

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
| EXT-007 | `destination=Kyoto&limit=5` | 5 tips about Kyoto | `len(tips) == 5`; each has title, text_preview, source | P0 |
| EXT-008 | `source` field values (v10.20 provenance rule) | Any destination | A community source (`r/<subreddit>`, with score and real permalink) appears only on live-fetched Reddit tips; every LLM/template tip is `General tip` with `score == 0` and empty `post_url` | `source == "General tip"` ⟺ tip is not from live Reddit | P0 |
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


### 5I — Authentication & Session Management (`/api/auth/*`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| AUTH-001 | Email/password signup (valid payload, `consent_accepted=true`) | `POST /api/auth/signup` returns `200` + `UserResponse`; `wp_access_token` + `wp_refresh_token` cookies set | User row created with `auth_provider="password"`; cookies present; immediate `GET /api/auth/me` succeeds | P0 |
| AUTH-002 | Duplicate-email signup | Existing email re-used on `POST /api/auth/signup` | HTTP 400 with `"Unable to sign up with these details."`; no second user row created | P0 |
| AUTH-003 | Weak password on signup (`<8` chars) | Frontend blocks submit; direct API call fails validation | UI shows `"Password must be at least 8 characters."`; direct API returns 422 from `SignupRequest.password` min_length | P0 |
| AUTH-004 | Missing consent field on signup request | `consent_accepted` omitted from JSON body | FastAPI validation rejects request with HTTP 422; account not created | P1 |
| AUTH-005 | Explicit `consent_accepted=false` on signup | Request reaches router with false consent | HTTP 400 with `"You must accept the Terms of Service and Privacy Policy to sign up."` | P0 |
| AUTH-006 | Email/password login (valid credentials) | `POST /api/auth/login` with correct password | HTTP 200 + `UserResponse`; both auth cookies refreshed; `last_login_at` updated | P0 |
| AUTH-007 | Login enumeration resistance | Submit wrong password for a real account, then same request shape for a nonexistent email | Both return HTTP 401 with the exact same detail: `"Incorrect email or password."` | P0 |
| AUTH-008 | Google SSO happy path | `GET /api/auth/google/start?return_to=/admin` → complete consent/account selection → callback | User ends on `FRONTEND_BASE_URL + return_to`; new Google user gets `auth_provider="google"`; existing same-email password account links instead of duplicating | P0 |
| AUTH-009 | Google SSO failure redirect | Callback missing/invalid `code` or expired/bad `state`, or Google returns `error` | Redirect lands on `/login?error=google_sso_failed`; login page shows the Google-failure banner | P1 |
| AUTH-010 | Refresh-token rotation + reuse rejection | Call `POST /api/auth/refresh` twice with the same original refresh cookie | First refresh succeeds and sets a new cookie pair; second reuse of the revoked/old refresh token returns HTTP 401 + clears cookies | P0 |
| AUTH-011 | Logout clears session | `POST /api/auth/logout` with an active refresh cookie | Refresh row revoked (if present), both auth cookies deleted, follow-up `GET /api/auth/me` returns 401 | P0 |
| AUTH-012 | `/auth/me` unauthenticated | `GET /api/auth/me` without `wp_access_token` cookie | HTTP 401 with `"Not authenticated"` | P0 |

### 5J — Forgot / Reset Password (`/api/auth/password/*`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| PWRESET-001 | Forgot-password response is identical for existing vs nonexistent email | `POST /api/auth/password/forgot` always returns `{"status":"if_account_exists_email_sent"}` | Same HTTP 200 body for both cases; frontend always shows `"If an account exists..."` copy | P0 |
| PWRESET-002 | Reset with a valid single-use token | `POST /api/auth/password/reset` with fresh token + strong password | Password hash updates; token `used_at` set; all existing refresh tokens revoked; response is `{"status":"password_updated"}` | P0 |
| PWRESET-003 | Reused reset token rejected | Re-submit the same token after a successful reset | HTTP 400 with `"This password reset link is invalid or has expired."` | P0 |
| PWRESET-004 | Expired reset token rejected | Use a token past `password_reset_token_ttl_minutes` (30 min) | HTTP 400 with the same generic invalid/expired message; no password change | P0 |
| PWRESET-005 | Malformed or missing token rejected | Invalid token string, or `/reset-password` opened without `?token=` | UI blocks with `"This reset link is missing its token..."` when absent; API rejects malformed token with HTTP 400 invalid/expired detail | P1 |
| PWRESET-006 | Password strength enforced on reset | New password shorter than 8 chars | UI shows `"Password must be at least 8 characters."`; direct API call fails validation (HTTP 422) via `ResetPasswordRequest.new_password` | P0 |

### 5K — Consent Capture & Legal Disclosure (Signup, `/terms`, `/privacy`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| CONSENT-001 | Signup requires the consent checkbox | Email/password signup cannot complete unless checkbox is ticked | Button submit path shows `"Please accept the Terms of Service and Privacy Policy to continue."`; backend also rejects `consent_accepted=false` | P0 |
| CONSENT-002 | Terms + Privacy links are present and open the correct pages | Signup form shows linked legal text | `/terms` and `/privacy` both open successfully (new tab target on signup form); terms mention account-required itinerary generation; privacy page explains account/trip/usage data collection | P0 |
| CONSENT-003 | Consent timestamp recorded | Successful signup creates/updates `users.consent_accepted_at` | Non-null timestamp stored for password signup; first-time Google-account creation also stamps `consent_accepted_at` in callback flow | P0 |
| CONSENT-004 | Consent copy is DPDP-aligned and consistent with legal pages | Checkbox text + `/terms` + `/privacy` are spot-checked together | Signup copy explicitly references Terms of Service and Privacy Policy; linked pages explain purpose limitation, processors (Gemini/Google OAuth/Pexels/Resend), deletion rights, and grievance/contact path | P1 |

### 5L — Account Deletion & Admin Purge (`DELETE /api/auth/me`, `/api/admin/users/*`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| PURGE-001 | Self-service delete confirmation UX | `/account` requires typing `DELETE` before the destructive button enables | Button stays disabled until exact uppercase `DELETE`; cancel clears the staged confirmation state | P0 |
| PURGE-002 | Self-service delete cascades to sessions | `DELETE /api/auth/me` on an authenticated account | User row deleted; `refresh_tokens` cascade-delete; analytics `events.user_id` becomes `NULL`; response clears cookies and returns `{"status":"account_deleted"}` | P0 |
| PURGE-003 | Admin single-user delete (non-admin target) | `DELETE /api/admin/users/{user_id}` as admin | HTTP 200 with `{"status":"deleted","user_id":"..."}`; target account gone; `admin_user_deleted` event logged | P0 |
| PURGE-004 | Admin route cannot delete the acting admin's own account | Admin calls `DELETE /api/admin/users/{their_own_id}` | HTTP 400 with `"Use your own account settings to delete your own account, not this endpoint."` | P0 |
| PURGE-005 | Bulk purge rejects the wrong confirmation phrase | `POST /api/admin/users/purge-all` with anything except `DELETE ALL USERS` | HTTP 400 with exact typed-phrase guidance; no accounts deleted | P0 |
| PURGE-006 | Bulk purge deletes only non-admins and returns count | `POST /api/admin/users/purge-all` with `{"confirm":"DELETE ALL USERS"}` | Single bulk delete removes every `is_admin=false` user, preserves admins, and returns `{"status":"purged","deleted_count":N}` | P0 |

### 5M — Admin Dashboard & Metrics (`/admin`, `/api/admin/metrics/*`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| ADMIN-001 | Logged-out access to `/admin` | Page shows sign-in CTA; API summary endpoint denies anonymous access | `/admin` renders the login prompt with `returnTo=/admin`; direct `GET /api/admin/metrics/summary` without cookies returns 401 | P0 |
| ADMIN-002 | Authenticated non-admin access to `/admin` | UI explains lack of admin access; backend returns 403 | `/admin` shows the shield warning; `GET /api/admin/metrics/summary` / `timeseries` return HTTP 403 with `"Admin access required"` | P0 |
| ADMIN-003 | Summary stat cards populate correctly | Admin dashboard loads `total_users`, `signups`, `logins`, `itineraries` | Four top stat cards render non-stale values from `/api/admin/metrics/summary`; login success rate uses `success_30d / (success_30d + failed_30d)` | P0 |
| ADMIN-004 | Activity chart supports 7d + 30d ranges | Toggle `/admin` range buttons | `GET /api/admin/metrics/timeseries?range=7d|30d` returns matching `range`; chart rows plot `session_start`, `signup`, `login_success`, `itinerary_generated` by day | P1 |
| ADMIN-005 | Cost cards show Gemini + Pexels usage | Admin cost section renders request/token/cost counters | UI shows Gemini requests, Gemini tokens, estimated Gemini cost, and Pexels call count sourced from `cost_usage` in `/api/admin/metrics/summary` | P0 |
| ADMIN-006 | YouTube thumbnail analytics remain queryable in admin metrics data | Generate thumbnail events, then inspect admin metrics data source | `youtube_thumbnail_call` / `youtube_thumbnail_failed` appear in `/api/admin/metrics/timeseries` on the correct day even though `/admin` currently has no dedicated YouTube stat card yet | P1 |

### 5N — Auth-Gated Itinerary Generation (`/signup`, `/api/generate-itinerary`, `LLMWizard.tsx`)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| GATE-001 | Logged-out generate action redirects to signup with `returnTo` | Clicking Generate while unauthenticated pushes `/signup?returnTo=/` | Wizard saves the assembled `TripConfig` first, then redirects to signup instead of silently failing | P0 |
| GATE-002 | Trip config survives the Google OAuth full-page redirect | Start unauthenticated → click Generate → choose Google Sign-In → return | `wp_pending_trip_config` in `sessionStorage` survives the round-trip and deserializes back into the wizard/app stores | P0 |
| GATE-003 | Generation auto-resumes immediately after auth | After successful email/password signup/login or Google SSO, `authStatus` flips to `authenticated` | `LLMWizard` detects pending config, clears it, calls `startGeneration(...)`, and user does not need to re-enter trip details | P0 |
| GATE-004 | Direct API call without a session cookie is blocked | `POST /api/generate-itinerary` without `wp_access_token` | HTTP 401 from `get_current_user`; frontend `streamItinerary()` maps this to `AUTH_REQUIRED` | P0 |

## Section 6 — Price Metering for Paid APIs

### 6A — Gemini API Cost Tracking

WanderPlanner uses **Gemini 2.0 Flash** (default) or **Gemini 2.5 Flash** (configurable via `gemini_model` env var). Pricing as of June 2026 (verify at [ai.google.dev/pricing](https://ai.google.dev/pricing)):

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
| COST-016 | User-Agent set | Inspect outgoing Nominatim request headers | `User-Agent: wanderplanner/1.0` | `user_agent == "wanderplanner/1.0"` | P0 |
| COST-017 | Rate limiter active | 3 rapid geocode calls | Min 1s between each outgoing HTTP call | No 403/429 from Nominatim | P0 |
| COST-018 | No excessive calls | User types in wizard destination input | Geocode only on submit/confirm, NOT on every keystroke | ≤ 1 geocode call per user action | P1 |

### 6D — OpenStreetMap / Wikivoyage (Free, Attribution Required)

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| COST-019 | Attribution shown on map | Open full-screen map in itinerary | "© OpenStreetMap contributors" visible | Attribution text visible in map UI | P0 |
| COST-020 | Wikivoyage attribution | Travel tips sourced from Wikivoyage | Source credited in tip UI | Source label shown | P1 |


### 6E — Auth-Era Usage Analytics & Admin Cost Signals

| ID | Test | Expected | Pass criteria | Priority |
|---|---|---|---|---|
| COST-021 | One itinerary-generation request flushes exactly one aggregated `gemini_usage` event | All Gemini calls made during a single request are persisted together after generation | Exactly one `events` row of type `gemini_usage` per request; `event_metadata.total_tokens == sum(call.total_tokens)` and `total_cost_usd == sum(call.cost_usd)` across the embedded `calls` array | P0 |
| COST-022 | Pexels cache hits do **not** increment call count | Repeat the same day-photo query within one process after the first successful fetch | Second call returns from `_cache` and records no additional `pexels_usage` event/call-count increment | P0 |
| COST-023 | Real Pexels network calls increment usage exactly once per uncached query | Call `get_day_photo()` with a fresh query and valid API key | One provider call records one `pexels` usage item; after `flush_llm_usage()` the resulting `pexels_usage.event_metadata.call_count` reflects only uncached network attempts | P0 |
| COST-024 | YouTube thumbnail lookup beacon fires on real frontend fetches | Load itinerary cards/tips that require `/api/youtube-thumbnail` lookups | Real fetch path logs `youtube_thumbnail_call`; retry failures log `youtube_thumbnail_failed`; cached hits in `ItineraryTimeline` short-circuit without emitting duplicate beacons | P1 |

---

## Section 7 — Frontend Features (Manual / Browser Tests)

### 7A — BookingHub (`BookingHub.tsx` + `bookingStore.ts`)

| ID | Test | Steps | Expected | Pass criteria | Priority |
|---|---|---|---|---|---|
| BOOKING-001 | Add a flight booking | Open BookingHub; select "Flight"; fill in name, confirmation, date, amount; save | Booking appears in list immediately | Row visible with correct type icon and data | P0 |
| BOOKING-002 | Remove a booking | Hover over booking row; click delete | Row disappears from list | Booking no longer visible | P0 |
| BOOKING-003 | BookingHub survives page refresh | Add booking; refresh page | Booking still visible after reload | `localStorage["wanderplanner-bookings"]` persists entry | P0 |
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
# Unit + integration tests (existing, includes all RAG test classes:
# TestHybridBM25Search, TestHyDEPassageGeneration, TestCrossEncoderReranking,
# TestOSMPoiParsing, TestItineraryCacheKey, + 3-tier fallback tests)
cd apps/api && .venv/bin/pytest tests/ -v

# RAG golden-dataset retrieval evaluation (Precision@k/Recall@k/MRR/nDCG@k) — see §4U
cd apps/api && python -m eval.run_rag_eval

# RAG retrieval load test (throughput/latency under concurrency)
cd apps/api && python load_test_rag.py

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
