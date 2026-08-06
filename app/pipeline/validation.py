"""Lead completeness validation.

Applied once, at ingest, after extraction but before a lead is persisted. The URL and photo
rules already live elsewhere (`app.pipeline.urls`, `app.pipeline.photos`) because they are
repair/reject rules enforced at the source boundary; this module is the higher-level check
that a *lead*, taken as a whole, is something worth showing an agent.

Two outcomes, not three:
- Missing everything that makes a listing identifiable (title, price, location) -> the row
  carries no usable information, so it is dropped rather than stored as a blank card.
- Missing some but not all required fields -> stored, but flagged (`status="incomplete"`) so
  it is visibly distinct from a reviewed lead instead of silently passing for complete data.

A missing photo never fails validation: the source itself may genuinely have none, and that is
a fact about the listing, not a defect in the pipeline (see `app.pipeline.photos`).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.extraction.schema import ExtractedLead
from app.sources.base import RawPostData

# Fields whose *joint* absence means the row has no identifiable content and should not be
# stored at all — a lead with none of these is not a lead, it is noise.
_CORE_FIELDS = ("title", "price", "location")


@dataclass(frozen=True)
class ValidationResult:
    missing: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        """True when none of the core identifying fields are present — reject outright."""
        return set(_CORE_FIELDS).issubset(self.missing)

    @property
    def is_complete(self) -> bool:
        return not self.missing


def validate_lead(post: RawPostData, extracted: ExtractedLead) -> ValidationResult:
    """Check the fields a dashboard card needs to be honest, not broken.

    `title` falls back to the source post's own title, matching what `lead_title` in
    `app.serializers` would ultimately render — a post with a source-provided title is not
    "missing a title" just because the extractor did not restate it.
    """
    missing: list[str] = []

    if not (post.title or extracted.description):
        missing.append("title")
    if not extracted.price:
        missing.append("price")
    if not extracted.location_text:
        missing.append("location")
    if not post.url:
        missing.append("listing_url")
    if not extracted.description:
        missing.append("description")

    return ValidationResult(missing=tuple(missing))
