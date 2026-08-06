"""Manual scan CLI — a diagnostic tool, not the way leads normally arrive.

Automation is the default path: the background worker starts with the API and scans
continuously (see `app.worker.scanner`). This command exists to run a single cycle on demand
when debugging a source, verifying credentials, or inspecting extraction output.

    python -m app.scan --source zameen                 # one live cycle, writes to DB
    python -m app.scan --source zameen --fixtures      # offline sample
    python -m app.scan --source zameen --dry-run       # fetch + extract, print, no DB write
    python -m app.scan --watch                         # run the worker loop in the foreground

It calls the same `run_scan_cycle` the worker calls, so what you see here is exactly what
automation does.
"""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from app.extraction.service import get_extraction_service
from app.logging_config import configure_logging
from app.pipeline.ingest import UnknownSourceError, build_adapter, run_scan_cycle

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def scan(
    source: str = typer.Option("zameen", help="Source name, e.g. zameen"),
    limit: int = typer.Option(25, help="Max listings to fetch this cycle"),
    fixtures: bool = typer.Option(False, help="Use the bundled offline sample (no network)"),
    dry_run: bool = typer.Option(False, help="Fetch and extract only; do not write to DB"),
    watch: bool = typer.Option(False, help="Run the background worker loop in the foreground"),
) -> None:
    configure_logging()

    if watch:
        _watch()
        return

    if dry_run:
        _dry_run(source, limit, fixtures)
        return

    try:
        result = run_scan_cycle(source, use_fixtures=fixtures, limit=limit)
    except UnknownSourceError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(
        f"\nfetched [bold]{result.fetched}[/bold] | "
        f"new [green]{result.new_count}[/green] | "
        f"duplicates [yellow]{result.duplicates}[/yellow] | "
        f"already seen [dim]{result.skipped_seen}[/dim] | "
        f"not listings [dim]{result.not_listings}[/dim] | "
        f"invalid [red]{result.invalid}[/red]"
    )
    if result.new_leads:
        _print_leads(result.new_leads)


def _dry_run(source: str, limit: int, fixtures: bool) -> None:
    """Fetch and extract without touching the database. Useful for checking listing URLs."""
    try:
        adapter = build_adapter(source, fixtures)
    except UnknownSourceError as exc:
        raise typer.BadParameter(str(exc)) from exc

    posts = adapter.fetch(limit=limit)
    extraction = get_extraction_service()
    console.print(f"[bold]{len(posts)}[/bold] listings fetched from '{source}'. Extracting...")

    table = Table(title="Extracted leads (dry run - nothing written)")
    columns = (
        "external_id", "listing?", "intent", "location",
        "price", "beds", "seller", "phone", "url",
    )
    for column in columns:
        table.add_column(column, overflow="fold")

    for post in posts:
        extracted = extraction.extract(post.text, post.facts)
        table.add_row(
            post.external_id,
            "yes" if extracted.is_property_listing else "no",
            extracted.intent.value,
            extracted.location_text or "-",
            f"{extracted.price:,.0f}" if extracted.price else "-",
            str(extracted.bedrooms) if extracted.bedrooms is not None else "-",
            extracted.seller_type.value,
            extracted.contact_phone or "-",
            post.url or "[red]MISSING[/red]",
        )

    console.print(table)


def _print_leads(leads: list[dict]) -> None:
    table = Table(title="New leads")
    for column in ("title", "location", "price", "beds", "seller", "score", "listing url"):
        table.add_column(column, overflow="fold")
    for lead in leads:
        table.add_row(
            str(lead.get("title", ""))[:50],
            str(lead.get("location", "-")),
            f"{lead.get('price', 0):,.0f}",
            str(lead.get("bedrooms", 0)),
            str(lead.get("sellerType", "-")),
            str(lead.get("score", 0)),
            lead.get("originalListingUrl") or "[red]MISSING[/red]",
        )
    console.print(table)


def _watch() -> None:
    """Run the same worker the API hosts, standalone.

    Useful for running scanning as its own process (a separate container or systemd unit)
    while the API stays stateless — set SCAN_ENABLED=false on the API in that deployment.
    """
    from app.worker.scanner import get_worker

    async def main() -> None:
        worker = get_worker()
        await worker.start()
        console.print("[green]Scan worker running.[/green] Press Ctrl+C to stop.")
        try:
            await asyncio.Event().wait()
        finally:
            await worker.stop()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Worker stopped.[/dim]")


if __name__ == "__main__":
    app()
