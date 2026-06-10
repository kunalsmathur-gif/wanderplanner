from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    llm_provider: str = "groq"  # "groq" | "ollama" | "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    llm_timeout_seconds: int = 20

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_wiki: str = "wiki"
    qdrant_collection_reddit: str = "reddit"
    qdrant_collection_osm: str = "osm_pois"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Nominatim
    nominatim_user_agent: str = "wanderplan/1.0"
    nominatim_rate_limit: int = 1

    # Ingestion
    reddit_refresh_hours: int = 6
    reddit_min_score: int = 10
    content_filter_level: str = "strict"

    log_level: str = "INFO"


settings = Settings()
