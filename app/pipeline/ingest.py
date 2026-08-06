"""One scan cycle, end to end.

    fetch -> new-since-watermark -> already-ingested filter -> AI extraction
          -> dedup -> persist -> emit realtime events

This module is deliberately synchronous and framework-free: the background worker runs it in
a thread, and the CLI calls it directly, so both paths execute the exact same pipeline. There
is no second implementation to drift.

Ordering matters for cost. The two cheap filters (watermark, already-ingested) run *before*
extraction, so at a 30-second cadence — where a search page is almost entirely listings seen
last cycle — a typical cycle makes zero LLM calls.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models import Lead, LeadSource, Photo, RawPost, ScanState, Source
from app.db.session import session_scope
from app.extraction.schema import ExtractedLead
from app.extraction.service import ExtractionService, get_extraction_service
from app.logging_config import get_logger
from app.pipeline.classify import derive_city, derive_property_type
from app.pipeline.dedup import build_dedup_key, existing_external_ids, find_duplicate_lead
from app.pipeline.normalize import normalize_phone
from app.pipeline.scoring import score_lead
from app.pipeline.urls import clean_listing_url
from app.pipeline.validation import ValidationResult, validate_lead
from app.serializers import lead_summary
from app.sources.base import RawPostData, SourceAdapter
from app.sources.zameen import ZameenAdapter

log = get_logger(__name__)

# Source registry. Adding a source = one entry here plus an adapter.
ADAPTERS: dict[str, type[SourceAdapter]] = {"zameen": ZameenAdapter}


@dataclass
class ScanResult:
    """Outcome of one cycle. Fed to logs, the realtime stream, and the scan status endpoint."""

    source: str
    fetched: int = 0
    considered: int = 0
    skipped_seen: int = 0
    duplicates: int = 0
    not_listings: int = 0
    invalid: int = 0
    new_leads: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def new_count(self) -> int:
        return len(self.new_leads)


class UnknownSourceError(ValueError):
    pass


def build_adapter(name: str, use_fixtures: bool = False) -> SourceAdapter:
    """Instantiate a source adapter, applying its DB-held config when available."""
    if name not in ADAPTERS:
        raise UnknownSourceError(f"unknown source '{name}'. Known: {sorted(ADAPTERS)}")
    config: dict = {}
    if not use_fixtures:
        with session_scope() as session:
            source = session.scalar(select(Source).where(Source.name == name))
            config = dict(source.config or {}) if source is not None else {}
    return ADAPTERS[name](config=config, use_fixtures=use_fixtures)


def run_scan_cycle(
    source_name: str,
    *,
    use_fixtures: bool = False,
    limit: int | None = None,
    extraction: ExtractionService | None = None,
    adapter: SourceAdapter | None = None,
) -> ScanResult:
    """Run one full cycle for one source and return what changed.

    Raises on fetch failure so the caller can apply backoff; per-listing failures are logged
    and skipped, because one malformed ad must not abort the cycle.
    """
    settings = get_settings()
    result = ScanResult(source=source_name)
    adapter = adapter or build_adapter(source_name, use_fixtures)
    extraction = extraction or get_extraction_service()

    log.info("scan.started", extra={"source": source_name, "mode": getattr(adapter, "mode", "n/a")})

    posts = adapter.fetch(limit=limit or settings.scan_page_size)
    result.fetched = len(posts)

    with session_scope() as session:
        source = _get_or_create_source(session, source_name)
        state = _get_or_create_state(session, source.id)
        watermark = _as_utc(state.last_posted_at)

        candidates = _select_candidates(posts, watermark, session, source.id, result, settings)
        log.info(
            "scan.fetched",
            extra={
                "source": source_name,
                "fetched": result.fetched,
                "new_candidates": len(candidates),
                "skipped_seen": result.skipped_seen,
                "watermark": watermark.isoformat() if watermark else None,
            },
        )

        newest_posted = watermark
        for post in candidates:
            try:
                summary = _ingest_post(session, source, post, extraction, result, source_name)
            except Exception as exc:
                # Roll back just this listing; the cycle continues with the next one.
                session.rollback()
                log.exception(
                    "listing.failed",
                    extra={
                        "source": source_name,
                        "external_id": post.external_id,
                        "error": str(exc),
                    },
                )
                continue

            if summary is not None:
                result.new_leads.append(summary)
            if post.posted_at and (newest_posted is None or post.posted_at > newest_posted):
                newest_posted = post.posted_at

        _update_state(state, newest_posted, candidates, result)

    log.info(
        "scan.completed",
        extra={
            "source": source_name,
            "fetched": result.fetched,
            "new_leads": result.new_count,
            "duplicates": result.duplicates,
            "skipped_seen": result.skipped_seen,
            "not_listings": result.not_listings,
            "invalid": result.invalid,
        },
    )
    return result


# -- cycle stages ------------------------------------------------------------
def _select_candidates(
    posts: list[RawPostData],
    watermark: dt.datetime | None,
    session: Session,
    source_id: str,
    result: ScanResult,
    settings,
) -> list[RawPostData]:
    """Narrow a fetched page down to listings genuinely worth processing."""
    if watermark is not None:
        # Only listings published after the last successful cycle.
        fresh = [post for post in posts if post.posted_at is None or post.posted_at > watermark]
    else:
        # First ever run: seed the watermark from a bounded slice instead of ingesting the
        # entire first page, so an empty database does not trigger a burst of LLM calls.
        fresh = posts[: settings.scan_backfill_limit]

    seen = existing_external_ids(session, source_id, [post.external_id for post in fresh])
    candidates = [post for post in fresh if post.external_id not in seen]
    result.skipped_seen = len(posts) - len(candidates)

    for post in fresh:
        if post.external_id in seen:
            log.debug(
                "listing.duplicate",
                extra={"reason": "already_ingested", "external_id": post.external_id},
            )

    # Oldest first, so the watermark advances monotonically even on a partial cycle.
    candidates.sort(key=lambda post: post.posted_at or dt.datetime.min.replace(tzinfo=dt.UTC))
    capped = candidates[: settings.scan_max_new_per_cycle]
    if len(candidates) > len(capped):
        log.info(
            "scan.capped",
            extra={"available": len(candidates), "processed": len(capped),
                   "reason": "scan_max_new_per_cycle"},
        )
    result.considered = len(capped)
    return capped


def _ingest_post(
    session: Session,
    source: Source,
    post: RawPostData,
    extraction: ExtractionService,
    result: ScanResult,
    source_name: str,
) -> dict[str, Any] | None:
    """Extract, dedup and persist one listing. Returns the lead payload if it is new."""
    log.info(
        "listing.new",
        extra={
            "source": source_name,
            "external_id": post.external_id,
            "url": post.url,
            "posted_at": post.posted_at.isoformat() if post.posted_at else None,
        },
    )

    raw = _upsert_raw_post(session, source.id, post)
    extracted = extraction.extract(post.text, post.facts)

    if not extracted.is_property_listing:
        result.not_listings += 1
        log.info(
            "listing.not_a_listing",
            extra={"source": source_name, "external_id": post.external_id},
        )
        session.commit()
        return None

    extracted = extracted.model_copy(
        update={"contact_phone": normalize_phone(extracted.contact_phone)}
    )

    validation = validate_lead(post, extracted)
    if validation.is_empty:
        # No title, no price, no location: nothing here identifies a property. Storing it
        # would just be a blank card in the dashboard, so it is dropped rather than flagged.
        result.invalid += 1
        log.info(
            "listing.invalid",
            extra={"source": source_name, "external_id": post.external_id,
                   "missing": validation.missing},
        )
        session.commit()
        return None

    dedup_key = build_dedup_key(source_name, post.external_id, extracted)

    duplicate = find_duplicate_lead(session, dedup_key)
    if duplicate is not None:
        _attach_and_touch(session, duplicate, raw)
        result.duplicates += 1
        log.info(
            "listing.duplicate",
            extra={
                "reason": "content_match",
                "source": source_name,
                "external_id": post.external_id,
                "lead_id": duplicate.id,
            },
        )
        return None

    lead = _create_lead(session, post, extracted, dedup_key, validation)
    try:
        session.flush()
        session.add(LeadSource(lead_id=lead.id, raw_post_id=raw.id))
        for url in post.photo_urls:
            session.add(Photo(lead_id=lead.id, url=url))
        session.commit()
    except IntegrityError:
        # A concurrent cycle won the race on the UNIQUE dedup_key. That is the constraint
        # doing its job — treat it as a duplicate, not an error.
        session.rollback()
        result.duplicates += 1
        log.info(
            "listing.duplicate",
            extra={"reason": "unique_constraint", "source": source_name,
                   "external_id": post.external_id},
        )
        return None

    log.info(
        "lead.saved",
        extra={
            "lead_id": lead.id,
            "source": source_name,
            "external_id": post.external_id,
            "listing_url": lead.listing_url,
            "price": lead.price,
            "score": lead.score,
        },
    )
    return _summarize(session, lead.id)


def _upsert_raw_post(session: Session, source_id: str, post: RawPostData) -> RawPost:
    """Store the post verbatim, preserving the scraped listing URL exactly as returned."""
    raw = session.scalar(
        select(RawPost).where(
            RawPost.source_id == source_id, RawPost.external_id == post.external_id
        )
    )
    if raw is not None:
        return raw
    raw = RawPost(
        source_id=source_id,
        external_id=post.external_id,
        url=post.url,
        title=post.title,
        text=post.text,
        posted_at=post.posted_at,
        raw_json=post.raw_json,
    )
    session.add(raw)
    session.flush()
    return raw


def _create_lead(
    session: Session,
    post: RawPostData,
    extracted: ExtractedLead,
    dedup_key: str,
    validation: ValidationResult,
) -> Lead:
    lead = Lead(
        # Validated at the boundary: a lead never carries a link that is not an advertisement.
        listing_url=clean_listing_url(post.url),
        title=post.title,
        dedup_key=dedup_key,
        # Missing a required field (but not empty outright) still gets stored — an agent may
        # be able to fill the gap from the listing itself — but it is flagged rather than
        # presented as a fully reviewed, complete lead.
        status="incomplete" if not validation.is_complete else "new",
        intent=extracted.intent.value,
        location_text=extracted.location_text,
        # Derived at write time so the leads list can filter and paginate on them in SQL.
        city=derive_city(extracted.location_text),
        property_type=derive_property_type(
            post.raw_json,
            (post.title, extracted.description, post.text),
        ),
        latitude=post.facts.get("latitude"),
        longitude=post.facts.get("longitude"),
        price=extracted.price,
        currency=extracted.currency,
        area_value=extracted.area_value,
        area_unit=extracted.area_unit,
        bedrooms=extracted.bedrooms,
        seller_type=extracted.seller_type.value,
        contact_phone=extracted.contact_phone,
        contact_name=extracted.contact_name,
        description=extracted.description,
        extraction_confidence=extracted.confidence,
        score=score_lead(extracted, post.facts),
    )
    session.add(lead)
    return lead


def _attach_and_touch(session: Session, lead: Lead, raw: RawPost) -> None:
    """Link a duplicate ad to the lead it duplicates and refresh its last-seen time."""
    already_linked = session.scalar(
        select(LeadSource).where(
            LeadSource.lead_id == lead.id, LeadSource.raw_post_id == raw.id
        )
    )
    if already_linked is None:
        session.add(LeadSource(lead_id=lead.id, raw_post_id=raw.id))
    lead.last_seen_at = dt.datetime.now(dt.UTC)
    # A repost with a working link repairs a lead whose original link was missing.
    if not lead.listing_url:
        lead.listing_url = clean_listing_url(raw.url)
    session.commit()


def _summarize(session: Session, lead_id: str) -> dict[str, Any]:
    """Re-read the lead with relationships loaded, in the dashboard's row shape."""
    lead = session.scalar(
        select(Lead)
        .where(Lead.id == lead_id)
        .options(
            selectinload(Lead.photos),
            selectinload(Lead.sources).selectinload(LeadSource.raw_post).selectinload(RawPost.source),
        )
    )
    return lead_summary(lead)


