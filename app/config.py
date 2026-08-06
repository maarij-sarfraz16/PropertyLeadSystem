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

    # LLM extraction (Gemini via Google AI Studio; free tier for pilot)
    gemini_api_key: str | None = Field(default=None)
    extraction_model: str = Field(default="gemini-flash-latest")
    escalation_model: str = Field(default="gemini-flash-latest")
    extraction_confidence_threshold: float = Field(default=0.6)

    # --- Background scanner -------------------------------------------------
    # The worker starts with the API process (FastAPI lifespan) unless disabled.
    scan_enabled: bool = Field(
        default=True, description="Start the background scan worker with the API."
    )
    scan_interval_seconds: float = Field(
        default=30.0, ge=5.0, description="Seconds between scan cycles."
    )
    scan_startup_delay_seconds: float = Field(
        default=2.0, ge=0.0, description="Grace period before the first cycle."
    )
    scan_sources: str = Field(
        default="zameen", description="Comma-separated source names the worker scans."
    )
    scan_page_size: int = Field(
        default=25, ge=1, le=100, description="Listings pulled from the source per cycle."
    )
    scan_backfill_limit: int = Field(
        default=10,
        ge=0,
        description="Listings ingested on the very first cycle, before a watermark exists.",
    )
    scan_max_new_per_cycle: int = Field(
        default=10,
        ge=1,
        description="Cap on new listings processed per cycle. Bounds LLM spend per cycle.",
    )
    scan_error_backoff_seconds: float = Field(
        default=15.0, ge=1.0, description="Initial delay after a failed cycle."
    )
    scan_error_backoff_max_seconds: float = Field(
        default=300.0, ge=1.0, description="Ceiling for the exponential error backoff."
    )

    # --- Source: Zameen web scraper ----------------------------------------
    # Search pages the scraper polls, newest-first. Comma-separated paths.
    zameen_base_url: str = Field(default="https://www.zameen.com")
    zameen_search_paths: str = Field(
        default=(
            "/Homes/Lahore-1-1.html,/Homes/Karachi-2-1.html,"
            "/Plots/Lahore-1-1.html,/Plots/Karachi-2-1.html,"
            "/Commercial/Lahore-1-1.html,/Commercial/Karachi-2-1.html"
        ),
        description="Comma-separated Zameen search paths polled newest-first.",
    )
    zameen_request_timeout_seconds: float = Field(default=30.0, ge=1.0)

    # --- Extraction behaviour ----------------------------------------------
    extraction_enabled: bool = Field(
        default=True,
        description="Call the LLM for new listings. When false, the heuristic extractor is used.",
    )
    extraction_fallback_enabled: bool = Field(
        default=True,
        description="Fall back to the heuristic extractor when the LLM errors or is out of quota.",
    )

    # --- Saved-search alerts -------------------------------------------------
    alerts_enabled: bool = Field(
        default=True,
        description="Match new leads against saved searches. False disables alerting entirely.",
    )
    alerts_max_per_search_per_hour: int = Field(
        default=30,
        ge=0,
        description=(
            "Rolling hourly cap per saved search. Guards against a search so broad it buries "
            "the alert inbox. 0 disables the cap."
        ),
    )
    alerts_max_per_cycle: int = Field(
        default=50,
        ge=1,
        description="Total alerts created in one scan cycle, across all saved searches.",
    )

    # --- Realtime -----------------------------------------------------------
    realtime_queue_size: int = Field(
        default=100,
        ge=1,
        description="Per-subscriber event buffer. Oldest events drop when a client lags.",
    )
    realtime_heartbeat_seconds: float = Field(
        default=20.0, ge=1.0, description="Keepalive ping interval for WebSocket/SSE clients."
    )

    # --- Logging ------------------------------------------------------------
    log_level: str = Field(default="INFO")
    log_json: bool = Field(
        default=False, description="Emit newline-delimited JSON logs instead of console text."
    )

    # --- API ----------------------------------------------------------------
    cors_allow_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    )

    # -- derived helpers -----------------------------------------------------
    @property
    def scan_source_list(self) -> list[str]:
        return [name.strip() for name in self.scan_sources.split(",") if name.strip()]

    @property
    def zameen_search_path_list(self) -> list[str]:
        return [path.strip() for path in self.zameen_search_paths.split(",") if path.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
