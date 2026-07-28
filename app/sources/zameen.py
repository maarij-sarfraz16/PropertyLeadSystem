"""Zameen source adapter.

Two modes:
- live: run an Apify Actor (id from the source config) and normalize its dataset items.
- fixtures: load a bundled sample so the pilot runs end-to-end without a token or network.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.sources.apify import ApifyRunner
from app.sources.base import RawPostData, SourceAdapter

_FIXTURE = Path(__file__).parent / "fixtures" / "zameen_sample.json"


class ZameenAdapter(SourceAdapter):
    name = "zameen"

    def __init__(self, config: dict[str, Any] | None = None, use_fixtures: bool = False) -> None:
        self.config = config or {}
        self.use_fixtures = use_fixtures

    def fetch(self, limit: int = 50) -> list[RawPostData]:
        items = self._load_fixtures() if self.use_fixtures else self._fetch_live(limit)
        return [self._normalize(item) for item in items[:limit]]

    # -- sources -------------------------------------------------------------
    def _load_fixtures(self) -> list[dict[str, Any]]:
        return json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def _fetch_live(self, limit: int) -> list[dict[str, Any]]:
        actor_id = self.config.get("apify_actor_id")
        if not actor_id:
            raise RuntimeError(
                "source config has no apify_actor_id. Set one, or use --fixtures for offline runs."
            )
        run_input = {"query": self.config.get("query", ""), "maxItems": limit}
        return ApifyRunner().run_actor(actor_id, run_input)

    # -- normalization -------------------------------------------------------
    def _normalize(self, item: dict[str, Any]) -> RawPostData:
        """Map a provider item to RawPostData. Tolerant of missing keys across Actor schemas."""
        text = item.get("text") or item.get("description") or item.get("title") or ""
        ext_id = item.get("id") or item.get("externalId") or item.get("url") or text[:64]
        return RawPostData(
            external_id=str(ext_id),
            text=text,
            url=item.get("url"),
            photo_urls=item.get("photos") or item.get("images") or [],
            raw_json=item,
        )
