"""Derivations that turn free text into the two facets the leads list filters on.

City and property type were previously computed at render time, from the raw post payload.
That is fine for one row but impossible to filter or paginate on: the database cannot answer
"page 3 of the Lahore apartments" for a value it does not store. Both are therefore derived
once at ingest and persisted on `leads`, and this module is the single definition of how —
shared by the pipeline (writes) and the serializers (reads of pre-column rows).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Ordered: the first keyword family that matches wins, so "commercial plot" classifies as a
# plot only if no commercial marker precedes it. Kept narrow on purpose — a wrong label is
# worse than "Unknown", because the filter silently hides leads.
_PROPERTY_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Apartment", ("apartment", "flat", "penthouse")),
    ("House", ("house", "home", "villa", "bungalow", "upper portion", "lower portion")),
    ("Plot", ("plot", "land", "file")),
    ("Commercial", ("shop", "commercial", "office", "warehouse", "building")),
]

# raw_json keys different providers use for the listing's own category label. Checked before
# free text, since a provider's own field beats keyword matching on a title.
_RAW_TYPE_KEYS = (
    "propertyType",
    "property_type",
    "type",
    "category",
    "listingType",
    "listing_type",
)


# Cities the sources actually list in. Not exhaustive Pakistan — extending it is cheap, and an
# unlisted city still resolves through the last-segment fallback below.
KNOWN_CITIES: tuple[str, ...] = (
    "Lahore",
    "Karachi",
    "Islamabad",
    "Rawalpindi",
    "Faisalabad",
    "Multan",
    "Peshawar",
    "Quetta",
    "Gujranwala",
    "Sialkot",
    "Hyderabad",
    "Bahawalpur",
    "Sargodha",
    "Sukkur",
    "Sheikhupura",
    "Abbottabad",
    "Murree",
    "Jhelum",
    "Sahiwal",
    "Okara",
    "Kasur",
    "Gujrat",
    "Mardan",
    "Chiniot",
    "Nawabshah",
    "Larkana",
    "Mirpur",
    "Muzaffarabad",
    "Gwadar",
    "Rahim Yar Khan",
    "Dera Ghazi Khan",
    "Wah Cantt",
)


def derive_city(location_text: str | None) -> str | None:
    """The city a listing sits in, or None when the text names no city we recognise.

    Only names in `KNOWN_CITIES` are returned. The obvious alternative — take the last
    comma-segment — was tried and produced a city filter offering "sector C", "DHA Phase 3
    commercial" and "Johar Town near Emporium", because extracted locations are free text and
    frequently omit the city entirely. A dropdown of neighbourhood fragments is worse than one
    that admits it does not know: unrecognised locations become "Unknown" and stay findable
    through search, which matches `location_text` directly.

    The list is easy to extend; adding a city and re-running the facet refresh reclassifies
    every affected lead (see `app.db.init_db.backfill_lead_facets`).
    """
    if not location_text:
        return None

    lowered = location_text.lower()
    # Rightmost match wins. Pakistani addresses run narrow-to-wide ("Model Town, Lahore"), so
    # a city named late in the string is the actual city, while one named early is usually part
    # of a road or society name — "Multan Road, Lahore" is in Lahore, not Multan.
    best: tuple[int, str] | None = None
    for city in KNOWN_CITIES:
        position = lowered.rfind(city.lower())
        if position >= 0 and (best is None or position > best[0]):
            best = (position, city)
    return best[1] if best is not None else None


def derive_property_type(
    raw_json: dict[str, Any] | None = None,
    texts: Iterable[str | None] = (),
) -> str | None:
    """Best-effort property category, or None when nothing in the payload indicates one."""
    candidates: list[Any] = []
    if raw_json:
        candidates.extend(raw_json.get(key) for key in _RAW_TYPE_KEYS)
    candidates.extend(texts)

    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).lower()
        for label, keywords in _PROPERTY_TYPE_RULES:
            if any(keyword in text for keyword in keywords):
                return label
    return None


PROPERTY_TYPES: tuple[str, ...] = tuple(label for label, _ in _PROPERTY_TYPE_RULES)
