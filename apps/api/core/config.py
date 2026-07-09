from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_provider: str = "groq"  # "groq" | "gemini" | "ollama" | "mock"
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
    itinerary_cache_score_threshold: float = 0.88

    # OSM POI ingestion (docs §3I)
    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    osm_poi_radius_m: int = 5000
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

    # Nominatim
    nominatim_user_agent: str = "wanderplanner/1.0"
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

    log_level: str = "INFO"

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


settings = Settings()
