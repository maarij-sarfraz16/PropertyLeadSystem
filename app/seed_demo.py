"""Seed demo leads from the bundled fixtures WITHOUT calling an LLM.

Useful when you want dashboard data with no API key and no network. It runs the *real*
ingest pipeline with a stubbed extractor, so the rows it writes are identical in shape to
scanned rows — dedup keys, scoring and URL validation all apply.

    python -m app.db.init_db     # once
    python -m app.seed_demo

Note: fixture listing URLs point at example.com and are not real advertisements. This is demo
data, not a substitute for the automatic scanner, which produces live Zameen leads with
working links. Remove demo rows again with `python -m app.db.cleanup --demo --apply`.
"""
from __future__ import annotations

from rich.console import Console

from app.extraction.base import Extractor
from app.extraction.schema import ExtractedLead, Intent, SellerType
from app.extraction.service import ExtractionService
from app.logging_config import configure_logging
from app.pipeline.ingest import run_scan_cycle

console = Console()

# Hand-written extraction per fixture post, keyed by a distinctive phrase in its text. This is
# the shape a model would return; stubbing it keeps the seeder deterministic and free.
_BY_PHRASE: list[tuple[str, ExtractedLead]] = [
    (
        "DHA Phase 5",
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
            description="10 marla brand new double-unit house for sale, direct owner.",
            confidence=0.95,
        ),
    ),
    (
        "Bahria Town",
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.sell,
            location_text="Bahria Town, Lahore",
            price=9_500_000,
            currency="PKR",
            area_value=5,
            area_unit="marla",
            seller_type=SellerType.agent,
            contact_phone="0321 9876543",
            contact_name="Ali",
            description="5 marla residential plot in Bahria Town, sector C.",
            confidence=0.9,
        ),
    ),
    (
        "Johar Town",
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.rent,
            location_text="Johar Town, Lahore",
            price=65_000,
            currency="PKR",
            bedrooms=3,
            seller_type=SellerType.owner,
            contact_phone="042-35551234",
            description="Upper portion 3 bed for rent near Emporium, family only.",
            confidence=0.88,
        ),
    ),
    (
        "Gulberg",
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.wanted,
            location_text="Gulberg, Lahore",
            price=250_000,
            currency="PKR",
            area_value=1,
            area_unit="kanal",
            seller_type=SellerType.unknown,
            contact_phone="0345-1122334",
            description="Wanted: 1 kanal house on rent in Gulberg for a family.",
            confidence=0.8,
        ),
    ),
    (
        "DHA Phase 3",
        ExtractedLead(
            is_property_listing=True,
            intent=Intent.sell,
            location_text="DHA Phase 3, Lahore",
            price=30_000_000,
            currency="PKR",
            area_value=2,
            area_unit="marla",
            seller_type=SellerType.agent,
            contact_phone="0333-4455667",
            contact_name="Malik Estate",
            description="Ground floor commercial shop for sale in DHA Phase 3.",
            confidence=0.9,
        ),
    ),
]


class _FixtureExtractor(Extractor):
    """Returns the canned extraction for a fixture post; rejects the blog post."""

    def extract(self, text: str) -> ExtractedLead:
        for phrase, extracted in _BY_PHRASE:
            if phrase.lower() in (text or "").lower():
                return extracted
        # zm-1006 is a blog post, not a listing — the pipeline should filter it out.
        return ExtractedLead(is_property_listing=False, confidence=0.9)


def main() -> None:
    configure_logging()
    result = run_scan_cycle(
        "zameen",
        use_fixtures=True,
        limit=50,
        extraction=ExtractionService(_FixtureExtractor()),
    )
    console.print(
        f"[green]{result.new_count}[/green] demo lead(s) written "
        f"({result.duplicates} duplicate, {result.skipped_seen} already seen, "
        f"{result.not_listings} not listings). Open the dashboard or GET /api/leads."
    )


if __name__ == "__main__":
    main()
