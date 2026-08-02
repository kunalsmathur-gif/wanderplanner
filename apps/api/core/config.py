import os

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Env vars that can identify the deployment as production, in priority order.
# `ENVIRONMENT` is ours; the `RAILWAY_*` pair is injected by Railway itself.
_PRODUCTION_ENV_VARS = ("ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT")


def is_production() -> bool:
    """True when this process is the production deployment.

    Checking only `ENVIRONMENT` is not enough: Railway never sets a bare
    `ENVIRONMENT` var, it injects `RAILWAY_ENVIRONMENT_NAME=production` (and
    `RAILWAY_ENVIRONMENT`). Because nothing set `ENVIRONMENT` on the Railway
    service, both prod guards below were dead code *in the only deployment
    they were written to protect* — the cookie validator in particular would
    not have fired even with `COOKIE_SAMESITE` unset, silently reinstating
    the cross-site session-drop bug it exists to prevent. Read live from the
    environment (not cached) so tests can monkeypatch it.
    """
    return any((os.getenv(var) or "").lower() == "production" for var in _PRODUCTION_ENV_VARS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_provider: str = "groq"  # "groq" | "gemini" | "ollama" | "mock"
    # Only used by eval/run_model_comparison.py (docs/eval-set.md §8) to call
    # OpenAI/Anthropic directly for model-selection comparison — not wired
    # into the production generate_itinerary() provider switch above.
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    # Only used by eval/run_budget_comparison.py (docs/eval-set.md §14) to
    # call Moonshot's Kimi models directly, alongside OpenAI/Anthropic/Gemini,
    # for the "our estimator vs asking an LLM directly" budget comparison —
    # same "not wired into production" scope as the two keys above. Moonshot's
    # API is OpenAI-SDK-compatible (different base_url only).
    moonshot_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    # ⚠️ This bounds the WHOLE of generate_itinerary() — routers/itinerary.py
    # wraps the call in asyncio.wait_for(). Both local .env and Railway set 120;
    # this 30 is the never-used code default, so read the env before reasoning
    # about worst-case latency. Note the Gemini retry cascade's own backoff
    # (5+10+20+40 = 75s per model) does not fit inside either value — see the
    # comment above `max_attempts` in chains/itinerary_chain.py.
    llm_timeout_seconds: int = 30
    # A generation slower than this logs its per-stage timing breakdown at
    # WARNING instead of INFO (core/timing.py). Cheapest useful alerting
    # available without an APM: grep the level, get the breakdown attached.
    # Set against the PRD's stated budget rather than measured p95 — revisit
    # once there is real traffic data to set it from.
    slow_itinerary_threshold_seconds: float = 20.0

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_wiki: str = "wiki"
    qdrant_collection_reddit: str = "reddit"
    qdrant_collection_osm: str = "osm_pois"
    qdrant_collection_itinerary_cache: str = "itinerary_cache"
    qdrant_collection_itinerary_corpus: str = "itinerary_corpus"
    qdrant_collection_youtube_comments: str = "youtube_comments"
    # Creator narration (transcripts + video descriptions), kept separate from
    # youtube_comments because services/gems.py counts mentions as independent
    # community signal and one vlogger repeating a name is not that. See
    # scrapers/youtube_narration.py.
    qdrant_collection_youtube_narration: str = "youtube_narration"
    # Entry/visa rules (scrapers/visa_info.py, issue #37). Keyed by COUNTRY,
    # not city — measured 2026-07-29, visa content is a country-level fact on
    # Wikivoyage: the "Get in" section of India/Thailand/UAE/France carries
    # 76/30/31/28 visa-word mentions while Jaipur's carries 0 and Bangkok's 0.
    # Storing it per-city would mean 170 near-duplicate copies of one country's
    # rules, all drifting apart as they refresh at different times.
    qdrant_collection_visa_info: str = "visa_info"
    # Visa rules are low-churn, so a monthly refresh is plenty; and unlike the
    # metered YouTube sources this is a free Wikimedia API, so the cadence is
    # about staleness, not quota.
    visa_info_refresh_days: int = 30
    agent_lead_sla_check_hours: int = 1
    # Retrieval side: off switch for the wizard's visa note, matching the
    # pattern of itinerary_corpus_retrieval_enabled.
    visa_info_retrieval_enabled: bool = True

    # Qdrant Cloud free tier is capped at 1GiB shared across every collection
    # above, with no built-in usage monitoring — the first symptom of hitting
    # it would otherwise be write failures mid-ingestion (docs/
    # scaling-tech-challenges.md §"No corpus size ceiling planning"). These
    # drive the periodic headroom check in core/scheduler.py and the
    # `/admin/metrics/summary` estimate — both use an estimate (points_count ×
    # vector bytes + a per-point payload overhead), not a real disk-usage API,
    # since qdrant-client 1.9's `get_collection()` doesn't expose disk bytes.
    qdrant_storage_limit_bytes: int = 1_073_741_824  # 1 GiB, the Cloud free-tier cap
    qdrant_storage_warn_threshold: float = 0.7  # log WARNING past 70% used
    qdrant_storage_critical_threshold: float = 0.9  # log ERROR past 90% used
    qdrant_storage_check_hours: int = 24

    # Redis (deployed on Railway 2026-07-29, replacing the previous in-process
    # dict caches for share links + travel tips — see core/redis_client.py for
    # the local-dev fallback rationale). Empty string = not configured, which
    # falls back to the old in-process dict behavior (local dev only).
    redis_url: str = ""
    share_link_ttl_seconds: int = 90 * 24 * 60 * 60  # 90 days
    travel_tips_ttl_seconds: int = 60 * 60  # 1 hour
    # Railway's free/Hobby Redis has no hard memory cap of its own to alert
    # on, so this is an app-level guardrail: a conservative ceiling for what
    # these small, short-TTL caches should ever legitimately need. Past it,
    # something is wrong (e.g. a key-explosion bug) rather than "healthy
    # growth", so the periodic check clears the cache outright rather than
    # trying to selectively evict — see core/scheduler.py.
    redis_memory_limit_bytes: int = 256 * 1024 * 1024  # 256 MiB
    redis_memory_warn_threshold: float = 0.7
    redis_memory_check_hours: int = 6

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Retrieval feature flags
    hybrid_search_enabled: bool = True   # BM25 + semantic RRF fusion (docs §3D)
    hyde_enabled: bool = True            # hypothetical-document query augmentation (docs §3G)
    reranking_enabled: bool = False      # cross-encoder rerank of merged candidates (docs P3)
                                          # off by default (adds a 2nd model + latency);
                                          # explicitly enabled only for final itinerary
                                          # generation via retrieve_context(enable_reranking=True)
    itinerary_corpus_retrieval_enabled: bool = True  # few-shot grounding from real
                                          # traveller itineraries (docs §9 retrieval)
    itinerary_cache_score_threshold: float = 0.88

    # OSM POI ingestion (docs §3I)
    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    # Additional public Overpass mirrors, tried in round-robin alongside
    # osm_overpass_url when a request fails — spreads load across
    # independently rate-limited instances instead of hammering a single one
    # ~100 times in a row during a large re-ingestion batch. Added 2026-07-23
    # after live batches (Warsaw/Maldives/Fiji/Hawaii) visibly saturated the
    # primary instance under back-to-back sequential load.
    osm_overpass_fallback_mirrors: list[str] = [
        "https://overpass.kumi.systems/api/interpreter",
        # overpass.openstreetmap.fr dropped 2026-07-27: answers 403
        # ("white-listed usages only") to every request, so it was
        # guaranteed-wasted rotation slot during the prominence
        # re-ingestion retries (see docs/NEXT_SESSION_TODO.md).
    ]
    osm_poi_radius_m: int = 5000
    # Fallback radius tried when the default radius comes back thin/food-
    # dominated (see scrapers/osm.py::ingest_osm_pois) — small towns and
    # "hidden gem" hill-stations often have their few landmark/nature POIs
    # spread wider than 5km even though restaurants cluster densely near the
    # centre point, so a bigger radius both raises the total count and
    # rebalances the category mix. Live-confirmed 2026-07-23 for Coorg/
    # Jaisalmer (restaurant-dominated) and Spiti/Nainital (thin OSM).
    osm_poi_radius_expanded_m: int = 15000
    osm_poi_max_results: int = 60
    # Radius for the *prominence* Overpass pass (scrapers/osm.py). Wider than
    # the default 5km on purpose: a city's most famous sites are routinely
    # just outside it — live-probed 2026-07-25, Delhi at 5km misses Red Fort,
    # Qutub Minar, Lotus Temple and Chandni Chowk, and at 15km finds all four.
    # Affordable precisely because that pass is filtered to prominent
    # elements, so a 3x radius still returns hundreds of results, not tens of
    # thousands (Delhi 77 -> 159, Bangkok 668).
    osm_prominence_radius_m: int = 15000

    # How many district sub-articles to pull per hub city (scrapers/wikivoyage.py,
    # issue #45). Big-city guides delegate their priced Eat/Sleep listings to
    # per-district pages, so the parent alone under-reports what the guide
    # actually documents. Live-measured 2026-07-29 with only the first FIVE
    # districts: price-bearing chunks went Paris 28->85, Bangkok 17->44,
    # Tokyo 11->26 and Delhi 8->61 (x7.6, the largest gain and an India
    # destination). 8 is a deliberate compromise — the yield per district falls
    # off well before a city's full list is exhausted (Paris has 21 non-redirect
    # sub-pages, Tokyo 29), and each one costs an HTTP fetch plus an embedding
    # pass at ingestion time. Set to 0 to disable district scraping entirely.
    wikivoyage_max_district_subpages: int = 8

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000"]

    @field_validator("allowed_origins")
    @classmethod
    def _no_wildcard_origins(cls, v: list[str]) -> list[str]:
        # A wildcard here combined with credentialed requests is a classic
        # CORS misconfiguration (see docs/scaling-tech-challenges.md,
        # Security Vulnerabilities #7). Fail fast at startup rather than
        # silently accepting it.
        if any(origin.strip() == "*" for origin in v):
            raise ValueError(
                "ALLOWED_ORIGINS must not contain '*' — list explicit origins per environment."
            )
        return v

    # Nominatim / Wikivoyage / Overpass — must comply with both Nominatim's
    # ToS and Wikimedia's User-Agent policy (client/version + contact info,
    # "bot" in the name): a bare "wanderplanner/1.0" with no contact info
    # started getting hard-403'd by Wikivoyage (confirmed live 2026-07-20 —
    # see https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy).
    nominatim_user_agent: str = "WanderPlannerBot/1.0 (https://github.com/kunalsmathur-gif/wanderplanner)"
    nominatim_rate_limit: int = 1

    # Pexels — hero photos for the PDF export only, fetched on demand via
    # POST /api/day-photos when the user presses Download. NOT used by the
    # dashboard day cards (those render YouTube thumbnails) and no longer
    # touched during generation — see docs/itinerary-generation-flow.md.
    pexels_api_key: str = ""

    # Ingestion
    reddit_refresh_hours: int = 6
    reddit_min_score: int = 10
    content_filter_level: str = "strict"

    osm_refresh_days: int = 7
    osm_ingest_delay_seconds: float = 2.0  # be polite to the free Overpass API between destinations

    itinerary_corpus_refresh_days: int = 30  # monthly cadence (docs §9 ingestion pipeline)

    # YouTube Data API v3 (docs/NEXT_SESSION_TODO.md item 3 — hidden-gems
    # alternative source while Reddit ingestion is blocked on approval).
    # Self-serve key from Google Cloud Console, no review process. Costs are
    # 100 units/query for search.list and 1 unit/call for commentThreads.list
    # against a free 10,000-units/day allowance — but see the budget below:
    # that unit allowance is NOT the quota that binds. Blank by default: every function
    # in scrapers/youtube_comments.py is a documented no-op without a key,
    # same pattern as pexels_api_key.
    youtube_api_key: str = ""
    youtube_comments_per_video: int = 50
    youtube_videos_per_destination: int = 5

    # Quota guard for the above. `search.list` is the expensive call (100 of
    # the free tier's 10,000 units/day) — but the unit quota is NOT what binds.
    # It carries a second, dedicated cap: `defaultSearchListPerDayPerProject`,
    # 100 calls per project per day, on its own meter. So the real ceiling is
    # 100 searches/day however many units are left, and this budget of 80 is
    # 80% of the day rather than the headroom an earlier version of this
    # comment claimed. Measured against the live API on 2026-07-26 (a 429 body
    # names the metric and its limit); see TECHNICAL_DOCUMENTATION §14 v10.40.1.
    # Both quotas reset at midnight Pacific, not UTC.
    #
    # Both automatic callers (the cold-start gate in
    # services/destination_ingestion.py and the scheduler refresh below) go
    # through scrapers/youtube_comments.py's rolling-24h budget. Note that
    # budget is per-process, so it bounds any one process — not the project's
    # daily total across prod, scripts and eval runs combined.
    #
    # Set to the provider cap rather than below it (raised from 80 on
    # 2026-07-26): with the real ceiling known to be 100, holding back 20 was
    # reserving headroom this process cannot actually protect — a concurrent
    # prod cold-start spends from the same project quota and never consults
    # this window. So this is now a "don't exceed the provider" bound, and the
    # thing that degrades gracefully on exhaustion is the 429 handling, not the
    # margin. Callers already treat "no videos found" as a retryable no-op.
    youtube_daily_search_budget: int = 100
    # Cold-start ingestion is opt-out: unlike OSM/Wikivoyage (free, unmetered
    # public APIs) this spends a real quota, so it's worth being able to turn
    # off without unsetting the key entirely (which would also disable the
    # manual/eval paths).
    youtube_ingest_on_cold_start: bool = True
    youtube_refresh_days: int = 14
    # Per-run cap on the scheduler's refresh loop — the daily budget above is
    # the real ceiling; this just stops one run from consuming all of it in a
    # single burst, leaving none for cold starts until the window rolls.
    youtube_refresh_batch_size: int = 20

    # Slow drip-retry for youtube_narration destinations that landed
    # description-only because a transcript-fetch burst got IP-blocked
    # (issue #46 follow-up, observed 2026-07-30). No quota cost — this is
    # about spreading load thin over time, not budget — so the cadence is
    # short (hours, not days) and the batch is small, on purpose: a handful
    # of destinations every few hours looks nothing like the burst that
    # triggered the block in the first place.
    youtube_narration_transcript_retry_hours: int = 4
    youtube_narration_transcript_retry_batch_size: int = 5

    log_level: str = "INFO"

    # Optional error-tracking/APM (Sentry). Unset by default — a missing DSN
    # simply means sentry_sdk.init() is never called (no-op), so this is safe
    # to leave blank in dev/CI and only needs to be set in production once a
    # Sentry project exists. See docs/scaling-tech-challenges.md, "Now (any
    # traffic)" risk bucket: "structured logging + basic observability".
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    sentry_environment: str = "development"

    # Cost display currency conversion — Gemini list pricing is USD-denominated,
    # so per-call costs are still computed/stored internally in USD; this rate
    # is applied only at the admin-dashboard display layer to show INR instead.
    # Update periodically to track the real USD/INR rate (approximate is fine —
    # this is a directional cost signal, not accounting-grade billing).
    usd_to_inr_rate: float = 87.0

    # Database (users, sessions, analytics events)
    # Defaults to local SQLite (zero setup, free) -- override via .env for
    # Postgres in production (e.g. Supabase free tier).
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    # Supabase (and most managed Postgres hosts) require TLS on their direct
    # connection port -- asyncpg does not negotiate SSL automatically, so this
    # must be explicitly enabled for those hosts (set DATABASE_SSL_REQUIRE=true).
    # Leave false for local SQLite / local Postgres without TLS.
    database_ssl_require: bool = False

    # Auth / sessions
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    cookie_domain: str = ""  # empty = host-only cookie (fine for same-site local/dev)
    cookie_secure: bool = True
    # "lax" for local http dev; set to "none" in prod (requires cookie_secure=True)
    # since frontend (Vercel) and backend (Railway) are different origins.
    cookie_samesite: str = "lax"

    # Google OAuth (SSO)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Frontend origin to redirect back to after OAuth / password flows
    frontend_base_url: str = "http://localhost:3000"

    # Transactional email (Resend) — used for password reset links
    resend_api_key: str = ""
    # Must be on a domain verified with Resend, or every send 403s. The
    # default was `wanderplanner.app`, a domain nobody owns — so the fallback
    # was guaranteed to fail. `wanderplanner.org` is the real verified sending
    # domain (DKIM/SPF/DMARC live at the registrar as of 2026-07-25).
    email_from_address: str = "Wanderplanner <no-reply@wanderplanner.org>"
    password_reset_token_ttl_minutes: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def _require_real_secret_in_prod(cls, v: str) -> str:
        # Fails loudly in CI/prod if someone forgets to set a real secret,
        # rather than silently signing tokens with a well-known default.
        if v == "change-me-in-production" and is_production():
            raise ValueError("JWT_SECRET must be set to a strong random value in production.")
        return v

    @model_validator(mode="after")
    def _validate_cookie_settings_for_prod(self) -> "Settings":
        # This deployment model is frontend (Vercel) + backend (Railway) on
        # different origins in production, so session cookies MUST be
        # SameSite=None (with Secure=True — browsers reject None without
        # Secure) or every cross-site request silently drops them, which
        # then masquerades as three separate-looking bugs: an authenticated
        # user gets asked to sign in again, signup fails claiming a
        # duplicate account (it's not wrong — they really do have one, the
        # app just can't see the session), and signing back in appears to
        # loop forever. Fails loudly at startup instead of shipping this
        # silently, the same way `jwt_secret` above already does.
        if not is_production():
            return self
        if self.cookie_samesite.lower() == "lax":
            raise ValueError(
                "COOKIE_SAMESITE=lax will not work in production — frontend and backend are on "
                "different origins, and browsers drop SameSite=Lax cookies on cross-site requests. "
                "Set COOKIE_SAMESITE=none (and COOKIE_SECURE=true, which is already the default)."
            )
        if self.cookie_samesite.lower() == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SAMESITE=none requires COOKIE_SECURE=true — browsers reject SameSite=None "
                "cookies that aren't also marked Secure."
            )
        return self


settings = Settings()
