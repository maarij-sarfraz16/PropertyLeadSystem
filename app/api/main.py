"""FastAPI application.

Also the process that owns the background scan worker: the worker is started and stopped by
the app lifespan, so `uvicorn app.api.main:app` is the only command needed to run the whole
system. No separate scheduler process, and no manual `python -m app.scan` step.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api.agents import router as agents_router
from app.api.leads import router as leads_router
from app.api.notifications import router as notifications_router
from app.api.realtime import router as realtime_router
from app.api.saved_searches import router as saved_searches_router
from app.config import get_settings
from app.db.init_db import init_db
from app.db.models import Lead, LeadSource, RawPost, ScanState, Source
from app.db.session import session_scope
from app.logging_config import configure_logging, get_logger
from app.serializers import (
    format_timestamp,
)
from app.serializers import (
    lead_detail as _lead_detail,
)
from app.serializers import (
    lead_summary as _lead_summary,
)
from app.worker.scanner import get_worker

log = get_logger(__name__)

# Re-exported: the serializers moved to app.api.serializers so the worker can share them.
__all__ = ["app", "build_dashboard_payload", "_lead_summary", "_lead_detail"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Bring the schema up to date, then start the scan worker with the API.

    init_db is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, backfill only
    touches un-classified rows, source seed is a no-op when present), so running it on every
    boot is safe and means `uvicorn app.api.main:app` alone syncs the DB — no manual
    `python -m app.db.init_db` step after a schema change.
    """
    configure_logging()
    init_db()
    settings = get_settings()
    worker = get_worker()

    if settings.scan_enabled:
        await worker.start()
    else:
        log.info("worker.disabled", extra={"reason": "SCAN_ENABLED=false"})

    try:
        yield
    finally:
        if settings.scan_enabled:
            await worker.stop()


