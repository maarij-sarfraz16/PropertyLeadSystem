"""Dedup key behaviour."""
from __future__ import annotations

from app.extraction.schema import ExtractedLead, Intent, SellerType
from app.pipeline.dedup import build_dedup_key


def _lead(**overrides) -> ExtractedLead:
    base = dict(
        is_property_listing=True,
        intent=Intent.sell,
        location_text="DHA Phase 5, Lahore",
        price=47_500_000.0,
        currency="PKR",
        area_value=10.0,
        area_unit="marla",
        bedrooms=5,
        seller_type=SellerType.owner,
        contact_phone="+923001234567",
        confidence=0.9,
    )
    base.update(overrides)
    return ExtractedLead(**base)


def test_same_property_reposted_under_new_ad_id_collapses():
    """The core case: an agency reposts the same property, so the ad id changes."""
    first = build_dedup_key("zameen", "111", _lead())
    second = build_dedup_key("zameen", "222", _lead())
    assert first == second


def test_same_property_across_sources_collapses():
    assert build_dedup_key("zameen", "111", _lead()) == build_dedup_key("olx", "999", _lead())


def test_different_price_is_a_different_property():
    assert build_dedup_key("zameen", "111", _lead()) != build_dedup_key(
        "zameen", "111", _lead(price=52_000_000.0)
    )


def test_different_seller_is_a_different_lead():
    assert build_dedup_key("zameen", "111", _lead()) != build_dedup_key(
        "zameen", "111", _lead(contact_phone="+923219876543")
    )


def test_minor_area_differences_still_match():
    """Portals round area conversions differently for the same plot."""
    assert build_dedup_key("zameen", "1", _lead(area_value=10.0)) == build_dedup_key(
        "zameen", "2", _lead(area_value=10.4)
    )


def test_falls_back_to_ad_identity_without_phone_or_price():
    thin = _lead(contact_phone=None, price=None)
    assert build_dedup_key("zameen", "111", thin) != build_dedup_key("zameen", "222", thin)
    # Same ad seen twice still matches itself.
    assert build_dedup_key("zameen", "111", thin) == build_dedup_key("zameen", "111", thin)
