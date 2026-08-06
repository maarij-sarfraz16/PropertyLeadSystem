"""Source adapter interface. One implementation now (Zameen); adding sources in Phase 2 is
config + a small adapter, not a rewrite of the pipeline.
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawPostData:
    """Normalized shape every adapter returns, regardless of provider payload.

    `url` is the deep link to the original advertisement and must already be validated by
    `app.pipeline.urls`; adapters set it to None rather than to a fallback page.

    `posted_at` is the platform's own publish time. The scanner uses it as its watermark, so
    an adapter that can supply it lets the pipeline detect "new since last cycle" precisely
    instead of re-diffing whole pages.

    `facts` carries structured fields the source already states authoritatively (price, area,
    bedrooms, contact). The pipeline trusts these over LLM guesses — the model is only asked
    for what the portal does not state outright.
    """

    external_id: str
    text: str
    url: str | None = None
    title: str | None = None
    posted_at: dt.datetime | None = None
    photo_urls: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    raw_json: dict = field(default_factory=dict)


class SourceAdapter(ABC):
    """Fetches posts from one source and normalizes them to RawPostData."""

    name: str

    @abstractmethod
    def fetch(self, limit: int = 50) -> list[RawPostData]:  # pragma: no cover - interface
        ...
