"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "paperpulse"
    user: str = "paperpulse"
    password: SecretStr = SecretStr("paperpulse")

    @property
    def async_url(self) -> str:
        """Get async database URL for asyncpg."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        """Get sync database URL for alembic."""
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class GeminiSettings(BaseSettings):
    """Google Gemini API configuration."""

    model_config = SettingsConfigDict(env_prefix="GEMINI_")

    api_key: SecretStr = SecretStr("")
    embedding_model: str = "text-embedding-004"
    chat_model: str = "gemini-2.0-flash"
    embedding_dimensions: int = 768


class EmailSettings(BaseSettings):
    """Email delivery configuration."""

    model_config = SettingsConfigDict(env_prefix="EMAIL_")

    provider: Literal["smtp", "console"] = "console"
    from_address: str = "digest@paperpulse.local"
    from_name: str = "PaperPulse"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_use_tls: bool = True


class RSSSettings(BaseSettings):
    """RSS collector configuration."""

    model_config = SettingsConfigDict(env_prefix="RSS_")

    user_agent: str = "PaperPulse/1.0 (Academic Paper Aggregator)"
    fetch_timeout_seconds: int = 30
    max_concurrent_feeds: int = 5
    retry_attempts: int = 3
    retry_delay_seconds: float = 2.0


class SemanticScholarSettings(BaseSettings):
    """Semantic Scholar API configuration."""

    model_config = SettingsConfigDict(env_prefix="SEMANTIC_SCHOLAR_")

    api_key: SecretStr = SecretStr("")  # Optional, increases rate limits
    base_url: str = "https://api.semanticscholar.org/graph/v1"
    rate_limit_per_second: float = 10.0  # 100 requests per 5 minutes without key
    timeout_seconds: int = 30
    max_results_per_query: int = 100


class PubMedSettings(BaseSettings):
    """PubMed/NCBI Entrez API configuration."""

    model_config = SettingsConfigDict(env_prefix="PUBMED_")

    email: str = ""  # Required by NCBI
    api_key: SecretStr = SecretStr("")  # Optional, increases rate limits
    tool_name: str = "PaperPulse"
    rate_limit_per_second: float = 3.0  # 3/sec without key, 10/sec with key
    timeout_seconds: int = 30
    max_results_per_query: int = 100


class ArxivSettings(BaseSettings):
    """arXiv API configuration."""

    model_config = SettingsConfigDict(env_prefix="ARXIV_")

    rate_limit_per_second: float = 1.0  # arXiv recommends max 1 req/sec
    timeout_seconds: int = 30
    max_results_per_query: int = 100


class SchedulerSettings(BaseSettings):
    """Scheduler configuration for background jobs."""

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")

    # Enable/disable scheduler
    enabled: bool = True

    # Paper collection schedule (every N hours)
    collect_interval_hours: int = 6

    # Digest schedules
    digest_weekly_day: str = "sunday"  # monday, tuesday, etc.
    digest_weekly_hour: int = 8  # 0-23
    digest_daily_hour: int = 7  # 0-23

    # Immediate alerts check interval (minutes)
    alerts_interval_minutes: int = 60

    # Embedding updates (daily at this hour)
    embedding_update_hour: int = 2  # 0-23

    # Job execution settings
    max_job_instances: int = 1  # Prevent overlapping jobs
    job_coalesce: bool = True  # Combine missed runs
    misfire_grace_time: int = 3600  # Allow 1 hour late execution

    # Job store (memory or database)
    job_store: Literal["memory", "database"] = "memory"


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "PaperPulse"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    secret_key: SecretStr = SecretStr("dev-secret-key-change-in-production")

    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    rss: RSSSettings = Field(default_factory=RSSSettings)
    semantic_scholar: SemanticScholarSettings = Field(default_factory=SemanticScholarSettings)
    pubmed: PubMedSettings = Field(default_factory=PubMedSettings)
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
