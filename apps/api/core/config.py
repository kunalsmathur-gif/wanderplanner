from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_timeout_seconds: int = 30

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_wiki: str = "wiki"
    qdrant_collection_reddit: str = "reddit"
    qdrant_collection_osm: str = "osm_pois"
    qdrant_collection_itinerary_cache: str = "itinerary_cache"
    qdrant_collection_itinerary_corpus: str = "itinerary_corpus"
    qdrant_collection_youtube_comments: str = "youtube_comments"

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

    # Pexels — hero photos for itinerary day cards / PDF
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
    # Self-serve key from Google Cloud Console, no review process — free
    # 10,000-units/day quota; search.list costs 100 units/query,
    # commentThreads.list costs 1 unit/call. Blank by default: every function
    # in scrapers/youtube_comments.py is a documented no-op without a key,
    # same pattern as pexels_api_key.
    youtube_api_key: str = ""
    youtube_comments_per_video: int = 50
    youtube_videos_per_destination: int = 5

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
    email_from_address: str = "Wanderplanner <no-reply@wanderplanner.app>"
    password_reset_token_ttl_minutes: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def _require_real_secret_in_prod(cls, v: str) -> str:
        # Fails loudly in CI/prod if someone forgets to set a real secret,
        # rather than silently signing tokens with a well-known default.
        import os

        if v == "change-me-in-production" and os.getenv("ENVIRONMENT", "development") == "production":
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
        import os

        if os.getenv("ENVIRONMENT", "development") != "production":
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
