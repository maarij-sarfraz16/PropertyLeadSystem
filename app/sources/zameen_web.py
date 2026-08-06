"""Zameen.com search scraper.

Zameen server-renders its search pages with the full result set embedded as a JSON blob
assigned to ``window.state``. Its ``algolia.content.hits`` array is the same payload the site
itself renders from, so parsing it gives structured, authoritative fields — including the
listing ``slug`` used to build the canonical ad URL, and ``createdAt`` (unix seconds) which
lets the scanner detect genuinely new inventory instead of re-diffing pages.

Reading that blob is preferred over HTML scraping: it does not break on markup changes, needs
no headless browser, and yields typed fields rather than strings parsed out of the DOM.

Appending ``?sort=newest`` makes the first page the newest listings, so one small request per
cycle is enough to catch everything published since the last scan.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

import httpx

from app.config import get_settings
from app.logging_config import get_logger
from app.pipeline.photos import public_photo_urls
from app.pipeline.urls import build_zameen_listing_url, first_listing_url
from app.sources.base import RawPostData

log = get_logger(__name__)

_STATE_MARKER = "window.state"

# A plain client hint. Zameen serves this payload to ordinary browsers; we identify as one and
# poll at a modest, configurable cadence rather than trying to evade anything.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


class ZameenScrapeError(RuntimeError):
    """Raised when a search page cannot be fetched or its embedded state cannot be parsed."""


def extract_window_state(html: str) -> dict[str, Any]:
    """Pull the ``window.state`` JSON object out of a Zameen page.

    Uses a brace-matching JSON decoder rather than a regex: the blob is ~1 MB of nested JSON
    containing ``</script>`` inside string values, which a regex terminates on incorrectly.
    """
    marker = html.find(_STATE_MARKER)
    if marker == -1:
        raise ZameenScrapeError("no window.state blob found in page")
    try:
        start = html.index("{", marker)
        state, _ = json.JSONDecoder().raw_decode(html, start)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ZameenScrapeError(f"could not decode window.state: {exc}") from exc
    if not isinstance(state, dict):
        raise ZameenScrapeError("window.state was not an object")
    return state


def hits_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the search-result hits, tolerating an absent/renamed container."""
    hits = (state.get("algolia") or {}).get("content", {}).get("hits")
    return [hit for hit in hits if isinstance(hit, dict)] if isinstance(hits, list) else []


