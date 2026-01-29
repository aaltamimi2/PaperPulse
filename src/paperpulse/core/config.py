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

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
