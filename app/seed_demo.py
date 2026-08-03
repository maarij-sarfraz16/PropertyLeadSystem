"""Seed demo leads WITHOUT calling Gemini.

Use this to populate the dashboard when you don't have a working GEMINI_API_KEY.
It takes the bundled zameen fixtures, applies a hand-written extraction for each
(the same shape Gemini would return), and writes raw_posts + leads to the DB,
including a plausible score so the dashboard charts have data.

    python -m app.db.init_db     # once, creates tables + seeds the 'zameen' source
    python -m app.seed_demo      # populates leads

Then open the dashboard (http://localhost:5173) or GET /api/leads.
"""
from __future__ import annotations

from rich.console import Console
from sqlalchemy import select

from app.db.models import Lead, LeadSource, Photo, RawPost, Source
from app.db.session import session_scope
from app.extraction.schema import ExtractedLead, Intent, SellerType
from app.pipeline.normalize import normalize_phone
from app.sources.zameen import ZameenAdapter

console = Console()

# Hand-written extraction for each fixture post, keyed by external_id.
# (external_id, ExtractedLead, score). score is a stand-in for Phase 2 scoring.
_EXTRACTIONS: dict[str, tuple[ExtractedLead, float]] = {
    "zm-1001": (
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.sell,
            location_text="DHA Phase 5, Lahore",
            price=47_500_000,
            currency="PKR",
            area_value=10,
            area_unit="marla",
            bedrooms=5,
            seller_type=SellerType.owner,
            contact_phone="0300-1234567",
            contact_name=None,
            description="10 marla brand new double-unit house for sale, direct owner.",
            confidence=0.95,
        ),
        96,
    ),
    "zm-1002": (
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.sell,
            location_text="Bahria Town, Lahore",
            price=9_500_000,
            currency="PKR",
            area_value=5,
            area_unit="marla",
            bedrooms=None,
            seller_type=SellerType.agent,
            contact_phone="0321 9876543",
            contact_name="Ali",
            description="5 marla residential plot in Bahria Town, sector C.",
            confidence=0.9,
        ),
        88,
    ),
    "zm-1003": (
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.rent,
            location_text="Johar Town, Lahore",
            price=65_000,
            currency="PKR",
            area_value=None,
            area_unit=None,
            bedrooms=3,
            seller_type=SellerType.owner,
            contact_phone="042-35551234",
            contact_name=None,
            description="Upper portion 3 bed for rent near Emporium, family only.",
            confidence=0.88,
        ),
        82,
    ),
    "zm-1004": (
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.wanted,
            location_text="Gulberg, Lahore",
            price=250_000,
            currency="PKR",
            area_value=1,
            area_unit="kanal",
            bedrooms=None,
            seller_type=SellerType.unknown,
            contact_phone="0345-1122334",
            contact_name=None,
            description="Wanted: 1 kanal house on rent in Gulberg for a family.",
            confidence=0.8,
        ),
        74,
    ),
    "zm-1005": (
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.sell,
            location_text="DHA Phase 3, Lahore",
            price=30_000_000,
            currency="PKR",
            area_value=2,
            area_unit="marla",
            bedrooms=None,
            seller_type=SellerType.agent,
            contact_phone="0333-4455667",
            contact_name="Malik Estate",
            description="Ground floor commercial shop for sale in DHA Phase 3.",
            confidence=0.9,
        ),
        91,
    ),
    # zm-1006 is a blog post, not a listing -> skipped on purpose.
}


def _persist(source_name: str, post, extracted: ExtractedLead, score: float) -> bool:
    """Write raw post + a canonical lead (with score). Returns True if a lead was written."""
    with session_scope() as s:
        src = s.scalar(select(Source).where(Source.name == source_name))
        if src is None:
            raise RuntimeError(
                "source 'zameen' not in DB. Run `python -m app.db.init_db` first."
            )
        raw = s.scalar(
            select(RawPost).where(
                RawPost.source_id == src.id, RawPost.external_id == post.external_id
            )
        )
        if raw is None:
            raw = RawPost(
                source_id=src.id,
                external_id=post.external_id,
                url=post.url,
                text=post.text,
                raw_json=post.raw_json,
            )
            s.add(raw)
            s.flush()

        if not extracted.is_property_listing:
            return False

        # Skip if a lead already links this raw post (idempotent re-runs).
        existing = s.scalar(select(LeadSource).where(LeadSource.raw_post_id == raw.id))
        if existing is not None:
            return False

        lead = Lead(
            intent=extracted.intent.value,
            location_text=extracted.location_text,
            price=extracted.price,
            currency=extracted.currency,
            area_value=extracted.area_value,
            area_unit=extracted.area_unit,
            bedrooms=extracted.bedrooms,
            seller_type=extracted.seller_type.value,
            contact_phone=normalize_phone(extracted.contact_phone),
            contact_name=extracted.contact_name,
            description=extracted.description,
            extraction_confidence=extracted.confidence,
            score=score,
        )
        s.add(lead)
        s.flush()
        s.add(LeadSource(lead_id=lead.id, raw_post_id=raw.id))
        for url in post.photo_urls:
            s.add(Photo(lead_id=lead.id, url=url))
        return True


def main() -> None:
    posts = ZameenAdapter(use_fixtures=True).fetch(limit=50)
    written = 0
    for post in posts:
        entry = _EXTRACTIONS.get(post.external_id)
        if entry is None:
            continue
        extracted, score = entry
        if _persist("zameen", post, extracted, score):
            written += 1
    console.print(
        f"[green]{written}[/green] demo leads written to DB (Gemini bypassed). "
        f"Open the dashboard or GET /api/leads."
    )


if __name__ == "__main__":
    main()
