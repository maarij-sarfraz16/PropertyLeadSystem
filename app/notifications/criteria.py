"""Saved-search criteria: storage shape, rehydration, and what counts as narrow enough.

A saved search is a persisted `LeadFilters`. It is stored as the **camelCase wire keys** the
leads API already speaks (`city`, `sellerType`, `minScore`, ...) rather than the dataclass
field names, because that contract is shared by `list_leads`' signature and the dashboard's
`leadQueryToSearchParams` — so stored criteria convert to a querystring with no translation,
and the criteria that fired an alert are exactly the criteria the click-through list applies.

Two rules keep stored blobs safe:

**Never `LeadFilters(**blob)`.** A blob written today outlives the code that wrote it. Every
key is whitelisted and coerced; unknown keys are ignored rather than raising, so adding or
removing a filter field can never strand an existing search.

**Date filters are never stored.** The dashboard resolves its date presets to absolute
instants before sending them (`resolveDateRange`), so persisting `dateFrom`/`dateTo` would
freeze a search to the day it was created and it would silently never match again. The
preset is kept as presentation-only metadata for rebuilding the click-through URL.
"""
from __future__ import annotations

from typing import Any

from app.leads_query import LeadFilters

# Wire key -> LeadFilters field, for the filters that take a list of strings.
_LIST_KEYS: dict[str, str] = {
    "city": "cities",
    "source": "sources",
    "sellerType": "seller_types",
    "propertyType": "property_types",
    "status": "statuses",
}

# Wire key -> LeadFilters field, for the numeric bounds.
_NUMBER_KEYS: dict[str, str] = {
    "minScore": "min_score",
    "maxScore": "max_score",
    "minPrice": "min_price",
    "maxPrice": "max_price",
    "minBedrooms": "min_bedrooms",
    "maxBedrooms": "max_bedrooms",
}

# Dropped on save and ignored on load. Storing a resolved instant freezes the search; `sort`,
# `page` and `pageSize` are presentation, not matching.
_DROPPED_KEYS = frozenset({"dateFrom", "dateTo", "sort", "page", "pageSize"})

# Presentation-only metadata: replayed into the UI when a saved search is opened, never matched
# on. Kept under one key so it cannot be confused with a filter.
PRESENTATION_KEY = "_presentation"

# A search narrowed by none of these matches essentially every lead, which is what the
# existing `lead.created` stream already provides. `status` is excluded deliberately: a new
# lead is always `new` or `incomplete`, so a status filter can never make a search *fire*.
_NARROWING_KEYS = frozenset(
    {"search", "city", "source", "sellerType", "propertyType", *_NUMBER_KEYS}
)


def _clean_strings(value: Any) -> list[str]:
    """Coerce a wire value into a list of non-empty strings, order-preserving and deduped.

    Accepts a list or a single scalar, mirroring how the query parser tolerates both
    `?city=A&city=B` and `?city=A,B`.

    Non-scalar entries (a dict, a nested list) are dropped rather than stringified: `str()` on
    a dict yields `"{'a': 'b'}"`, which would become a real predicate matching nothing and
    leave the search quietly broken instead of merely ignoring the bad key.
    """
    if value is None or isinstance(value, dict):
        return []
    raw = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None or not isinstance(item, (str, int, float, bool)):
            continue
        for part in str(item).split(","):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                out.append(part)
    return out


def _clean_number(value: Any) -> float | None:
    """Coerce to a float, or None when the value is absent or not numeric."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_criteria(criteria: dict[str, Any] | None) -> dict[str, Any]:
    """Canonicalize a criteria blob for storage: whitelist, coerce, drop empties and dates."""
    criteria = criteria or {}
    out: dict[str, Any] = {}

    search = criteria.get("search")
    if search is not None and str(search).strip():
        out["search"] = str(search).strip()

    for wire_key in _LIST_KEYS:
        values = _clean_strings(criteria.get(wire_key))
        if values:
            out[wire_key] = values

    for wire_key in _NUMBER_KEYS:
        number = _clean_number(criteria.get(wire_key))
        if number is not None:
            out[wire_key] = number

    presentation = criteria.get(PRESENTATION_KEY)
    if isinstance(presentation, dict) and presentation:
        out[PRESENTATION_KEY] = presentation

    return out


def criteria_to_filters(criteria: dict[str, Any] | None) -> LeadFilters:
    """Rehydrate stored criteria into `LeadFilters`, ignoring anything unrecognised.

    Defensive by construction: a blob containing a filter this build no longer knows about,
    a wrong type, or a stale date range still produces a usable filter set rather than an
    exception that would take the whole matching cycle down.
    """
    criteria = criteria or {}

    search = criteria.get("search")
    search = str(search).strip() if search is not None and str(search).strip() else None

    kwargs: dict[str, Any] = {"search": search}
    for wire_key, field in _LIST_KEYS.items():
        kwargs[field] = tuple(_clean_strings(criteria.get(wire_key)))
    for wire_key, field in _NUMBER_KEYS.items():
        kwargs[field] = _clean_number(criteria.get(wire_key))

    # date_from / date_to are intentionally left at their defaults — see the module docstring.
    return LeadFilters(**kwargs)


def is_matchable(criteria: dict[str, Any] | None) -> bool:
    """True if the criteria narrow the result set at all.

    Guards against the saved search that matches everything: at peak the scanner discovers
    ~140 leads an hour, so an unnarrowed search would bury the alert inbox within the hour.
    """
    normalized = normalize_criteria(criteria)
    return any(key in normalized for key in _NARROWING_KEYS)
