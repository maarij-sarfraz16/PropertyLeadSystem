"""Listing-URL validation — the guard against the "Ad not found" regression."""
from __future__ import annotations

import pytest

from app.pipeline.urls import (
    build_zameen_listing_url,
    clean_listing_url,
    first_listing_url,
    is_listing_url,
)

_REAL = (
    "https://www.zameen.com/Property/dha_defence_dha_phase_6_luxury"
    "-54350713-1448-1.html"
)


@pytest.mark.parametrize(
    "url",
    [
        _REAL,
        "https://www.zameen.com/Plot/lahore_bahria-123-1.html",
        "https://example.com/zameen-fixture/Property/lahore-1001.html",
    ],
)
def test_accepts_real_listing_urls(url):
    assert is_listing_url(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "not a url",
        "ftp://www.zameen.com/Property/x-1.html",
        # The exact bug: a bare homepage must never pass as a listing.
        "https://www.zameen.com",
        "https://www.zameen.com/",
        # Search and content pages are not advertisements.
        "https://www.zameen.com/Houses_Property/Lahore-1-1.html",
        "https://www.zameen.com/blog/best-areas-lahore",
        # Right prefix, but not an ad page.
        "https://www.zameen.com/Property/",
    ],
)
def test_rejects_non_listing_urls(url):
    assert not is_listing_url(url)


def test_build_zameen_url_from_slug():
    slug = "dha_defence_dha_phase_6_luxury-54350713-1448-1"
    assert build_zameen_listing_url(slug) == f"https://www.zameen.com/Property/{slug}.html"


def test_build_zameen_url_is_idempotent_on_html_suffix():
    slug = "lahore_johar-123-1.html"
    assert build_zameen_listing_url(slug).endswith("lahore_johar-123-1.html")
    assert ".html.html" not in build_zameen_listing_url(slug)


def test_build_zameen_url_returns_none_without_slug():
    assert build_zameen_listing_url(None) is None
    assert build_zameen_listing_url("  ") is None


def test_clean_strips_tracking_params():
    assert clean_listing_url(f"{_REAL}?utm_source=x&ref=y") == _REAL


def test_clean_returns_none_for_non_listing():
    assert clean_listing_url("https://www.zameen.com/") is None


def test_first_listing_url_skips_bad_candidates_without_falling_back():
    assert first_listing_url(None, "https://www.zameen.com/", _REAL) == _REAL
    # Critically: when nothing is a real listing the answer is None, never a homepage.
    assert first_listing_url(None, "https://www.zameen.com/", "") is None