# -- state -------------------------------------------------------------------
def _get_or_create_source(session: Session, name: str) -> Source:
    source = session.scalar(select(Source).where(Source.name == name))
    if source is None:
        # Self-healing: the worker must not require a manual seeding step to start.
        source = Source(name=name, type="portal", config={}, enabled=True)
        session.add(source)
        session.flush()
        log.info("source.created", extra={"source": name})
    return source


def _get_or_create_state(session: Session, source_id: str) -> ScanState:
    state = session.get(ScanState, source_id)
    if state is None:
        state = ScanState(source_id=source_id)
        session.add(state)
        session.flush()
    return state


def _update_state(
    state: ScanState,
    newest_posted: dt.datetime | None,
    candidates: list[RawPostData],
    result: ScanResult,
) -> None:
    now = dt.datetime.now(dt.UTC)
    state.last_run_at = now
    state.last_success_at = now
    state.last_error = None
    state.consecutive_errors = 0
    state.total_runs = (state.total_runs or 0) + 1
    state.total_new_leads = (state.total_new_leads or 0) + result.new_count
    # Advanced only from a real publish time. Stamping it with the run clock instead would let
    # an offline/fixture cycle push the watermark past live listings that were published
    # moments earlier, silently skipping them on the next real scan. When a source reports no
    # publish time the watermark simply stays put and the already-ingested filter carries the
    # load — slightly more work per cycle, but it can never skip a listing.
    if newest_posted is not None:
        state.last_posted_at = newest_posted
    if candidates:
        state.last_external_id = candidates[-1].external_id


def record_scan_error(source_name: str, error: str) -> None:
    """Persist a failed cycle so the dashboard can show the source as degraded."""
    try:
        with session_scope() as session:
            source = session.scalar(select(Source).where(Source.name == source_name))
            if source is None:
                return
            state = _get_or_create_state(session, source.id)
            state.last_run_at = dt.datetime.now(dt.UTC)
            state.last_error = error[:500]
            state.consecutive_errors = (state.consecutive_errors or 0) + 1
            state.total_runs = (state.total_runs or 0) + 1
    except Exception:  # pragma: no cover - error path of an error path
        log.exception("scan.error_state_write_failed", extra={"source": source_name})


def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value
