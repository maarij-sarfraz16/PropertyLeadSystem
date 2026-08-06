"""Zameen search-payload parsing.

The sample below mirrors the real `window.state` shape (verified against the live site),
trimmed to the fields the scraper reads.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from app.sources.zameen_web import (
    ZameenScrapeError,
    ZameenWebScraper,
    extract_window_state,
    hits_from_state,
)

_HIT = {
    "externalID": "54350713",
    "id": 116037574,
    "slug": "dha_defence_dha_phase_6_luxury_residence-54350713-1448-1",
    "title": "DHA Phase 6 Luxury Residence",
    "shortDescription": "1-kanal ultra modern house.",
    "price": 240000000,
    "rooms": 5,
    "baths": 6,
    "area": 505.857,  # square metres -> 20 marla
    "purpose": "for-sale",
    "createdAt": 1785842169,
    "geography": {"lat": 31.471571, "lng": 74.445906},
    "agency": {"name": "Wall Green Realtors"},
    "contactName": "Muhammad Munir",
    "phoneNumber": {"mobile": "+923234121106", "whatsapp": "923234121106"},
    "coverPhoto": {"url": "https://img.example.com/cover.jpg"},
    "category": [{"name": "Homes"}, {"name": "Houses"}],
    "location": [
        {"level": 0, "name": "Pakistan"},
        {"level": 1, "name": "Punjab"},
        {"level": 2, "name": "Lahore"},
        {"level": 3, "name": "DHA Defence"},
        {"level": 4, "name": "DHA Phase 6"},
    ],
}


def _page(hits: list[dict]) -> str:
    state = {"algolia": {"content": {"hits": hits}}}
    # The real page embeds the blob inside a script tag, followed by more markup.
    return f"<html><script>window.state = {json.dumps(state)};</script><div>rest</div></html>"


def test_extract_window_state_handles_trailing_markup():
    state = extract_window_state(_page([_HIT]))
    assert hits_from_state(state)[0]["externalID"] == "54350713"


def test_extract_window_state_survives_script_tag_inside_json():
    """A regex-based parser terminates early here; the brace-matching decoder does not."""
    hit = {**_HIT, "shortDescription": "Call now </script> for details"}
    parsed = hits_from_state(extract_window_state(_page([hit])))
    assert parsed[0]["shortDescription"].startswith("Call")


def test_extract_window_state_raises_without_blob():
    with pytest.raises(ZameenScrapeError):
        extract_window_state("<html><body>no state here</body></html>")


def test_hits_from_state_tolerates_missing_container():
    assert hits_from_state({}) == []
    assert hits_from_state({"algolia": {"content": {}}}) == []


def test_normalize_builds_canonical_listing_url():
    post = ZameenWebScraper()._normalize(_HIT)
    assert post is not None
    assert post.url == (
        "https://www.zameen.com/Property/"
        "dha_defence_dha_phase_6_luxury_residence-54350713-1448-1.html"
    )


def test_normalize_extracts_publish_time_for_the_watermark():
    post = ZameenWebScraper()._normalize(_HIT)
    assert post.posted_at == dt.datetime.fromtimestamp(1785842169, tz=dt.UTC)


def test_normalize_maps_authoritative_facts():
    facts = ZameenWebScraper()._normalize(_HIT).facts
    assert facts["price"] == 240000000
    assert facts["bedrooms"] == 5
    assert facts["intent"] == "sell"
    assert facts["seller_type"] == "agent"  # an agency block means an agency listing
    assert facts["contact_phone"] == "+923234121106"
    assert facts["property_type"] == "Houses"
    # Area converted from square metres to marla, most-specific-first location.
    assert facts["area_value"] == pytest.approx(20.0, abs=0.1)
    assert facts["location_text"] == "DHA Phase 6, DHA Defence, Lahore"


def test_normalize_skips_listing_without_a_usable_url():
    """No slug and no url means no verifiable ad — better dropped than stored broken."""
    assert ZameenWebScraper()._normalize({**_HIT, "slug": None}) is None


def test_normalize_skips_hit_without_id():
    assert ZameenWebScraper()._normalize({"slug": "x-1-1"}) is None


def test_fetch_interleaves_across_paths(monkeypatch):
    """A prolific path (e.g. Homes) must not consume the whole per-cycle limit before a
    smaller path (e.g. Plots) is ever reached."""

    def _hit(hit_id: str, category: str) -> dict:
        return {
            **_HIT,
            "externalID": hit_id,
            "id": hit_id,
            "slug": f"listing-{hit_id}-1-1",
            "category": [{"name": category}],
        }

    pages = {
        "/Homes/Lahore-1-1.html": [_hit(f"home-{i}", "Homes") for i in range(20)],
        "/Plots/Lahore-1-1.html": [_hit(f"plot-{i}", "Plots") for i in range(20)],
    }

    scraper = ZameenWebScraper(search_paths=list(pages))
    monkeypatch.setattr(
        scraper, "_fetch_path", lambda client, path: pages[path]
    )

    posts = scraper.fetch(limit=10)

    ids = {post.external_id for post in posts}
    assert any(i.startswith("home-") for i in ids)
    assert any(i.startswith("plot-") for i in ids)


def test_search_url_applies_newest_first():
    scraper = ZameenWebScraper(search_paths=["/Homes/Lahore-1-1.html"])
    assert scraper._search_url("/Homes/Lahore-1-1.html").endswith("?sort=newest")
    # An explicit sort in the configured path is respected, not duplicated.
    assert scraper._search_url("/Homes/Lahore-1-1.html?sort=price").count("sort=") == 1
