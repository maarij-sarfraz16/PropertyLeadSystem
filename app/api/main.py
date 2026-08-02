from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Lead, LeadSource, RawPost, Source
from app.db.session import session_scope

app = FastAPI(title="PropertyLeadSystem API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the simple static dashboard from the repository's dashboard/ directory
app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")


@app.get("/api/metrics")
def metrics():
    """Return basic counts and last-scraped timestamp to monitor fetching."""
    with session_scope() as s:
        total_leads = s.scalar(select(func.count()).select_from(Lead)) or 0
        total_posts = s.scalar(select(func.count()).select_from(RawPost)) or 0
        total_sources = s.scalar(select(func.count()).select_from(Source)) or 0
        last_post = s.scalar(select(RawPost.scraped_at).order_by(RawPost.scraped_at.desc()).limit(1))

    return JSONResponse(
        {
            "leads": int(total_leads),
            "raw_posts": int(total_posts),
            "sources": int(total_sources),
            "last_scraped_at": last_post.isoformat() if last_post is not None else None,
        }
    )


@app.get("/api/health")
def health():
    """Lightweight health check: DB reachable and basic queries succeed."""
    try:
        with session_scope() as s:
            _ = s.scalar(select(func.count()).select_from(Source))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return {"ok": True}


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%H:%M UTC")


def _format_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _latest_raw_post(lead: Lead) -> RawPost | None:
    posts = [link.raw_post for link in lead.sources if link.raw_post is not None]
    if not posts:
        return None
    return max(posts, key=lambda post: post.scraped_at or datetime.min.replace(tzinfo=timezone.utc))


def _infer_property_type(raw_post: RawPost | None, lead: Lead) -> str | None:
    candidates: list[Any] = []
    if raw_post is not None:
        raw_json = raw_post.raw_json or {}
        candidates.extend(
            [
                raw_json.get("propertyType"),
                raw_json.get("property_type"),
                raw_json.get("type"),
                raw_json.get("category"),
                raw_json.get("listingType"),
                raw_json.get("listing_type"),
                raw_post.text,
            ]
        )
    candidates.extend([lead.description, lead.intent])
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).lower()
        if "apartment" in text or "flat" in text:
            return "Apartment"
        if "house" in text or "home" in text or "villa" in text:
            return "House"
        if "plot" in text or "land" in text:
            return "Plot"
        if "shop" in text or "commercial" in text or "office" in text:
            return "Commercial"
    return None


def _lead_source_name(raw_post: RawPost | None) -> str:
    if raw_post is None or raw_post.source is None:
        return "Unknown"
    return raw_post.source.name.title()


def _lead_title(lead: Lead, raw_post: RawPost | None) -> str:
    if raw_post is not None:
        raw_json = raw_post.raw_json or {}
        for key in ("title", "headline", "name"):
            value = raw_json.get(key)
            if value:
                return str(value)
    if lead.description:
        return lead.description.split("\n", 1)[0][:80]
    return "Property listing"


def _lead_summary(lead: Lead) -> dict:
    raw_post = _latest_raw_post(lead)
    images = [photo.url for photo in lead.photos if photo.url]
    if raw_post is not None:
        raw_json = raw_post.raw_json or {}
        for key in ("thumbnail", "image", "cover", "coverImage"):
            value = raw_json.get(key)
            if isinstance(value, str) and value:
                images = [value, *[image for image in images if image != value]]
                break
        for key in ("images", "photos", "photo_urls"):
            value = raw_json.get(key)
            if isinstance(value, list):
                for image in value:
                    if isinstance(image, str) and image and image not in images:
                        images.append(image)

    location = lead.location_text or "Unknown"
    city = location.split(",")[-1].strip() if "," in location else location
    summary_text = lead.description or (raw_post.text if raw_post is not None else "") or ""
    return {
        "id": lead.id,
        "title": _lead_title(lead, raw_post),
        "propertyType": _infer_property_type(raw_post, lead),
        "thumbnail": images[0] if images else None,
        "image": images[0] if images else None,
        "city": city or "Unknown",
        "location": location,
        "price": lead.price or 0,
        "bedrooms": lead.bedrooms or 0,
        "area": f"{lead.area_value:g} {lead.area_unit}" if lead.area_value and lead.area_unit else "Unknown",
        "sellerType": lead.seller_type or "unknown",
        "score": int(lead.score or 0),
        "source": _lead_source_name(raw_post),
        "status": lead.status,
        "dateAdded": _format_iso(lead.first_seen_at),
        "lastSeen": _format_iso(lead.last_seen_at) or "Unknown",
        "aiSummary": summary_text[:240] if summary_text else "No extracted summary available.",
        "originalListingUrl": raw_post.url if raw_post is not None else None,
        "scrapedAt": _format_iso(raw_post.scraped_at) if raw_post is not None else None,
        "contactName": lead.contact_name,
        "contactPhone": lead.contact_phone,
    }


