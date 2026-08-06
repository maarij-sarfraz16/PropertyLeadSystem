"""Lead scoring.

A transparent, additive score in 0-100. Every lead needs one at ingest so the dashboard can
sort and triage the moment a listing arrives — waiting for the Phase 2 model would leave the
new realtime feed unsorted.

The weights encode what makes a lead actionable for an agent: reachable seller, direct owner
(no agency commission in the way), complete data, and a fresh posting.
"""
from __future__ import annotations

from typing import Any

from app.extraction.schema import ExtractedLead, Intent, SellerType

_BASE = 50.0


def score_lead(extracted: ExtractedLead, facts: dict[str, Any] | None = None) -> float:
    """Return a 0-100 actionability score."""
    facts = facts or {}
    score = _BASE

    # A lead you cannot call is barely a lead.
    if extracted.contact_phone:
        score += 15
    if extracted.contact_name:
        score += 3

    # Owner listings convert better than agency inventory already on the market.
    if extracted.seller_type is SellerType.owner:
        score += 12
    elif extracted.seller_type is SellerType.agent:
        score += 2

    # A clear transaction intent beats an ambiguous post.
    if extracted.intent in (Intent.sell, Intent.rent):
        score += 6
    elif extracted.intent is Intent.wanted:
        score += 4

    # Completeness: a lead missing price or size needs manual research before outreach.
    if extracted.price:
        score += 6
    if extracted.area_value:
        score += 3
    if extracted.bedrooms is not None:
        score += 2

    # Trust the score no further than the extraction behind it.
    score += (extracted.confidence - 0.5) * 10

    # Portal-verified ads are less likely to be stale or fake.
    if facts.get("property_type"):
        score += 2

    return round(max(0.0, min(100.0, score)), 1)
