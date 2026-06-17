# WanderPlan — System Design Document
**Version:** 2.0 (Conversational Interface)  
**Last Updated:** June 17, 2026  
**Audience:** Engineering team and technical stakeholders

---

## Table of Contents
1. [High-Level Architecture](#1-high-level-architecture)
2. [Data Flow: Conversational Wizard](#2-data-flow-conversational-wizard)
3. [Data Flow: Itinerary Generation](#3-data-flow-itinerary-generation)
4. [Data Flow: Voice Interaction](#4-data-flow-voice-interaction)
5. [API Contract](#5-api-contract)
6. [Qdrant Collection Schema](#6-qdrant-collection-schema)
7. [Gemini Prompt Design](#7-gemini-prompt-design)
8. [Frontend State Architecture](#8-frontend-state-architecture)
9. [Environment Variables Reference](#9-environment-variables-reference)
10. [Performance & Cost Analysis](#10-performance--cost-analysis)

---

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         BROWSER (Desktop)                             │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Next.js 16 (Turbopack) + TypeScript                          │  │
│  │                                                                 │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │  Anya - Conversational Wizard (Full-Screen Overlay)     │ │  │
│  │  │  🎙️ Voice Mode: Speech Recognition + Synthesis         │ │  │
│  │  │  💬 Chat Interface with Quick-Reply Chips               │ │  │
│  │  │  📊 Progress Tracking (9 wizard fields)                 │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  │                                                                 │  │
│  │  ┌──────────┐  ┌──────────────────┐  ┌────────────────────┐  │  │
│  │  │ Column 1 │  │    Column 2       │  │    Column 3        │  │  │
│  │  │ (20%)    │  │    (55%)          │  │    (25%)           │  │  │
│  │  │          │  │                   │  │                    │  │  │
│  │  │ Metrics  │  │ Itinerary         │  │ Map (Leaflet)      │  │  │
│  │  │ Booking  │  │ Timeline          │  │ Best Time Widget   │  │  │
│  │  │ Expenses │  │ Comparison        │  │ Travel Tips        │  │  │
│  │  └──────────┘  └──────────────────┘  └────────────────────┘  │  │
│  │                                                                 │  │
│  │  State Management: Zustand (4 stores)                          │  │
│  │  - tripConfigStore  - wizardChatStore                          │  │
│  │  - itineraryStore   - appStore                                 │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ HTTPS / JSON / SSE
┌─────────────────────────────▼────────────────────────────────────────┐
│              FastAPI (Python 3.9+) on Port 8000                       │
│                                                                        │
│  Routers:                                                              │
│  POST /api/generate-itinerary   → Gemini 2.0 Flash (streaming)       │
│  POST /api/chat-refine          → Anya conversation handler          │
│  POST /api/recommend-cities     → City suggestions (Gemini)          │
│  GET  /api/travel-tips          → Gemini-generated tips (cached)     │
│  GET  /api/best-time/{city}     → Weather data (Open-Meteo)          │
│  GET  /api/geocode              → Nominatim wrapper                   │
│  GET  /api/youtube-thumbnail    → YouTube scraper                     │
│  GET  /health                   → Readiness check                     │
│                                                                        │
│  Background Jobs (APScheduler):                                       │
│  - Reddit content refresh (every 6 hours)                            │
│  - Qdrant vector ingestion                                            │
└──────┬──────────────┬─────────────────┬──────────────────┬────────────┘
       │              │                 │                  │
┌──────▼──────┐ ┌─────▼──────┐  ┌──────▼────────┐  ┌─────▼──────────┐
│   Qdrant    │ │   Gemini   │  │  Open-Meteo   │  │ External APIs  │
│ (in-memory) │ │  2.0 Flash │  │  Weather API  │  │                │
│             │ │            │  │               │  │ • Nominatim    │
│ Collections:│ │ Model:     │  │ Historical +  │  │ • Reddit JSON  │
│ - reddit    │ │ gemini-2.0 │  │ Forecast data │  │ • YouTube      │
│ - wiki      │ │ -flash-exp │  │               │  │ • OSM Tiles    │
└─────────────┘ └────────────┘  └───────────────┘  └────────────────┘

Embedding Model: sentence-transformers/all-MiniLM-L6-v2 (local, 384 dims)
```

---

## 2. Data Flow: Conversational Wizard

### 2.1 Wizard Field Flow

```
User opens wizard → Anya greets: "Hi! I'm Anya from WanderPlan..."
         │
         ▼
Field Sequence (in wizardChatStore):
1. purpose       → "What's the main purpose of your trip?"
                   Chips: Leisure, Adventure, Honeymoon, Family, Business, Solo, Group
         │
         ▼
2. origin        → "Where are you starting from?"
                   Input: City name → POST /api/geocode → {city, lat, lon}
         │
         ▼
3. destination_mode → "Do you have a specific destination in mind?"
                      Chips: "Yes, I have one", "Suggest me!", "Exploring a country"
         │
         ├─→ [Fixed] → 4a. destination (city input)
         ├─→ [Exploring] → POST /api/recommend-cities (vibe → cities) → 4b. city_selection
         └─→ [Country] → 4c. country input → recommend-cities → city_selection
         │
         ▼
5. dates         → "When are you planning to travel?"
                   Chips: This month, Next month, In 3 months, Custom, Flexible
         │
         ▼
6. group         → "Who's coming with you?"
                   Sub-flow: adults → kids count → kid ages
         │
         ▼
7. budget        → "What's your total budget?"
                   Chips: ₹50K, ₹1L, ₹2.5L, ₹5L, ₹10L+
                   Currency: INR (default)
         │
         ▼
8. accommodation → "What type of accommodation do you prefer?"
                   Chips: Hotel, Airbnb/Villa, Hostel, Resort, Service Apartment, No preference
         │
         ▼
9. pace          → "What's your preferred travel pace?"
                   Chips: Relaxed, Moderate, Packed
         │
         ▼
10. themes       → "Select themes (tap multiple)"
                   Multi-select chips: Culture, Food, Adventure, Nature, Shopping, etc.
                   Button: "Done ✓ (N selected)"
         │
         ▼
11. refinement   → "Anything else before I generate?"
                   User input → POST /api/chat-refine → apply config_patch
                   Chip: "Looks good, proceed ✓"
         │
         ▼
12. summary      → Display all collected inputs in TripSummaryCard
                   Buttons:
                   - "Edit [field]" → jump back to that field
                   - "Generate Itinerary 🚀" → POST /api/generate-itinerary
                   - "View Current Itinerary →" (if exists)
```

### 2.2 State Management

**wizardChatStore.ts**:
```typescript
{
  messages: WizardMessage[]  // {role: 'user'|'bot', content, chips?, inputType?}
  currentField: WizardField | null
  phase: 'chatting' | 'summary' | 'generating' | 'done'
  collectedLabels: Record<string, string>  // User-friendly display values
}
```

**tripConfigStore.ts**:
```typescript
{
  purpose: string
  dates: {start: string|null, end: string|null, flexible: boolean}
  origin: {city, lat, lon}
  destination: {city, country, lat, lon} | null
  destination_mode: 'fixed' | 'exploring' | 'country'
  group: {infants, kids: [{age}], adults, seniors, pets}
  accommodation: {style[], min_bedrooms, bathrooms, ...}
  pace: 'relaxed' | 'moderate' | 'packed'
  budget: {amount, currency}
  themes: string[]
  personas: string[]
}
```

---

## 3. Data Flow: Itinerary Generation

```
User clicks "Generate Itinerary 🚀"
         │
         ▼
Frontend: POST /api/generate-itinerary
Body: TripConfig (full configuration)
         │
         ▼
Backend: chains/generate_itinerary.py
         │
         ├─→ [1] Context Retrieval
         │      Query Qdrant:
         │      - destination + themes
         │      - Returns top 10 Reddit/Wikivoyage chunks
         │      - Score threshold: 0.1
         │
         ├─→ [2] Prompt Construction
         │      System prompt template:
         │      "You are an expert travel planner. Generate a {duration}-day
         │       itinerary for {destination}.
         │       
         │       User Profile:
         │       - Purpose: {purpose}
         │       - Group: {group_composition}
         │       - Pace: {pace}
         │       - Budget: {currency} {amount}
         │       - Themes: {themes}
         │       
         │       Context from travelers:
         │       {qdrant_results}
         │       
         │       Output JSON format:
         │       {
         │         'days': [
         │           {
         │             'date': 'YYYY-MM-DD',
         │             'items': [
         │               {
         │                 'time': 'HH:MM',
         │                 'title': '...',
         │                 'description': '...',
         │                 'cost_estimate': number,
         │                 'duration_minutes': number,
         │                 'location': {lat, lon, address},
         │                 'youtube_search_query': '...',
         │                 'tags': ['...']
         │               }
         │             ]
         │           }
         │         ]
         │       }"
         │
         ├─→ [3] Gemini API Call
         │      Model: gemini-2.0-flash-exp
         │      Temperature: 0.7
         │      Max tokens: 4096
         │      Streaming: True (SSE chunks)
         │
         └─→ [4] Post-Processing
                - Parse JSON response
                - Validate Pydantic schema
                - Add YouTube video IDs (if available)
                - Calculate total cost
                - Return streaming chunks to frontend
         │
         ▼
Frontend: Receives SSE stream
         │
         ├─→ Parse JSON chunks
         ├─→ Update itineraryStore incrementally
         ├─→ Render timeline as data arrives
         ├─→ Geocode locations → add map pins
         └─→ Close wizard, show itinerary
```

---

## 4. Data Flow: Voice Interaction

### 4.1 Voice Mode Activation

```
User clicks 🎙️ voice button
         │
         ▼
toggleVoiceMode() triggered
         │
         ├─→ Set voiceModeActive = true
         ├─→ Initialize SpeechRecognition (en-IN)
         ├─→ Speak last bot message (TTS)
         └─→ Start listening
         │
         ▼
Auto-loop: onend → restart recognition
         │
         ▼
User speaks → transcript captured
         │
         ▼
handleAnswer(transcript)
         │
         ├─→ If in summary phase: POST /api/chat-refine
         └─→ Else: Process field input
         │
         ▼
Bot responds (text) → speakMessage(reply)
         │
         ├─→ Strip markdown/emojis
         ├─→ Select Indian female voice
         │   Priority:
         │   1. en-IN female voices
         │   2. Any English female voice
         │   3. Google/MS Indian voices
         │
         ├─→ Set voice params:
         │   - pitch: 1.15 (young female)
         │   - rate: 1.05 (energetic)
         │   - volume: 1.0
         │
         └─→ Speak via SpeechSynthesis API
         │
         ▼
Auto-restart listening (if voiceModeActive)
```

### 4.2 Voice Button States

- **Inactive**: Gray background, 🎙️ icon, static
- **Active**: Purple/blue gradient, 🎙️ icon, pulsating animation, ping rings
- **Click**: Toggle voice mode on/off

---

## 5. API Contract

### 5.1 Itinerary Generation

**Endpoint**: `POST /api/generate-itinerary`

**Request**:
```json
{
  "purpose": "Leisure",
  "dates": {"start": "2026-07-01", "end": "2026-07-05", "flexible": false},
  "origin": {"city": "Delhi", "lat": 28.6139, "lon": 77.2090},
  "destination": {"city": "Paris", "country": "France", "lat": 48.8566, "lon": 2.3522},
  "group": {"infants": 0, "kids": [], "adults": 2, "seniors": 0, "pets": 0},
  "budget": {"amount": 250000, "currency": "INR"},
  "pace": "moderate",
  "themes": ["Culture", "Food", "Photography"],
  "accommodation": {"style": ["Hotel"], "min_bedrooms": 1, "bathrooms": 1}
}
```

**Response**: Server-Sent Events (SSE)
```
data: {"status": "Retrieving context from travelers..."}

data: {"status": "Generating day-by-day itinerary..."}

data: {"day": 1, "date": "2026-07-01", "items": [...]}

data: {"day": 2, "date": "2026-07-02", "items": [...]}

data: {"status": "complete"}
```

**Error**:
```json
{
  "error": "Failed to generate itinerary",
  "detail": "Gemini API rate limit exceeded",
  "retry_after": 60
}
```

### 5.2 Chat Refinement

**Endpoint**: `POST /api/chat-refine`

**Request**:
```json
{
  "messages": [
    {"role": "user", "content": "I want a more relaxed pace"},
    {"role": "assistant", "content": "Got it! I've updated..."}
  ],
  "trip_config": {...}  // Current TripConfig
}
```

**Response**:
```json
{
  "reply": "Sure! I've updated your trip pace to Relaxed — more downtime and fewer rushed activities. ✅",
  "action_type": "patch_config",
  "config_patch": {"pace": "relaxed"},
  "major_change": false
}
```

**Action Types**:
- `none`: No config change (general question)
- `patch_config`: Minor change (pace, themes, accommodation)
- `regenerate`: Major change requiring regeneration (destination, dates, budget >20%)

### 5.3 City Recommendations

**Endpoint**: `POST /api/recommend-cities`

**Request**:
```json
{
  "country": "Thailand",
  "trip_config": {...},
  "count": 5
}
```

**Response**:
```json
{
  "cities": [
    {"name": "Bangkok", "description": "Vibrant capital with temples, street food, and nightlife"},
    {"name": "Chiang Mai", "description": "Cultural hub in the mountains, known for temples and night markets"},
    {"name": "Phuket", "description": "Beach paradise with water sports and island-hopping"},
    {"name": "Krabi", "description": "Stunning limestone cliffs and pristine beaches"},
    {"name": "Ayutthaya", "description": "Ancient capital with UNESCO heritage temples"}
  ]
}
```

### 5.4 Travel Tips

**Endpoint**: `GET /api/travel-tips?destination=Tokyo&limit=6`

**Response**:
```json
[
  {
    "title": "Get a JR Pass before you arrive",
    "text_preview": "Save hundreds on train travel. Buy online before departure...",
    "source": "Reddit r/travel",
    "post_url": "https://www.reddit.com/r/travel/search/?q=tokyo+jr+pass",
    "score": 342
  },
  ...
]
```

**Cache**: In-memory per destination, persists until API restart

---

## 6. Qdrant Collection Schema

### 6.1 reddit_highlights Collection

```python
{
  "id": "reddit_{post_id}",
  "vector": [0.123, ...],  # 384 dimensions (all-MiniLM-L6-v2)
  "payload": {
    "text": "Full post text...",
    "destination": "Tokyo",
    "source": "reddit",
    "post_url": "https://reddit.com/r/travel/comments/...",
    "score": 450,
    "author": "username",
    "created_at": "2026-05-15T10:30:00Z"
  }
}
```

**Ingestion**: APScheduler job every 6 hours  
**Query**: `destination + themes` → cosine similarity > 0.1  
**Limit**: Top 10 results per query

### 6.2 wikivoyage_content Collection

```python
{
  "id": "wiki_{destination}_{section_hash}",
  "vector": [0.456, ...],
  "payload": {
    "text": "Section content...",
    "destination": "Paris",
    "source": "wikivoyage",
    "section": "See",  # See, Do, Eat, Sleep, Stay safe
    "url": "https://en.wikivoyage.org/wiki/Paris"
  }
}
```

**Ingestion**: On startup + manual refresh  
**Scraping**: BeautifulSoup4 + httpx

---

## 7. Gemini Prompt Design

### 7.1 Itinerary Generation Prompt

**System Role**: Expert travel planner  
**Temperature**: 0.7 (creative but grounded)  
**Max Tokens**: 4096

**Template**:
```
You are an expert travel planner. Generate a {duration}-day itinerary for {destination}.

User Profile:
- Purpose: {purpose}
- Group: {group_composition}
- Pace: {pace}
- Budget: {currency} {amount}
- Themes: {themes}

Context from travelers:
{qdrant_results}

Requirements:
- Day-by-day schedule with timestamps
- Activity duration: 30-180 minutes
- Include transit time between activities
- Cost estimates in {currency}
- Location coordinates for map pins
- YouTube search queries for activities
- Mix of must-see landmarks and local experiences
- Consider group composition (kids, seniors, pets)

Output JSON format:
{
  "days": [
    {
      "date": "YYYY-MM-DD",
      "items": [
        {
          "time": "HH:MM",
          "title": "Activity name",
          "description": "Brief description",
          "cost_estimate": number,
          "duration_minutes": number,
          "location": {"lat": X, "lon": Y, "address": "..."},
          "youtube_search_query": "destination activity name",
          "tags": ["theme1", "theme2"]
        }
      ]
    }
  ]
}
```

### 7.2 Chat Refinement Prompt (Anya)

**Persona**: Anya — friendly, helpful AI travel assistant  
**Temperature**: 0.5 (balanced)  
**Max Tokens**: 1024

**System Prompt**:
```
You are Anya, WanderPlan's friendly AI travel assistant.

Current Trip Config:
{trip_config_json}

Your role:
1. Answer travel questions factually
2. Detect when user wants to change trip parameters
3. Suggest improvements to their itinerary

Response format (JSON only):
{
  "reply": "Your friendly conversational reply",
  "action_type": "none" | "patch_config" | "regenerate",
  "config_patch": null or {...fields to change...},
  "major_change": false
}

Action rules:
- "none": General questions, no config change
- "patch_config": Small changes (pace, themes, accommodation) → major_change: false
- "regenerate": Big changes (destination, dates, budget >20%, group size) → major_change: true, ask for confirmation

Guardrails:
- Only answer travel-related questions
- Never make bookings or collect payment info
- Budget always in INR
- Keep replies concise and friendly
- If non-travel question: "I'm Anya, WanderPlan's travel assistant — I can only help with travel questions! 🌍"
```

### 7.3 City Recommendations Prompt

**Temperature**: 0.7  
**Max Tokens**: 512

**Template**:
```
Recommend 5 cities in {country} for a traveler interested in: {themes}.

Consider:
- Trip purpose: {purpose}
- Group: {group_composition}
- Pace: {pace}

For each city, provide:
1. City name
2. One-sentence description highlighting why it's a good fit

Output JSON:
{
  "cities": [
    {"name": "...", "description": "..."}
  ]
}
```

---

## 8. Frontend State Architecture

### 8.1 Zustand Store Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                      appStore                                │
│  - wizardOpen: boolean                                       │
│  - step3View: 'itinerary' | 'comparison'                    │
│  - openWizard() / closeWizard()                             │
└──────────────────┬──────────────────────────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
┌────────▼──────────┐  ┌─────▼────────────────────────────────┐
│ wizardChatStore   │  │     tripConfigStore                  │
│                   │  │                                       │
│ - messages: []    │  │ - config: TripConfig                 │
│ - currentField    │  │ - updateConfig()                     │
│ - phase           │  │ - setDestination()                   │
│ - collectedLabels │  │ - updateGroup()                      │
│                   │  │ - effectivePace()                    │
│ - addMessage()    │  │                                       │
│ - pushNextField() │  │                                       │
│ - setPhase()      │  │                                       │
└───────────────────┘  └──────────────────────────────────────┘
                                     │
                                     │ Used by
                                     │
                          ┌──────────▼──────────────────────────┐
                          │     itineraryStore                  │
                          │                                     │
                          │ - days: ItineraryDay[]              │
                          │ - activeDay: number                 │
                          │ - isLoading: boolean                │
                          │ - error: string | null              │
                          │                                     │
                          │ - setDays()                         │
                          │ - setActiveDay()                    │
                          │ - clearItinerary()                  │
                          └─────────────────────────────────────┘
```

### 8.2 Component Hierarchy

```
RootLayout
  ├─ MobileWarningBanner
  └─ HomePage
       ├─ ThreeColumnLayout
       │    ├─ Column1Metrics (left 20%)
       │    │    ├─ Trip metrics
       │    │    ├─ BookingLinksSection
       │    │    ├─ ExpenseBreakupCard
       │    │    └─ CurrencyWidget
       │    │
       │    ├─ ItineraryTimeline | ComparisonPanel (center 55%)
       │    │    ├─ Day tabs
       │    │    ├─ Activity cards
       │    │    └─ Transit warnings
       │    │
       │    └─ Column3Sidebar (right 25%)
       │         ├─ MapWrapper (Leaflet)
       │         ├─ BestTimeWidget
       │         └─ TravelTips
       │
       └─ ConversationalWizard (overlay, conditional)
            ├─ Header: "Anya - Your AI Travel Assistant"
            ├─ Progress bar
            ├─ Message history
            ├─ Quick-reply chips
            ├─ Input field + voice button
            └─ TripSummaryCard (when phase='summary')
```

---

## 9. Environment Variables Reference

### 9.1 Backend (.env)

```bash
# LLM Provider
LLM_PROVIDER=gemini          # or 'mock' for testing
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash-exp

# Vector Database
QDRANT_URL=:memory:          # or http://localhost:6333 for persistent

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://wanderplan.vercel.app

# Optional
INGESTION_REFRESH_HOURS=6    # Reddit refresh interval
CONTENT_FILTER_LEVEL=strict  # or 'moderate'
```

### 9.2 Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 10. Performance & Cost Analysis

### 10.1 Response Times (P95)

| Endpoint | Time | Notes |
|----------|------|-------|
| `/api/generate-itinerary` | 30-60s | Streaming, 5-7 day trip |
| `/api/chat-refine` | 2-5s | Gemini 2.0 Flash |
| `/api/recommend-cities` | 3-6s | Gemini 2.0 Flash |
| `/api/travel-tips` (cached) | <200ms | In-memory cache |
| `/api/travel-tips` (uncached) | 2-4s | Gemini + cache write |
| `/api/geocode` | 500-1000ms | Nominatim rate-limited |
| `/api/best-time` | 1-2s | Open-Meteo |

### 10.2 Cost Analysis (100 Users/Month)

**Gemini API Costs** (free tier during preview):
- Itinerary generation: 1-2 calls/user × ₹0.01 = ₹0.01-0.02
- Chat refinements: 3-5 calls/user × ₹0.01 = ₹0.03-0.05
- City recommendations: 1 call/user × ₹0.01 = ₹0.01
- Travel tips: 1 call cached/destination × ₹0.01 = ₹0.01

**Total per user**: ₹0.10-0.15  
**100 users**: ₹10-15/month

**Other services**: Free (Nominatim, Open-Meteo, Reddit, OSM)

### 10.3 Scalability Considerations

**Bottlenecks**:
1. Gemini API rate limits (free tier)
2. Qdrant in-memory → data loss on restart
3. Reddit JSON API → 403 blocking (Gemini fallback active)

**Optimizations**:
- Travel tips caching (~98% hit rate after warmup)
- Qdrant semantic search with threshold filtering
- SSE streaming for itinerary generation (perceived performance)

**Scale to 1000 users**:
- Migrate Qdrant to persistent storage (Railway volume)
- Implement Redis caching for geocode results
- Add CDN for static assets
- Consider Gemini paid tier for higher rate limits

---

**End of System Design Document**