class ZameenWebScraper:
    """Fetches newest-first listings from one or more Zameen search paths."""

    def __init__(
        self,
        base_url: str | None = None,
        search_paths: list[str] | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.zameen_base_url).rstrip("/")
        self.search_paths = search_paths or settings.zameen_search_path_list
        self.timeout = timeout or settings.zameen_request_timeout_seconds

    def fetch(self, limit: int = 25) -> list[RawPostData]:
        """Fetch up to `limit` listings across the configured search paths, newest first.

        Every configured path is fetched (one cheap request each), and posts are interleaved
        round-robin across paths rather than filled from the first path to `limit`. A prolific
        category like Homes returns far more than `limit` hits on its own; filling the quota
        from it first — as an earlier version of this method did — meant Plots and Commercial
        paths were configured but never actually reached.
        """
        posts_by_path: list[list[RawPostData]] = []
        seen_ids: set[str] = set()
        errors: list[str] = []

        with httpx.Client(
            timeout=self.timeout, headers=_HEADERS, follow_redirects=True
        ) as client:
            for path in self.search_paths:
                try:
                    hits = self._fetch_path(client, path)
                except ZameenScrapeError as exc:
                    # One bad path must not sink the cycle: record and continue.
                    errors.append(f"{path}: {exc}")
                    log.warning(
                        "source.path_failed",
                        extra={"source": "zameen", "path": path, "error": str(exc)},
                    )
                    continue

                path_posts: list[RawPostData] = []
                for hit in hits:
                    post = self._normalize(hit)
                    if post is None or post.external_id in seen_ids:
                        continue
                    seen_ids.add(post.external_id)
                    path_posts.append(post)
                posts_by_path.append(path_posts)

        if not any(posts_by_path) and errors:
            raise ZameenScrapeError("; ".join(errors))

        posts: list[RawPostData] = []
        round_index = 0
        while len(posts) < limit and any(round_index < len(p) for p in posts_by_path):
            for path_posts in posts_by_path:
                if round_index < len(path_posts):
                    posts.append(path_posts[round_index])
                    if len(posts) >= limit:
                        break
            round_index += 1

        # Newest first, so the caller can stop at the watermark.
        oldest = dt.datetime.min.replace(tzinfo=dt.UTC)
        posts.sort(key=lambda post: post.posted_at or oldest, reverse=True)
        return posts

    # -- internals -----------------------------------------------------------
    def _fetch_path(self, client: httpx.Client, path: str) -> list[dict[str, Any]]:
        url = self._search_url(path)
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ZameenScrapeError(f"request failed: {exc}") from exc
        return hits_from_state(extract_window_state(response.text))

    def _search_url(self, path: str) -> str:
        """Absolute search URL with newest-first ordering applied."""
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        if "sort=" not in url:
            url += ("&" if "?" in url else "?") + "sort=newest"
        return url

    def _normalize(self, hit: dict[str, Any]) -> RawPostData | None:
        """Map one search hit to RawPostData, or None if it lacks an id or a usable ad URL."""
        external_id = hit.get("externalID") or hit.get("id")
        if external_id is None:
            return None
        external_id = str(external_id)

        # The listing URL is built from the slug and validated. If neither the slug nor an
        # explicit URL field yields a real ad link, the listing is skipped outright rather
        # than stored with a URL that would 404 — this is the "Ad not found" fix.
        listing_url = first_listing_url(
            build_zameen_listing_url(hit.get("slug"), self.base_url),
            hit.get("url"),
            hit.get("link"),
        )
        if not listing_url:
            log.debug("listing.no_url", extra={"source": "zameen", "external_id": external_id})
            return None

        title = str(hit.get("title") or "").strip()
        description = str(hit.get("shortDescription") or "").strip()
        location_text = _location_text(hit)
        facts = _facts(hit, location_text)

        return RawPostData(
            external_id=external_id,
            title=title or None,
            url=listing_url,
            text=_listing_text(title, description, location_text, facts),
            posted_at=_epoch_to_utc(hit.get("createdAt")),
            photo_urls=_photo_urls(hit),
            facts=facts,
            raw_json=_compact_raw(hit, listing_url),
        )


