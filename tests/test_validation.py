"""Completeness validation: a lead must carry enough real content to be worth showing."""
from __future__ import annotations

from app.extraction.schema import ExtractedLead
from app.pipeline.validation import validate_lead
from app.sources.base import RawPostData


def _post(**overrides) -> RawPostData:
    defaults = dict(external_id="ext-1", text="some ad text", url="https://www.zameen.com/Property/x.html")
    defaults.update(overrides)
    return RawPostData(**defaults)


def _extracted(**overrides) -> ExtractedLead:
    defaults = dict(is_property_listing=True)
    defaults.update(overrides)
    return ExtractedLead(**defaults)


def test_complete_lead_has_no_missing_fields():
    post = _post(title="3 Bed House in DHA")
    extracted = _extracted(
        location_text="DHA Phase 5, Lahore", price=25_000_000, description="A lovely house."
    )
    result = validate_lead(post, extracted)
    assert result.is_complete
    assert not result.is_empty


def test_missing_price_is_flagged_not_dropped():
    post = _post(title="3 Bed House in DHA")
    extracted = _extracted(location_text="DHA Phase 5, Lahore", description="A lovely house.")
    result = validate_lead(post, extracted)
    assert "price" in result.missing
    assert not result.is_complete
    assert not result.is_empty


def test_missing_title_price_and_location_is_empty():
    post = _post(title=None)
    extracted = _extracted(description=None)
    result = validate_lead(post, extracted)
    assert result.is_empty


def test_title_falls_back_to_extracted_description():
    post = _post(title=None)
    extracted = _extracted(
        location_text="Gulberg, Lahore", price=10_000_000, description="Corner plot near market."
    )
    result = validate_lead(post, extracted)
    assert "title" not in result.missing
