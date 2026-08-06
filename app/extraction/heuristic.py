"""Rule-based extractor used as the LLM's safety net.

The scanner must keep producing leads when Gemini is rate-limited, out of quota, or
unreachable — otherwise a provider outage silently stops the whole product. This extractor
covers the same `ExtractedLead` contract using deterministic rules over the ad text.

It is intentionally conservative: it reports a low confidence, so downstream consumers can
tell a rule-derived lead from a model-derived one.
"""
from __future__ import annotations

import re

from app.extraction.base import Extractor
from app.extraction.schema import ExtractedLead, Intent, SellerType

# "4.75 crore", "95 lakh", "65,000", "1.2 million"
_PRICE_RE = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore|karor|lakh|lac|million|thousand|k\b)?",
    re.IGNORECASE,
)
_MULTIPLIERS = {
    "crore": 10_000_000,
    "karor": 10_000_000,
    "lakh": 100_000,
    "lac": 100_000,
    "million": 1_000_000,
    "thousand": 1_000,
    "k": 1_000,
}
_AREA_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>marla|kanal|sq\.?\s*ft|sqft|sq\.?\s*yd|sqyd)",
    re.IGNORECASE,
)
_BEDROOM_RE = re.compile(r"(?P<value>\d+)\s*(?:bed|bhk|bedroom)", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:\+92|0)\s*\d{2,3}[\s-]?\d{7}")

_RENT_HINTS = ("for rent", "on rent", "rental", "per month", "monthly")
_WANTED_HINTS = ("wanted", "required", "looking for", "need a", "need ")
_OWNER_HINTS = ("direct owner", "owner", "no agents", "no dealers")
_AGENT_HINTS = ("agent", "dealer", "estate", "realtor", "properties", "marketing")
# Content that is not an advertisement at all.
_NON_LISTING_HINTS = ("blog", "guide to", "read more", "top investment areas", "news")


class HeuristicExtractor(Extractor):
    """Deterministic, offline extraction. No network, no cost, no quota."""

    def extract(self, text: str) -> ExtractedLead:
        body = text or ""
        lower = body.lower()

        if not body.strip() or any(hint in lower for hint in _NON_LISTING_HINTS):
            return ExtractedLead(is_property_listing=False, confidence=0.3)

        return ExtractedLead(
            is_property_listing=True,
            intent=_intent(lower),
            location_text=_location(body),
            price=_price(body, lower),
            currency="PKR",
            area_value=_area(body)[0],
            area_unit=_area(body)[1],
            bedrooms=_bedrooms(body),
            seller_type=_seller_type(lower),
            contact_phone=_phone(body),
            contact_name=None,
            description=_summary(body),
            # Deliberately low: this is a rules pass, not a model judgement.
            confidence=0.45,
        )


def _intent(lower: str) -> Intent:
    if any(hint in lower for hint in _WANTED_HINTS):
        return Intent.wanted
    if any(hint in lower for hint in _RENT_HINTS):
        return Intent.rent
    if "for sale" in lower or "sale" in lower:
        return Intent.sell
    return Intent.unknown


def _seller_type(lower: str) -> SellerType:
    # "no agents please" is an owner signal even though it contains "agent", so owner wins.
    if any(hint in lower for hint in _OWNER_HINTS):
        return SellerType.owner
    if any(hint in lower for hint in _AGENT_HINTS):
        return SellerType.agent
    return SellerType.unknown


def _price(body: str, lower: str) -> float | None:
    """Largest plausible money figure in the text, scaled by its unit word."""
    best: float | None = None
    for match in _PRICE_RE.finditer(body):
        unit = (match.group("unit") or "").lower().strip()
        try:
            value = float(match.group("value").replace(",", ""))
        except ValueError:
            continue
        if not unit and value < 10_000:
            continue  # bare small numbers are bedrooms/marla, not prices
        scaled = value * _MULTIPLIERS.get(unit, 1)
        if scaled < 1_000:
            continue
        if best is None or scaled > best:
            best = scaled
    return best


def _area(body: str) -> tuple[float | None, str | None]:
    match = _AREA_RE.search(body)
    if not match:
        return None, None
    unit = re.sub(r"[\s.]", "", match.group("unit").lower())
    unit = {"sqft": "sqft", "sqyd": "sqyd"}.get(unit, unit)
    try:
        return float(match.group("value")), unit
    except ValueError:
        return None, None


def _bedrooms(body: str) -> int | None:
    match = _BEDROOM_RE.search(body)
    try:
        return int(match.group("value")) if match else None
    except ValueError:
        return None


def _phone(body: str) -> str | None:
    match = _PHONE_RE.search(body)
    return match.group(0) if match else None


def _location(body: str) -> str | None:
    """Prefer the explicit 'Location:' line the source adapters emit."""
    for line in body.splitlines():
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _summary(body: str) -> str:
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first_line[:240]
