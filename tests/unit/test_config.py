"""Unit tests for configuration management."""

import os

import pytest

from paperpulse.core.config import (
    DatabaseSettings,
    EmailSettings,
    GeminiSettings,
    RSSSettings,
    Settings,
)


class TestDatabaseSettings:
    """Tests for database configuration."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        settings = DatabaseSettings()
        assert settings.host == "localhost"
        assert settings.port == 5432
        assert settings.name == "paperpulse"

    def test_async_url_generation(self) -> None:
        """Should generate valid async URL."""
        settings = DatabaseSettings(
            host="db.example.com",
            port=5433,
            name="testdb",
            user="testuser",
            password="testpass",
        )
        url = settings.async_url
        assert "postgresql+asyncpg://" in url
        assert "testuser:testpass" in url
        assert "db.example.com:5433" in url
        assert "/testdb" in url

    def test_sync_url_generation(self) -> None:
        """Should generate valid sync URL for alembic."""
        settings = DatabaseSettings(
            host="localhost",
            name="paperpulse",
            user="user",
            password="pass",
        )
        url = settings.sync_url
        assert "postgresql://" in url
        assert "asyncpg" not in url


class TestGeminiSettings:
    """Tests for Gemini API configuration."""

    def test_default_models(self) -> None:
        """Should have default model configurations."""
        settings = GeminiSettings()
        assert settings.embedding_model == "text-embedding-004"
        assert settings.chat_model == "gemini-2.0-flash"
        assert settings.embedding_dimensions == 768


class TestEmailSettings:
    """Tests for email configuration."""

    def test_default_provider_is_console(self) -> None:
        """Default provider should be console for development."""
        settings = EmailSettings()
        assert settings.provider == "console"

    def test_smtp_defaults(self) -> None:
        """Should have Gmail SMTP defaults."""
        settings = EmailSettings()
        assert settings.smtp_host == "smtp.gmail.com"
        assert settings.smtp_port == 587
        assert settings.smtp_use_tls is True


class TestRSSSettings:
    """Tests for RSS collector configuration."""

    def test_default_timeout(self) -> None:
        """Should have reasonable timeout default."""
        settings = RSSSettings()
        assert settings.fetch_timeout_seconds == 30

    def test_default_retry_settings(self) -> None:
        """Should have retry settings configured."""
        settings = RSSSettings()
        assert settings.retry_attempts == 3
        assert settings.retry_delay_seconds == 2.0


class TestMainSettings:
    """Tests for main application settings."""

    def test_default_environment(self) -> None:
        """Default environment should be development."""
        settings = Settings()
        assert settings.environment == "development"
        assert settings.is_development is True

    def test_nested_settings_loaded(self) -> None:
        """Nested settings should be accessible."""
        settings = Settings()
        assert settings.database is not None
        assert settings.gemini is not None
        assert settings.email is not None
        assert settings.rss is not None

    def test_is_development_property(self) -> None:
        """is_development should reflect environment."""
        settings = Settings(environment="production")
        assert settings.is_development is False

        settings = Settings(environment="development")
        assert settings.is_development is True
