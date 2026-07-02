from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Nominatim
    nominatim_user_agent: str = "wanderplan/1.0"
    nominatim_rate_limit: int = 1

    # Ingestion
    reddit_refresh_hours: int = 6
    reddit_min_score: int = 10
    content_filter_level: str = "strict"

    osm_refresh_days: int = 7
    osm_ingest_delay_seconds: float = 2.0  # be polite to the free Overpass API between destinations

    log_level: str = "INFO"


settings = Settings()
