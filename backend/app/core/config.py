from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Task Bot"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://taskbot:taskbot@localhost:5432/taskbot"

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Redis pub/sub (realtime task events -> WebSocket clients) ---
    # A separate logical DB from the Celery broker so the two concerns never
    # collide, even though both live on the same Redis instance.
    redis_pubsub_url: str = "redis://localhost:6379/1"
    task_events_channel: str = "task_events"

    # --- Telegram ---
    telegram_bot_token: str = ""
    max_voice_duration_seconds: int = 120
    max_voice_file_mb: int = 20
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_request_timeout_seconds: float = 15.0

    # --- OpenAI / Whisper ---
    openai_api_key: str = ""
    whisper_model: str = "whisper-1"
    whisper_language: str = ""

    # --- Bot -> backend integration ---
    backend_internal_url: str = "http://localhost:8000"
    # Shared secret that lets the bot act on behalf of a Telegram user. The
    # default is for local development only — see .env.example.
    internal_api_token: str = "local-dev-only-change-me"

    # --- Dashboard ---
    # Public base URL, used to build the link the bot sends on /dashboard.
    dashboard_base_url: str = "http://localhost:3001"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url_sync(self) -> str:
        """Sync SQLAlchemy URL (psycopg) for Celery's worker, which cannot use asyncio."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")

    @property
    def max_voice_file_bytes(self) -> int:
        return self.max_voice_file_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
