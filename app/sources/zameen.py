"""Zameen source adapter.

Three modes, chosen in this order:

- ``fixtures``: bundled offline sample. Unit tests and demos only — the sample URLs are
  synthetic and deliberately not zameen.com, so a fixture link can never be mistaken for a
  real advertisement.
- ``apify``: run an Apify Actor when ``apify_actor_id`` is configured on the source. Kept for
  sources that genuinely need managed proxying.
- ``web`` (default for live scans): read Zameen's own server-rendered search payload directly.
  No token, no third-party dependency, and it yields the listing slug needed to build the
  canonical ad URL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.pipeline.urls import first_listing_url
from app.sources.apify import ApifyRunner
from app.sources.base import RawPostData, SourceAdapter
from app.sources.zameen_web import ZameenWebScraper

log = get_logger(__name__)

_FIXTURE = Path(__file__).parent / "fixtures" / "zameen_sample.json"


class ZameenAdapter(SourceAdapter):
    name = "zameen"

    def __init__(self, config: dict[str, Any] | None = None, use_fixtures: bool = False) -> None:
        self.config = config or {}
        self.use_fixtures = use_fixtures

    @property
    def mode(self) -> str:
        if self.use_fixtures:
            return "fixtures"
        return "apify" if self.config.get("apify_actor_id") else "web"

    def fetch(self, limit: int = 50) -> list[RawPostData]:
        mode = self.mode
        if mode == "fixtures":
            items = self._load_fixtures()
        elif mode == "apify":
            items = self._fetch_apify(limit)
        else:
            # The web scraper already returns normalized, URL-validated posts.
            return ZameenWebScraper(
                base_url=self.config.get("base_url"),
                search_paths=self.config.get("search_paths"),
            ).fetch(limit=limit)

        posts = [self._normalize(item) for item in items[:limit]]
        return [post for post in posts if post is not None]

    # -- sources -------------------------------------------------------------
    def _load_fixtures(self) -> list[dict[str, Any]]:
        return json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def _fetch_apify(self, limit: int) -> list[dict[str, Any]]:
        run_input = {"query": self.config.get("query", ""), "maxItems": limit}
        return ApifyRunner().run_actor(self.config["apify_actor_id"], run_input)

    # -- normalization -------------------------------------------------------
    def _normalize(self, item: dict[str, Any]) -> RawPostData | None:
        """Map a provider item to RawPostData. Tolerant of missing keys across Actor schemas.

        Returns None when no genuine advertisement URL can be recovered: a lead whose link
        would 404 is worse than no lead, and it is the defect this pipeline had.
        """
        text = item.get("text") or item.get("description") or item.get("title") or ""
        ext_id = item.get("id") or item.get("externalId") or item.get("url") or text[:64]

        # Probe every field name Actors use for the ad link, but accept only a real listing URL.
        url = first_listing_url(
            item.get("url"), item.get("link"), item.get("adUrl"), item.get("detailUrl")
        )
        if not url:
            log.warning("listing.no_url", extra={"source": self.name, "external_id": str(ext_id)})
            return None

        return RawPostData(
            external_id=str(ext_id),
            text=text,
            title=item.get("title"),
            url=url,
            photo_urls=item.get("photos") or item.get("images") or [],
            raw_json=item,
        )