app = FastAPI(title="PropertyLeadSystem API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(realtime_router)
# Lead browsing (list, facets, detail, status) lives in its own module — see app.api.leads.
app.include_router(leads_router)
# Saved searches turn the leads filters into standing alerts; notifications are their inbox.
app.include_router(saved_searches_router)
app.include_router(notifications_router)
app.include_router(agents_router)

# Serve the built SPA when it exists. Mounting the Vite source directory instead would serve
# an index.html referencing unbuilt module paths.
_DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
if _DASHBOARD_DIST.is_dir():
    app.mount(
        "/dashboard",
        StaticFiles(directory=str(_DASHBOARD_DIST), html=True),
        name="dashboard",
    )


# -- health / ops ------------------------------------------------------------
@app.get("/api/health")
def health():
    """DB reachable and basic queries succeed."""
    try:
        with session_scope() as s:
            _ = s.scalar(select(func.count()).select_from(Source))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return {"ok": True}


@app.get("/api/metrics")
def metrics():
    """Basic counts and last-scraped timestamp to monitor fetching."""
    with session_scope() as s:
        total_leads = s.scalar(select(func.count()).select_from(Lead)) or 0
        total_posts = s.scalar(select(func.count()).select_from(RawPost)) or 0
        total_sources = s.scalar(select(func.count()).select_from(Source)) or 0
        last_post = s.scalar(
            select(RawPost.scraped_at).order_by(RawPost.scraped_at.desc()).limit(1)
        )

    return JSONResponse(
        {
            "leads": int(total_leads),
            "raw_posts": int(total_posts),
            "sources": int(total_sources),
            "last_scraped_at": last_post.isoformat() if last_post is not None else None,
        }
    )


@app.get("/api/scan/status")
def scan_status():
    """Worker state plus per-source watermarks — how you verify automation is alive."""
    with session_scope() as s:
        rows = s.execute(
            select(
                Source.name,
                Source.enabled,
                ScanState.last_posted_at,
                ScanState.last_run_at,
                ScanState.last_success_at,
                ScanState.last_error,
                ScanState.consecutive_errors,
                ScanState.total_runs,
                ScanState.total_new_leads,
            ).join(ScanState, ScanState.source_id == Source.id, isouter=True)
        ).all()

    return {
        "worker": get_worker().status,
        "sources": [
            {
                "name": row[0],
                "enabled": row[1],
                "lastPostedAt": row[2].isoformat() if row[2] else None,
                "lastRunAt": row[3].isoformat() if row[3] else None,
                "lastSuccessAt": row[4].isoformat() if row[4] else None,
                "lastError": row[5],
                "consecutiveErrors": row[6] or 0,
                "totalRuns": row[7] or 0,
                "totalNewLeads": row[8] or 0,
            }
            for row in rows
        ],
    }


# -- dashboard ---------------------------------------------------------------
def build_dashboard_payload(
    *,
    total_leads: int,
    total_posts: int,
    total_sources: int,
    last_post: dt.datetime | None,
    leads: list[dict],
    sources: list[dict],
    new_today: int | None = None,
    scan_status: dict | None = None,
) -> dict:
    """Assemble the dashboard contract from real aggregates.

    Every number here is derived from the rows passed in — nothing is invented. The counters
    below exist only to feed a tile or an insight sentence; the dashboard renders no charts,
    so no aggregate is computed speculatively.
    """
    city_counter: Counter[str] = Counter()
    seller_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    scoring_rows: list[dict] = []
    prices: list[float] = []

    for lead in leads:
        location = str(lead.get("location_text") or "Unknown")
        city = location.split(",")[-1].strip() if "," in location else location
        city_counter[city] += 1
        seller_counter[str(lead.get("seller_type") or "unknown")] += 1
        source_counter[str(lead.get("source_name") or "unknown")] += 1

        price = float(lead.get("price") or 0)
        if price > 0:
            prices.append(price)

        score = int(lead.get("score") or 0)
        scoring_rows.append(
            {
                "id": str(lead.get("id") or "lead"),
                "score": score,
                "label": _score_label(score),
                "city": city,
                "area": location,
            }
        )

    sorted_scoring = sorted(scoring_rows, key=lambda item: item["score"], reverse=True)[:4]
    high_value = sum(1 for row in scoring_rows if row["score"] >= 80)
    avg_price = round(sum(prices) / len(prices)) if prices else 0
    top_source = source_counter.most_common(1)[0][0] if source_counter else "Unknown"
    new_today = new_today if new_today is not None else 0
    worker = (scan_status or {}).get("worker", {})
    active_scans = len(worker.get("sources", [])) if worker.get("running") else 0

    metrics_rows = [
        _metric("Total Leads Found", total_leads, f"+{new_today} today", up=bool(new_today)),
        _metric("New Leads Today", new_today, "live", up=bool(new_today)),
        _metric("High Value Leads", high_value, "score 80+", up=bool(high_value)),
        _metric("Sources Monitored", total_sources, "configured"),
        _metric(
            "Active Scans",
            active_scans,
            "worker running" if active_scans else "worker idle",
            up=bool(active_scans),
            down=not active_scans,
        ),
        {"label": "Posts Ingested", "value": total_posts, "change": "cumulative", "trend": "up"},
        _metric("Average Property Price", avg_price, f"{len(prices)} priced", suffix=" PKR"),
        _metric(
            "Top Performing Source",
            source_counter[top_source] if source_counter else 0,
            "by lead count",
            suffix=f" {top_source}",
            up=True,
        ),
    ]

    lead_rows = [
        {
            "id": str(lead.get("id") or "lead"),
            "image": None,
            "title": str(lead.get("title") or lead.get("description") or "Property listing"),
            "city": str(lead.get("city") or "Unknown"),
            "location": str(lead.get("location_text") or "Unknown"),
            "price": float(lead.get("price") or 0),
            "bedrooms": int(lead.get("bedrooms") or 0),
            "area": f"{lead.get('area_value') or 0} {lead.get('area_unit') or 'sqft'}",
            "sellerType": str(lead.get("seller_type") or "unknown"),
            "score": int(lead.get("score") or 0),
            "source": str(lead.get("source_name") or "Unknown"),
            "status": str(lead.get("status") or "new"),
            "lastSeen": format_timestamp(lead.get("last_seen_at")),
            "originalListingUrl": lead.get("listing_url"),
            "aiSummary": str(lead.get("description") or "New lead discovered."),
        }
        for lead in leads
    ]

    source_status = {entry["name"]: entry for entry in (scan_status or {}).get("sources", [])}
    source_rows = []
    for source in sources:
        name = str(source.get("name") or "Unknown")
        state = source_status.get(name, {})
        healthy = source.get("enabled") is not False and not state.get("lastError")
        source_rows.append(
            {
                "name": name,
                "status": "online" if healthy else "offline",
                "leadsFound": int(state.get("totalNewLeads") or source.get("lead_count") or 0),
                "lastScan": (
                    _relative(state.get("lastSuccessAt"))
                    or format_timestamp(last_post)
                    or "never"
                ),
                "frequency": _frequency_label(worker.get("intervalSeconds")),
                "successRate": _success_rate(state),
            }
        )

    if not source_rows:
        source_rows.append(
            {
                "name": "No sources",
                "status": "offline",
                "leadsFound": 0,
                "lastScan": "never",
                "frequency": "n/a",
                "successRate": 0,
            }
        )

    notifications = [
        {
            "id": f"n-{lead['id']}",
            "title": "High-value lead" if lead["score"] >= 85 else "New lead",
            "body": f"{lead['title'][:70]} - {lead['location']}",
            "level": "success" if lead["score"] >= 85 else "info",
            "time": lead["lastSeen"] or "just now",
        }
        for lead in sorted(lead_rows, key=lambda row: row["score"], reverse=True)[:5]
    ]

    feed = [
        {
            "id": f"f-{lead['id']}",
            "type": "high_score" if lead["score"] >= 85 else "new_listing",
            "message": f"{lead['title'][:70]} ({lead['city']}) - score {lead['score']}",
            "time": lead["lastSeen"] or "just now",
        }
        for lead in lead_rows[:8]
    ]

    return {
        "metrics": metrics_rows,
        "leads": lead_rows,
        "sources": source_rows,
        "notifications": notifications,
        "feed": feed,
        "insights": _insights(
            total_leads,
            total_posts,
            total_sources,
            new_today,
            city_counter,
            seller_counter,
            avg_price,
        ),
        "scoring": sorted_scoring,
        "pipeline": [
            {"label": "Scraping", "status": "active" if worker.get("running") else "idle"},
            {"label": "AI Extraction", "status": "active" if worker.get("running") else "idle"},
            {"label": "Deduplication", "status": "active" if worker.get("running") else "idle"},
            {"label": "Lead Scoring", "status": "active" if worker.get("running") else "idle"},
            {
                "label": "Realtime Push",
                "status": "active" if (worker.get("realtime") or {}).get("subscribers") else "idle",
            },
            {"label": "Agent Assignment", "status": "queued"},
        ],
    }


@app.get("/api/dashboard/overview")
def dashboard_overview():
    """The data contract used by the React dashboard."""
    midnight = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    with session_scope() as s:
        total_leads = s.scalar(select(func.count()).select_from(Lead)) or 0
        total_posts = s.scalar(select(func.count()).select_from(RawPost)) or 0
        total_sources = s.scalar(select(func.count()).select_from(Source)) or 0
        new_today = s.scalar(
            select(func.count()).select_from(Lead).where(Lead.first_seen_at >= midnight)
        ) or 0
        last_post = s.scalar(
            select(RawPost.scraped_at).order_by(RawPost.scraped_at.desc()).limit(1)
        )

        leads = s.execute(
            select(
                Lead.id,
                Lead.location_text,
                Lead.city,
                Lead.price,
                Lead.bedrooms,
                Lead.seller_type,
                Lead.score,
                Lead.status,
                Lead.description,
                Lead.title,
                Lead.listing_url,
                Lead.intent,
                Lead.area_value,
                Lead.area_unit,
                Lead.first_seen_at,
                Lead.last_seen_at,
            )
            .order_by(Lead.first_seen_at.desc())
            .limit(50)
        ).all()

        sources = s.execute(
            select(Source.name, Source.enabled).order_by(Source.name).limit(20)
        ).all()

        # Which portal each of those leads came from. Resolved in one query keyed by lead id
        # rather than assumed — the "top performing source" tile is only meaningful if the
        # attribution is real.
        source_names = dict(
            s.execute(
                select(LeadSource.lead_id, Source.name)
                .join(RawPost, RawPost.id == LeadSource.raw_post_id)
                .join(Source, Source.id == RawPost.source_id)
                .where(LeadSource.lead_id.in_([row.id for row in leads]))
            ).all()
        ) if leads else {}

    lead_rows = [
        {
            "id": row.id,
            "location_text": row.location_text,
            "price": row.price,
            "bedrooms": row.bedrooms,
            "seller_type": row.seller_type,
            "score": row.score,
            "status": row.status,
            "description": row.description,
            "title": row.title,
            "listing_url": row.listing_url,
            "intent": row.intent,
            "area_value": row.area_value,
            "area_unit": row.area_unit,
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "city": row.city or _city_of(row.location_text),
            "source_name": source_names.get(row.id, "Unknown").title(),
        }
        for row in leads
    ]

    return build_dashboard_payload(
        total_leads=int(total_leads),
        total_posts=int(total_posts),
        total_sources=int(total_sources),
        last_post=last_post,
        leads=lead_rows,
        sources=[{"name": row[0], "enabled": row[1]} for row in sources],
        new_today=int(new_today),
        scan_status=scan_status(),
    )


# -- helpers -----------------------------------------------------------------
def _metric(
    label: str,
    value: float,
    change: str,
    *,
    suffix: str | None = None,
    up: bool = False,
    down: bool = False,
) -> dict:
    """One metric tile. `change` is a factual descriptor, never an invented percentage."""
    tile = {
        "label": label,
        "value": value,
        "change": change,
        "trend": "up" if up else "down" if down else "neutral",
    }
    if suffix is not None:
        tile["suffix"] = suffix
    return tile


def _score_label(score: int) -> str:
    if score >= 85:
        return "Hot Lead"
    if score >= 70:
        return "High Priority"
    return "Medium Priority"


def _city_of(location_text: str | None) -> str:
    """City is the last segment of 'Area, Society, City'."""
    if not location_text:
        return "Unknown"
    return location_text.split(",")[-1].strip() or "Unknown"


def _frequency_label(interval_seconds: Any) -> str:
    if not interval_seconds:
        return "n/a"
    seconds = float(interval_seconds)
    return f"Every {int(seconds)}s" if seconds < 120 else f"Every {int(seconds // 60)}m"


def _success_rate(state: dict) -> int:
    runs = int(state.get("totalRuns") or 0)
    if not runs:
        return 0
    errors = int(state.get("consecutiveErrors") or 0)
    return max(0, round(100 * (runs - errors) / runs))


def _relative(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        moment = dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    seconds = (dt.datetime.now(dt.UTC) - moment).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _insights(
    total_leads: int,
    total_posts: int,
    total_sources: int,
    new_today: int,
    cities: Counter,
    sellers: Counter,
    avg_price: int,
) -> list[str]:
    insights = [
        f"{total_leads} lead(s) in the database; {new_today} arrived today.",
        f"{total_posts} post(s) ingested from {total_sources} source(s).",
    ]
    if cities:
        city, count = cities.most_common(1)[0]
        insights.append(f"{city} leads the pipeline with {count} lead(s).")
    if sellers.get("owner"):
        share = round(100 * sellers["owner"] / max(sum(sellers.values()), 1))
        insights.append(f"{share}% of leads are direct-owner listings.")
    if avg_price:
        insights.append(f"Average listed price is {avg_price:,.0f} PKR.")
    return insights
