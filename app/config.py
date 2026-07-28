"""Centralized settings. Loaded from environment / .env, validated by pydantic.

No secret is ever hardcoded — everything sensitive comes through here so there is a
single place to swap in a secrets manager when prod hosting is chosen.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://leadint:leadint@localhost:5432/leadint"
    )

    # Redis (queue / rate-limit buckets; used from Phase 1b)
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Apify
    apify_token: str | None = Field(default=None)

    # Anthropic
    anthropic_api_key: str | None = Field(default=None)
    extraction_model: str = Field(default="claude-haiku-4-5-20251001")
    escalation_model: str = Field(default="claude-sonnet-4-6")
    extraction_confidence_threshold: float = Field(default=0.6)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
