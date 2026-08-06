"""Lead -> dashboard JSON.

Lives outside `app.api` on purpose. The background worker must emit a realtime lead in
exactly the shape the REST endpoints return — if the two drifted, a lead pushed over the
WebSocket would render differently from the same lead after a page reload. Importing this
from the API package would drag the FastAPI app (and therefore the worker) into the
pipeline's import graph, so the shared presentation layer sits one level up instead.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Lead, RawPost
from app.pipeline.classify import derive_city, derive_property_type
from app.pipeline.photos import public_photo_urls
from app.pipeline.urls import clean_listing_url


def format_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%H:%M UTC")


def latest_raw_post(lead: Lead) -> RawPost | None:
    posts = [link.raw_post for link in lead.sources if link.raw_post is not None]
    if not posts:
        return None
    return max(posts, key=lambda post: post.scraped_at or datetime.min.replace(tzinfo=UTC))


def listing_url_for(lead: Lead, raw_post: RawPost | None) -> str | None:
    """The ad's deep link.

    `leads.listing_url` is the denormalized copy written at ingest and is authoritative; the
    raw post is a fallback for rows created before that column existed. Both go through
    validation, so a stale or malformed value renders as "Unavailable" rather than sending the
    user to a page that reports "Ad not found".
    """
    return clean_listing_url(lead.listing_url) or clean_listing_url(
        raw_post.url if raw_post is not None else None
    )


def infer_property_type(raw_post: RawPost | None, lead: Lead) -> str | None:
    """The stored column when present, otherwise the same derivation applied on the fly.

    Rows written before `leads.property_type` existed (and any the backfill could not resolve)
    still render a type here; only the persisted value is filterable.
    """
    if lead.property_type:
        return lead.property_type
    return derive_property_type(
        raw_post.raw_json if raw_post is not None else None,
        (
            raw_post.title if raw_post is not None else None,
            raw_post.text if raw_post is not None else None,
            lead.title,
            lead.description,
        ),
    )


def lead_city(lead: Lead) -> str:
    return lead.city or derive_city(lead.location_text) or "Unknown"


def lead_source_name(raw_post: RawPost | None) -> str:
    if raw_post is None or raw_post.source is None:
        return "Unknown"
    return raw_post.source.name.title()


def lead_title(lead: Lead, raw_post: RawPost | None) -> str:
    if lead.title:
        return lead.title
    if raw_post is not None:
        if raw_post.title:
            return raw_post.title
        raw_json = raw_post.raw_json or {}
        for key in ("title", "headline", "name"):
            value = raw_json.get(key)
            if value:
                return str(value)
    if lead.description:
        return lead.description.split("\n", 1)[0][:80]
    return "Property listing"


def _images(lead: Lead, raw_post: RawPost | None) -> list[str]:
    """Every photo for a lead, cover first, as URLs a browser can actually load.

    Repaired on read as well as on write (`public_photo_urls`): the raw post is stored verbatim
    by design, so its photo links are whatever the provider returned — and leads ingested
    before the repair existed still hold the unusable original.
    """
    images = [photo.url for photo in lead.photos if photo.url]
    if raw_post is None:
        return public_photo_urls(images)

    raw_json = raw_post.raw_json or {}
    for key in ("coverPhoto", "thumbnail", "image", "cover", "coverImage"):
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
    # Deduped after repair, since the S3 and CDN forms of one photo collapse to the same URL.
    return public_photo_urls(images)


def lead_summary(lead: Lead) -> dict:
    """Row shape consumed by the dashboard table and the realtime stream."""
    raw_post = latest_raw_post(lead)
    images = _images(lead, raw_post)
    location = lead.location_text or "Unknown"
    summary_text = lead.description or (raw_post.text if raw_post is not None else "") or ""

    return {
        "id": lead.id,
        "title": lead_title(lead, raw_post),
        "propertyType": infer_property_type(raw_post, lead),
        "thumbnail": images[0] if images else None,
        "image": images[0] if images else None,
        "city": lead_city(lead),
        "location": location,
        "price": lead.price or 0,
        "currency": lead.currency or "PKR",
        "bedrooms": lead.bedrooms or 0,
        "area": (
            f"{lead.area_value:g} {lead.area_unit}"
            if lead.area_value and lead.area_unit
            else "Unknown"
        ),
        "sellerType": lead.seller_type or "unknown",
        "score": int(lead.score or 0),
        "source": lead_source_name(raw_post),
        "status": lead.status,
        "dateAdded": format_iso(lead.first_seen_at),
        "lastSeen": format_iso(lead.last_seen_at) or "Unknown",
        "aiSummary": summary_text[:240] if summary_text else "No extracted summary available.",
        "originalListingUrl": listing_url_for(lead, raw_post),
        "scrapedAt": format_iso(raw_post.scraped_at) if raw_post is not None else None,
        "postedAt": format_iso(raw_post.posted_at) if raw_post is not None else None,
        "contactName": lead.contact_name,
        "contactPhone": lead.contact_phone,
    }


def lead_detail(lead: Lead) -> dict:
    """Row shape plus everything the detail drawer renders."""
    raw_post = latest_raw_post(lead)
    summary = lead_summary(lead)
    raw_json = raw_post.raw_json if raw_post is not None else {}
    return {
        **summary,
        "description": lead.description
        or (raw_post.text if raw_post is not None else summary["aiSummary"]),
        "images": _images(lead, raw_post),
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
