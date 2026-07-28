"""Source adapter interface. One implementation now (Zameen); adding sources in Phase 2 is
config + a small adapter, not a rewrite of the pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RawPostData:
    """Normalized shape every adapter returns, regardless of provider payload."""

    external_id: str
    text: str
    url: str | None = None
    photo_urls: list[str] = field(default_factory=list)
    raw_json: dict = field(default_factory=dict)


class SourceAdapter(ABC):
    """Fetches posts from one source and normalizes them to RawPostData."""

    name: str

    @abstractmethod
    def fetch(self, limit: int = 50) -> list[RawPostData]:  # pragma: no cover - interface
        ...
