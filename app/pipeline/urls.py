"""Listing-URL construction and validation.

Root cause of the "Ad not found" bug this module fixes: nothing in the pipeline ever
asserted that a stored URL pointed at an *advertisement*. A missing or truncated URL was
silently accepted, and anything that fell back to a bare domain sent the user to the Zameen
homepage, which renders "Ad not found" for a deep-link expectation.

The rule enforced here: a listing URL is stored only if it is an absolute http(s) URL with a
path that identifies a single advertisement. Anything else is stored as NULL, so the
dashboard can honestly render "Unavailable" instead of shipping a dead link.
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

# Path prefixes that identify a single advertisement on Zameen.
_ZAMEEN_LISTING_PREFIXES = ("/property/", "/plot/", "/rentals/")

# Paths that are emphatically NOT a listing. A URL resolving to one of these is the exact
# failure mode being fixed, so they are rejected rather than stored.
_NON_LISTING_PATHS = {"", "/", "/index.html", "/home", "/homepage"}


def build_zameen_listing_url(
    slug: str | None, base_url: str = "https://www.zameen.com"
) -> str | None:
    """Build the canonical ad URL from a Zameen search-result slug.

    Zameen's search payload carries `slug` (e.g. ``dha_defence_..._-54350713-1448-1``) rather
    than a full URL; the public ad lives at ``/Property/<slug>.html``. Building it here — once —
    means every adapter path produces the same canonical form.
    """
    if not slug:
        return None
    slug = slug.strip().strip("/")
    if not slug:
        return None
    if slug.lower().endswith(".html"):
        slug = slug[: -len(".html")]
    return f"{base_url.rstrip('/')}/Property/{slug}.html"


def is_listing_url(url: str | None) -> bool:
    """True only for an absolute http(s) URL whose path identifies one advertisement."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    path = parsed.path.rstrip("/").lower() or "/"
    if path in _NON_LISTING_PATHS:
        return False

    host = parsed.netloc.lower()
    if "zameen." in host:
        # Zameen ads always live under a listing prefix and end in .html. A URL that does not
        # is a search page, a blog post, or the homepage — never an ad.
        return path.startswith(_ZAMEEN_LISTING_PREFIXES) and path.endswith(".html")

    # Other sources: require a path with real content, not a bare domain.
    return len(path) > 1


def clean_listing_url(url: str | None) -> str | None:
    """Return a normalized listing URL, or None if it does not identify an advertisement.

    Tracking parameters are stripped: they make identical ads look like distinct URLs and
    add nothing when the user opens the page.
    """
    if not is_listing_url(url):
        return None
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def first_listing_url(*candidates: str | None) -> str | None:
    """Return the first candidate that is a genuine listing URL, else None.

    Used by adapters that must probe several provider field names (`url`, `link`, `adUrl`, …)
    without ever degrading to a non-listing fallback.
    """
    for candidate in candidates:
        cleaned = clean_listing_url(candidate)
        if cleaned:
            return cleaned
    return None