# -- field mapping -----------------------------------------------------------
def _epoch_to_utc(value: Any) -> dt.datetime | None:
    """Zameen reports publish time as unix seconds."""
    try:
        return dt.datetime.fromtimestamp(float(value), tz=dt.UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _location_text(hit: dict[str, Any]) -> str | None:
    """Join the location hierarchy below country/province into 'Area, Society, City'."""
    locations = hit.get("location")
    if not isinstance(locations, list):
        return None
    names = [
        str(entry.get("name")).strip()
        for entry in locations
        if isinstance(entry, dict) and entry.get("level", 0) >= 2 and entry.get("name")
    ]
    # Most specific first reads better in the UI than the portal's country-down order.
    return ", ".join(reversed(names)) if names else None


def _category_name(hit: dict[str, Any]) -> str | None:
    categories = hit.get("category")
    if isinstance(categories, list) and categories:
        last = categories[-1]
        if isinstance(last, dict) and last.get("name"):
            return str(last["name"])
    return None


def _contact_phone(hit: dict[str, Any]) -> str | None:
    phone = hit.get("phoneNumber")
    if not isinstance(phone, dict):
        return None
    for key in ("mobile", "phone", "whatsapp"):
        value = phone.get(key)
        if value:
            return str(value)
    numbers = phone.get("mobileNumbers") or phone.get("phoneNumbers")
    if isinstance(numbers, list) and numbers:
        return str(numbers[0])
    return None


def _facts(hit: dict[str, Any], location_text: str | None) -> dict[str, Any]:
    """Fields Zameen states authoritatively. These override LLM guesses downstream."""
    purpose = str(hit.get("purpose") or "")
    area_sqm = hit.get("area")
    agency = _as_dict(hit.get("agency"))
    geo = _as_dict(hit.get("geography"))
    return {
        "intent": "rent" if purpose == "for-rent" else "sell" if purpose == "for-sale" else None,
        "location_text": location_text,
        "price": _as_float(hit.get("price")),
        "currency": "PKR",
        # Zameen reports area in square metres; the market quotes marla (1 marla = 25.2929 m2).
        "area_value": round(float(area_sqm) / 25.2929, 2) if _as_float(area_sqm) else None,
        "area_unit": "marla" if _as_float(area_sqm) else None,
        "bedrooms": _as_int(hit.get("rooms")),
        "bathrooms": _as_int(hit.get("baths")),
        # An ad carrying an agency block is an agency listing; that is a fact, not an inference.
        "seller_type": "agent" if agency else None,
        "contact_name": hit.get("contactName") or None,
        "contact_phone": _contact_phone(hit),
        "property_type": _category_name(hit),
        "agency": agency.get("name") if agency else None,
        "latitude": _as_float(geo.get("lat")),
        "longitude": _as_float(geo.get("lng")),
    }


def _listing_text(
    title: str, description: str, location_text: str | None, facts: dict[str, Any]
) -> str:
    """Compact prompt text for the extractor: the ad as a human would read it."""
    parts = [title, description]
    if location_text:
        parts.append(f"Location: {location_text}")
    if facts.get("price"):
        parts.append(f"Price: {facts['price']:.0f} PKR")
    if facts.get("area_value"):
        parts.append(f"Area: {facts['area_value']} marla")
    if facts.get("bedrooms"):
        parts.append(f"Bedrooms: {facts['bedrooms']}")
    if facts.get("property_type"):
        parts.append(f"Type: {facts['property_type']}")
    if facts.get("agency"):
        parts.append(f"Listed by agency: {facts['agency']}")
    if facts.get("contact_phone"):
        parts.append(f"Contact: {facts['contact_phone']}")
    return "\n".join(part for part in parts if part)


def _photo_urls(hit: dict[str, Any]) -> list[str]:
    """The listing's cover photo, rewritten to the CDN rendition a browser can load.

    The API returns the private S3 object path, which answers 403 — see
    `app.pipeline.photos`. Only the cover is available here; the search response carries a
    `photoCount` but not the remaining image ids, so the gallery shows what the source gave.
    """
    cover = hit.get("coverPhoto")
    if isinstance(cover, dict) and cover.get("url"):
        return public_photo_urls([str(cover["url"])])
    return []


def _compact_raw(hit: dict[str, Any], listing_url: str) -> dict[str, Any]:
    """Store a trimmed payload.

    A full hit is ~8 KB of mostly localized duplicates and agency metadata. Persisting all of
    it on every listing bloats the table and the dashboard's metadata panel for no benefit, so
    keep the fields that are actually read back.
    """
    return {
        "externalID": hit.get("externalID"),
        "url": listing_url,
        "title": hit.get("title"),
        "shortDescription": hit.get("shortDescription"),
        "price": hit.get("price"),
        "rooms": hit.get("rooms"),
        "baths": hit.get("baths"),
        "area": hit.get("area"),
        "purpose": hit.get("purpose"),
        "product": hit.get("product"),
        "isVerified": hit.get("isVerified"),
        "photoCount": hit.get("photoCount"),
        "createdAt": hit.get("createdAt"),
        "propertyType": _category_name(hit),
        "agency": _as_dict(hit.get("agency")).get("name"),
        "contactName": hit.get("contactName"),
        "coverPhoto": _as_dict(hit.get("coverPhoto")).get("url"),
        "geography": hit.get("geography"),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    """Nested blocks are sometimes null; treat anything non-dict as absent."""
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
