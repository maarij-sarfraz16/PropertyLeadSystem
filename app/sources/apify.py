"""Thin Apify runner: start an Actor, wait, return its dataset items.

Apify handles proxy rotation, CAPTCHAs, and dynamic content internally — that is the whole
reason we use it instead of building anti-bot evasion in-house (see plan section 1).
"""
from __future__ import annotations

from typing import Any

from apify_client import ApifyClient

from app.config import get_settings


class ApifyRunner:
    def __init__(self, token: str | None = None) -> None:
        token = token or get_settings().apify_token
        if not token:
            raise RuntimeError(
                "APIFY_TOKEN not set. Set it in .env, or run the scan with --fixtures for "
                "offline testing."
            )
        self._client = ApifyClient(token)

    def run_actor(self, actor_id: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
        run = self._client.actor(actor_id).call(run_input=run_input)
        dataset_id = run["defaultDatasetId"]
        return list(self._client.dataset(dataset_id).iterate_items())
