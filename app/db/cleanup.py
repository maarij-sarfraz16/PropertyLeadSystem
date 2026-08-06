"""Maintenance: remove leads that cannot be opened.

Why this exists: before the pipeline validated listing URLs, demo/fixture data was written
with hand-written zameen.com paths for advertisements that never existed. Those rows pass a
format check but return "Ad not found" when clicked — the exact defect the URL validation now
prevents for new leads. Existing rows still need clearing out once.

    python -m app.db.cleanup --demo         # drop fixture-derived rows (external ids like zm-*)
    python -m app.db.cleanup --dead-links   # HTTP-check every lead URL, drop the dead ones
    python -m app.db.cleanup --demo --apply # actually delete (default is a dry run)

Defaults to a dry run: it prints what it would delete and changes nothing.
"""
from __future__ import annotations

import httpx
import typer
from rich.console import Console
from sqlalchemy import delete, select

from app.db.models import Lead, LeadSource, Photo, RawPost
from app.db.session import session_scope
from app.logging_config import configure_logging, get_logger

app = typer.Typer(add_completion=False)
console = Console()
log = get_logger(__name__)

# External-id prefixes used by the bundled fixtures.
_FIXTURE_PREFIXES = ("zm-",)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}


@app.command()
def cleanup(
    demo: bool = typer.Option(False, help="Delete leads derived from bundled fixtures."),
    dead_links: bool = typer.Option(False, help="Delete leads whose listing URL does not resolve."),
    apply: bool = typer.Option(False, help="Perform the deletion. Without this it is a dry run."),
) -> None:
    configure_logging()
    if not demo and not dead_links:
        raise typer.BadParameter("pass --demo and/or --dead-links")

    doomed: set[str] = set()
    if demo:
        doomed |= _fixture_lead_ids()
    if dead_links:
        doomed |= _dead_link_lead_ids(skip=doomed)

    if not doomed:
        console.print("[green]Nothing to clean.[/green]")
        return

    if not apply:
        console.print(
            f"[yellow]Dry run:[/yellow] {len(doomed)} lead(s) would be deleted. "
            f"Re-run with --apply to delete them."
        )
        return

    _delete_leads(doomed)
    console.print(f"[green]{len(doomed)}[/green] lead(s) deleted.")


def _fixture_lead_ids() -> set[str]:
    """Leads whose only source post came from a fixture."""
    with session_scope() as session:
        rows = session.execute(
            select(Lead.id, RawPost.external_id, RawPost.url)
            .join(LeadSource, LeadSource.lead_id == Lead.id)
            .join(RawPost, RawPost.id == LeadSource.raw_post_id)
        ).all()

    ids = {
        lead_id
        for lead_id, external_id, _ in rows
        if external_id and external_id.startswith(_FIXTURE_PREFIXES)
    }
    console.print(f"fixture-derived leads: [yellow]{len(ids)}[/yellow]")
    return ids


def _dead_link_lead_ids(skip: set[str]) -> set[str]:
    """Leads whose stored URL does not resolve to a live advertisement."""
    with session_scope() as session:
        rows = session.execute(
            select(Lead.id, Lead.listing_url, RawPost.url)
            .join(LeadSource, LeadSource.lead_id == Lead.id, isouter=True)
            .join(RawPost, RawPost.id == LeadSource.raw_post_id, isouter=True)
        ).all()

    checked: dict[str, bool] = {}
    dead: set[str] = set()
    with httpx.Client(timeout=20, headers=_HEADERS, follow_redirects=True) as client:
        for lead_id, listing_url, raw_url in rows:
            if lead_id in skip or lead_id in dead:
                continue
            url = listing_url or raw_url
            if not url:
                dead.add(lead_id)
                continue
            if url not in checked:
                checked[url] = _is_live(client, url)
            if not checked[url]:
                dead.add(lead_id)
                console.print(f"  dead: {url[:90]}")

    console.print(f"dead-link leads: [yellow]{len(dead)}[/yellow]")
    return dead


def _is_live(client: httpx.Client, url: str) -> bool:
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    # Zameen answers a removed ad with 200 and an "Ad not found" body, so status alone lies.
    return "ad not found" not in response.text[:20000].lower()


def _delete_leads(lead_ids: set[str]) -> None:
    """Delete leads and their dependent rows. Raw posts are kept as the ingest audit trail."""
    with session_scope() as session:
        ids = list(lead_ids)
        session.execute(delete(Photo).where(Photo.lead_id.in_(ids)))
        session.execute(delete(LeadSource).where(LeadSource.lead_id.in_(ids)))
        session.execute(delete(Lead).where(Lead.id.in_(ids)))
    log.info("cleanup.deleted", extra={"leads": len(lead_ids)})


if __name__ == "__main__":
    app()
