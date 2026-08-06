"""Extraction service: fallback on failure, and source facts winning over model guesses."""
from __future__ import annotations

import pytest

from app.extraction.base import Extractor
from app.extraction.heuristic import HeuristicExtractor
from app.extraction.schema import ExtractedLead, Intent, SellerType
from app.extraction.service import ExtractionService


class _Boom(Extractor):
    def extract(self, text: str) -> ExtractedLead:
        raise RuntimeError("429 quota exceeded")


class _Stub(Extractor):
    def __init__(self, result: ExtractedLead) -> None:
        self._result = result

    def extract(self, text: str) -> ExtractedLead:
        return self._result


def test_falls_back_to_heuristic_when_the_model_fails():
    """A provider outage must not stop lead production."""
    service = ExtractionService(_Boom())
    result = service.extract(
        "10 marla house for sale in DHA Phase 5. Price 4.75 crore. Owner 0300-1234567."
    )
    assert result.is_property_listing
    assert result.price == 47_500_000
    # Rule-derived leads are marked with a lower confidence than model-derived ones.
    assert result.confidence < 0.6


def test_source_facts_override_model_output():
    model_guess = ExtractedLead(
        is_property_listing=True,
        intent=Intent.unknown,
        price=1.0,
        bedrooms=1,
        location_text="somewhere",
        confidence=0.9,
    )
    result = ExtractionService(_Stub(model_guess)).extract(
        "ad text",
        {
            "price": 240_000_000,
            "bedrooms": 5,
            "location_text": "DHA Phase 6, Lahore",
            "intent": "sell",
        },
    )
    assert result.price == 240_000_000
    assert result.bedrooms == 5
    assert result.location_text == "DHA Phase 6, Lahore"
    assert result.intent is Intent.sell


def test_model_fills_gaps_the_source_leaves():
    model_guess = ExtractedLead(
        is_property_listing=True,
        seller_type=SellerType.owner,
        description="Direct owner sale.",
        confidence=0.9,
    )
    result = ExtractionService(_Stub(model_guess)).extract("ad text", {"price": 500_000})
    assert result.price == 500_000
    assert result.description == "Direct owner sale."


def test_source_does_not_downgrade_a_confident_owner_read():
    """'Direct owner, no agents' beats an agency block attached to the ad."""
    model_guess = ExtractedLead(
        is_property_listing=True, seller_type=SellerType.owner, confidence=0.95
    )
    result = ExtractionService(_Stub(model_guess)).extract("ad", {"seller_type": "agent"})
    assert result.seller_type is SellerType.owner


def test_empty_facts_leave_extraction_untouched():
    model_guess = ExtractedLead(is_property_listing=True, price=99.0, confidence=0.8)
    assert ExtractionService(_Stub(model_guess)).extract("ad", {}).price == 99.0


@pytest.mark.parametrize(
    ("text", "expected_intent", "expected_seller"),
    [
        (
            "10 marla house for sale, direct owner, no agents. 0300-1234567",
            Intent.sell,
            SellerType.owner,
        ),
        (
            "Upper portion 3 bed for rent, 65000 per month. 042-35551234",
            Intent.rent,
            SellerType.unknown,
        ),
        (
            "Wanted 1 kanal house on rent in Gulberg, budget 2.5 lakh",
            Intent.wanted,
            SellerType.unknown,
        ),
        (
            "Shop for sale DHA. Price 3 crore. Dealer: Malik Estate 0333-4455667",
            Intent.sell,
            SellerType.agent,
        ),
    ],
)
def test_heuristic_reads_intent_and_seller(text, expected_intent, expected_seller):
    result = HeuristicExtractor().extract(text)
    assert result.intent is expected_intent
    assert result.seller_type is expected_seller


def test_heuristic_rejects_non_listings():
    result = HeuristicExtractor().extract("Our blog guide to top investment areas in Lahore.")
    assert not result.is_property_listing


def test_heuristic_scales_pakistani_price_units():
    assert HeuristicExtractor().extract("Price 4.75 crore for this plot").price == 47_500_000
    assert HeuristicExtractor().extract("Demand 95 lakh negotiable").price == 9_500_000