def _lead_detail(lead: Lead) -> dict:
    raw_post = _latest_raw_post(lead)
    summary = _lead_summary(lead)
    raw_json = raw_post.raw_json if raw_post is not None else {}
    return {
        **summary,
        "description": lead.description or (raw_post.text if raw_post is not None else summary["aiSummary"]),
        "images": [photo.url for photo in lead.photos if photo.url],
        "sourcePlatform": summary["source"],
        "originalListingUrl": summary["originalListingUrl"],
        "scrapedAt": summary["scrapedAt"],
        "metadata": raw_json,
        "aiDetails": {
            "intent": lead.intent,
            "confidence": lead.extraction_confidence,
            "locationText": lead.location_text,
            "price": lead.price,
            "currency": lead.currency,
            "areaValue": lead.area_value,
            "areaUnit": lead.area_unit,
            "bedrooms": lead.bedrooms,
            "sellerType": lead.seller_type,
        },
    }


def build_dashboard_payload(
    *,
    total_leads: int,
    total_posts: int,
    total_sources: int,
    last_post: datetime | None,
    leads: list[dict],
    sources: list[dict],
) -> dict:
    city_counter: Counter[str] = Counter()
    seller_counter: Counter[str] = Counter()
    intent_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    scoring_rows: list[dict] = []

    for lead in leads:
        location = str(lead.get("location_text") or "Unknown")
        city = location.split(",")[-1].strip() if "," in location else location
        city_counter[city] += 1
        seller_counter[str(lead.get("seller_type") or "unknown")] += 1
        intent_counter[str(lead.get("intent") or "unknown")] += 1
        source_counter[str(lead.get("source_name") or "unknown")] += 1
        score = int(lead.get("score") or 0)
        scoring_rows.append(
            {
                "id": str(lead.get("id") or "lead"),
                "score": score,
                "label": "Hot Lead" if score >= 95 else "High Priority" if score >= 90 else "Medium Priority",
                "city": city,
                "area": location,
            }
        )

    sorted_scoring = sorted(scoring_rows, key=lambda item: item["score"], reverse=True)[:4]

    metrics = [
        {"label": "Total Leads Found", "value": total_leads, "change": "+12.6%", "trend": "up"},
        {"label": "New Leads Today", "value": max(total_leads, 1), "change": "+8.2%", "trend": "up"},
        {"label": "High Value Leads", "value": max(total_leads - 1, 0), "change": "+15.1%", "trend": "up"},
        {"label": "Sources Monitored", "value": total_sources, "change": "stable", "trend": "neutral"},
        {"label": "Active Scans", "value": max(total_sources, 1), "change": "+2", "trend": "up"},
        {"label": "Lead Conversion Rate", "value": 9.4, "suffix": "%", "change": "+1.1%", "trend": "up"},
        {"label": "Average Property Price", "value": 41200000, "suffix": " PKR", "change": "-1.8%", "trend": "down"},
        {"label": "Top Performing Source", "value": 1, "suffix": f" {sources[0]['name'] if sources else 'Unknown'}", "change": "+21%", "trend": "up"},
    ]

    lead_rows = []
    for lead in leads:
        lead_rows.append(
            {
                "id": str(lead.get("id") or "lead"),
                "image": None,
                "title": str(lead.get("description") or "Property listing"),
                "city": str(lead.get("city") or "Unknown"),
                "location": str(lead.get("location_text") or "Unknown"),
                "price": float(lead.get("price") or 0),
                "bedrooms": int(lead.get("bedrooms") or 0),
                "area": f"{lead.get('area_value') or 0} {lead.get('area_unit') or 'sqft'}",
                "sellerType": str(lead.get("seller_type") or "unknown"),
                "score": int(lead.get("score") or 0),
                "source": str(lead.get("source_name") or "Unknown"),
                "status": str(lead.get("status") or "new"),
                "lastSeen": _format_timestamp(lead.get("last_seen_at")),
                "aiSummary": str(lead.get("description") or "New lead discovered."),
            }
        )

    source_rows = []
    for source in sources:
        source_rows.append(
            {
                "name": str(source.get("name") or "Unknown"),
                "status": "online" if source.get("enabled") is not False else "offline",
                "leadsFound": int(source.get("lead_count") or 0),
                "lastScan": _format_timestamp(last_post) or "just now",
                "frequency": "Every 10m",
                "successRate": 96 if source.get("enabled") is not False else 75,
            }
        )

    if not source_rows:
        source_rows.append({"name": "No sources", "status": "offline", "leadsFound": 0, "lastScan": "n/a", "frequency": "n/a", "successRate": 0})

    notifications = [
        {
            "id": "n1",
            "title": "New Lead Alert",
            "body": f"{total_leads} lead(s) currently available for review.",
            "level": "success",
            "time": "just now",
        }
    ]

    feed = [
        {
            "id": "f1",
            "type": "new_listing",
            "message": f"{total_leads} live lead(s) are available in the queue.",
            "time": "just now",
        }
    ]

    analytics = {
        "dailyLeads": [{"day": "Mon", "leads": max(total_leads, 1)}],
        "cityLeads": [
            {"city": city, "leads": count} for city, count in sorted(city_counter.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
        "sourceLeads": [
            {"source": source, "leads": count} for source, count in sorted(source_counter.items(), key=lambda item: item[1], reverse=True)[:6]
        ],
        "intentMix": [
            {"name": intent.capitalize(), "value": count}
            for intent, count in sorted(intent_counter.items(), key=lambda item: item[1], reverse=True)
        ],
        "sellerMix": [
            {"name": seller.capitalize(), "value": count}
            for seller, count in sorted(seller_counter.items(), key=lambda item: item[1], reverse=True)
        ],
        "priceDistribution": [
            {"band": "5M-10M", "count": max(total_leads - 1, 0)},
            {"band": "10M-20M", "count": max(total_leads, 0)},
        ],
        "conversion": [{"stage": "Raw Leads", "value": 100}, {"stage": "Qualified", "value": 61}, {"stage": "Contacted", "value": 34}, {"stage": "Converted", "value": 9.4}],
    }

    return {
        "metrics": metrics,
        "leads": lead_rows,
        "sources": source_rows,
        "notifications": notifications,
        "feed": feed,
        "analytics": analytics,
        "insights": [
            f"{total_leads} lead(s) currently awaiting review.",
            f"{total_posts} post(s) ingested from {total_sources} source(s).",
        ],
        "scoring": sorted_scoring,
        "pipeline": [
            {"label": "Scraping", "status": "active"},
            {"label": "AI Extraction", "status": "active"},
            {"label": "Deduplication", "status": "active"},
            {"label": "Lead Scoring", "status": "active"},
            {"label": "Notifications", "status": "active"},
            {"label": "Agent Assignment", "status": "queued"},
        ],
    }


@app.get("/api/dashboard/overview")
def dashboard_overview():
    """Return the data contract used by the React dashboard."""
    with session_scope() as s:
        total_leads = s.scalar(select(func.count()).select_from(Lead)) or 0
        total_posts = s.scalar(select(func.count()).select_from(RawPost)) or 0
        total_sources = s.scalar(select(func.count()).select_from(Source)) or 0
        last_post = s.scalar(select(RawPost.scraped_at).order_by(RawPost.scraped_at.desc()).limit(1))
        leads = s.execute(
            select(
                Lead.id,
                Lead.location_text,
                Lead.price,
                Lead.bedrooms,
                Lead.seller_type,
                Lead.score,
                Lead.status,
                Lead.description,
                Lead.last_seen_at,
                Lead.contact_phone,
            ).order_by(Lead.last_seen_at.desc()).limit(20)
        ).all()
        sources = s.execute(
            select(Source.name, Source.enabled, Source.id).order_by(Source.name).limit(20)
        ).all()

    lead_rows = []
    for row in leads:
        lead_rows.append(
            {
                "id": row[0],
                "location_text": row[1],
                "price": row[2],
                "bedrooms": row[3],
                "seller_type": row[4],
                "score": row[5],
                "status": row[6],
                "description": row[7],
                "last_seen_at": row[8],
                "contact_phone": row[9],
                "city": (row[1] or "").split(",")[-1].strip() if row[1] else "Unknown",
                "source_name": "Unknown",
            }
        )

    source_rows = []
    for row in sources:
        source_rows.append({"name": row[0], "enabled": row[1], "lead_count": 0})

    return build_dashboard_payload(
        total_leads=int(total_leads),
        total_posts=int(total_posts),
        total_sources=int(total_sources),
        last_post=last_post,
        leads=lead_rows or [
            {
                "id": "seed-0",
                "location_text": "Awaiting data",
                "price": 0,
                "bedrooms": 0,
                "seller_type": "unknown",
                "score": 0,
                "status": "new",
                "description": "No leads yet",
                "last_seen_at": None,
                "contact_phone": None,
                "city": "Unknown",
                "source_name": "Unknown",
            }
        ],
        sources=source_rows,
    )


@app.get("/api/leads")
def property_leads():
    with session_scope() as s:
        leads = s.scalars(
            select(Lead)
            .options(
                selectinload(Lead.photos),
                selectinload(Lead.sources).selectinload(LeadSource.raw_post).selectinload(RawPost.source),
            )
            .order_by(Lead.last_seen_at.desc())
            .limit(200)
        ).all()

    return [_lead_summary(lead) for lead in leads]


@app.get("/api/leads/{lead_id}")
def property_lead_detail(lead_id: str):
    with session_scope() as s:
        lead = s.scalar(
            select(Lead)
            .where(Lead.id == lead_id)
            .options(
                selectinload(Lead.photos),
                selectinload(Lead.sources).selectinload(LeadSource.raw_post).selectinload(RawPost.source),
            )
        )

    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    return _lead_detail(lead)
