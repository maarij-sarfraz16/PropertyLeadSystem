"""Phase 1a entry point: one-shot scan of a single source.

    python -m app.scan --source zameen --fixtures            # offline sample, needs GEMINI_API_KEY
    python -m app.scan --source zameen --fixtures --dry-run   # extract + print, no DB write
    python -m app.scan --source zameen --limit 50             # live via Apify, writes to DB

Flow: fetch -> Gemini extract -> (write raw_posts + leads) -> print table.
Dedup and scoring arrive in Phase 2; here every genuine listing becomes one lead.
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from app.db.models import Lead, LeadSource, Photo, RawPost, Source
from app.db.session import session_scope
from app.extraction.gemini import GeminiExtractor
from app.extraction.schema import ExtractedLead
from app.pipeline.normalize import normalize_phone
from app.sources.base import RawPostData, SourceAdapter
from app.sources.zameen import ZameenAdapter

app = typer.Typer(add_completion=False)
console = Console()

# Source registry. Adding a source in Phase 2 = one entry here + an adapter.
_ADAPTERS = {"zameen": ZameenAdapter}


def _build_adapter(name: str, use_fixtures: bool) -> SourceAdapter:
    if name not in _ADAPTERS:
        raise typer.BadParameter(f"unknown source '{name}'. Known: {list(_ADAPTERS)}")
    config: dict = {}
    if not use_fixtures:
        with session_scope() as s:
            src = s.scalar(select(Source).where(Source.name == name))
            if src is None:
                raise typer.BadParameter(
                    f"source '{name}' not in DB. Run `python -m app.db.init_db` first, "
                    f"or pass --fixtures for offline runs."
                )
            config = dict(src.config or {})
    return _ADAPTERS[name](config=config, use_fixtures=use_fixtures)


def _persist(source_name: str, post: RawPostData, extracted: ExtractedLead) -> None:
    """Write the raw post, and a canonical lead if it is a genuine listing."""
    with session_scope() as s:
        src = s.scalar(select(Source).where(Source.name == source_name))
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
            return

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
        )
        s.add(lead)
        s.flush()
        s.add(LeadSource(lead_id=lead.id, raw_post_id=raw.id))
        for url in post.photo_urls:
            s.add(Photo(lead_id=lead.id, url=url))


@app.command()
def scan(
    source: str = typer.Option(..., help="Source name, e.g. zameen"),
    limit: int = typer.Option(50, help="Max posts to fetch"),
    fixtures: bool = typer.Option(False, help="Use bundled offline sample (no Apify/network)"),
    dry_run: bool = typer.Option(False, help="Extract and print only; do not write to DB"),
) -> None:
    adapter = _build_adapter(source, fixtures)
    posts = adapter.fetch(limit=limit)
    console.print(f"[bold]{len(posts)}[/bold] posts fetched from '{source}'. Extracting...")

    extractor = GeminiExtractor()
    rows: list[tuple[RawPostData, ExtractedLead]] = []
    for post in posts:
        extracted = extractor.extract(post.text)
        rows.append((post, extracted))
        if not dry_run:
            _persist(source, post, extracted)

    _print_table(rows)
    leads = sum(1 for _, e in rows if e.is_property_listing)
    console.print(
        f"\n[green]{leads}[/green] genuine listings / {len(rows)} posts"
        + ("  [dim](dry-run: nothing written)[/dim]" if dry_run else "  written to DB")
    )


def _print_table(rows: list[tuple[RawPostData, ExtractedLead]]) -> None:
    table = Table(title="Extracted leads")
    for col in ("id", "listing?", "intent", "location", "price", "beds", "seller", "phone", "conf"):
        table.add_column(col, overflow="fold")
    for post, e in rows:
        table.add_row(
            post.external_id,
            "yes" if e.is_property_listing else "no",
            e.intent.value,
            e.location_text or "-",
            f"{e.price:,.0f} {e.currency or ''}".strip() if e.price else "-",
            str(e.bedrooms) if e.bedrooms is not None else "-",
            e.seller_type.value,
            normalize_phone(e.contact_phone) or "-",
            f"{e.confidence:.2f}",
        )
    console.print(table)


if __name__ == "__main__":
    app()
