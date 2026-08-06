"""Lead browsing endpoints — the data layer behind the Leads workspace.

The list is filtered, sorted and paginated *in SQL* rather than in the browser. That is the
whole point of this module: the dashboard used to fetch the newest 200 leads and filter them
client-side, which meant "all leads in Karachi last month" silently searched only whatever
happened to be in that window. Every filter here therefore runs against the full table, and
`total` reflects the real match count, not the page.

Historical browsing needs no new storage: `leads.first_seen_at` has always recorded when a
lead was discovered. What was missing was a way to *ask* for a range, which `dateFrom`/`dateTo`
now provide.
"""
from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Lead, LeadSource, RawPost
from app.db.session import session_scope
# Query construction lives outside the API layer so the saved-search matcher in the background
# worker can apply the exact same predicates without importing the FastAPI app. See
# app.leads_query for why. Re-exported here so existing imports of this module keep working.
from app.leads_query import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    LeadFilters,
    LeadPage,
    apply_filters,
    apply_sort,
    count_matching,
)
from app.leads_query import csv_values as _csv
from app.serializers import lead_detail as _lead_detail
from app.serializers import lead_summary as _lead_summary

router = APIRouter(prefix="/api/leads", tags=["leads"])

__all__ = [
    "router",
    "LeadFilters",
    "LeadPage",
    "apply_filters",
    "apply_sort",
    "count_matching",
    "parse_moment",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
]


def parse_moment(value: str | None, *, end_of_day: bool = False) -> dt.datetime | None:
    """Accept either a full ISO instant or a bare `YYYY-MM-DD` date.

    The dashboard sends instants so a range means "today *in the user's timezone*". A bare date
    is still accepted for hand-written calls and is interpreted as a UTC day, with `end_of_day`
    extending it to the final microsecond so `dateTo=2026-08-05` includes all of the 5th.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            day = dt.date.fromisoformat(text)
            moment = dt.datetime.combine(
                day,
                dt.time.max if end_of_day else dt.time.min,
                tzinfo=dt.UTC,
            )
        else:
            moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid date '{value}'. Use ISO-8601 or YYYY-MM-DD."
        ) from exc
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


# -- endpoints ---------------------------------------------------------------
@router.get("")
def list_leads(
    # Annotated form (not `= Query(...)` defaults) so the parameters are plain values with
    # ordinary defaults; the camelCase names are the wire contract the dashboard sends.
    search: Annotated[str | None, Query(description="Title, location, city or contact")] = None,
    city: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    sellerType: Annotated[list[str] | None, Query()] = None,  # noqa: N803
    propertyType: Annotated[list[str] | None, Query()] = None,  # noqa: N803
    status: Annotated[list[str] | None, Query()] = None,
    minScore: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    maxScore: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    minPrice: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    maxPrice: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    minBedrooms: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    maxBedrooms: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    dateFrom: Annotated[str | None, Query(description="ISO instant or YYYY-MM-DD")] = None,  # noqa: N803, E501
    dateTo: Annotated[str | None, Query(description="ISO instant or YYYY-MM-DD")] = None,  # noqa: N803, E501
    sort: Annotated[str, Query()] = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,  # noqa: N803
) -> dict:
    """A page of leads matching the filters, newest first by default.

    Returns an envelope rather than a bare array because the client needs `total` to paginate
    honestly — without it the UI can only report "showing what we happened to fetch".
    """
    filters = LeadFilters(
        search=search,
        cities=_csv(city),
        sources=_csv(source),
        seller_types=_csv(sellerType),
        property_types=_csv(propertyType),
        statuses=_csv(status),
        min_score=minScore,
        max_score=maxScore,
        min_price=minPrice,
        max_price=maxPrice,
        min_bedrooms=minBedrooms,
        max_bedrooms=maxBedrooms,
        date_from=parse_moment(dateFrom),
        date_to=parse_moment(dateTo, end_of_day=True),
    )

    with session_scope() as session:
        total = int(
            session.scalar(apply_filters(select(func.count(Lead.id)), filters)) or 0
        )

        stmt = apply_sort(apply_filters(select(Lead), filters), sort)
        rows = session.scalars(
            stmt.options(
                selectinload(Lead.photos),
                selectinload(Lead.sources)
                .selectinload(LeadSource.raw_post)
                .selectinload(RawPost.source),
            )
            .offset((page - 1) * pageSize)
            .limit(pageSize)
        ).all()

        items = [_lead_summary(lead) for lead in rows]

    return LeadPage(items=items, total=total, page=page, page_size=pageSize).to_dict()


@router.get("/facets")
def lead_facets() -> dict:
    """Distinct filter values across the *whole* table, plus the observed ranges.

    Derived from the data rather than hard-coded, and deliberately not scoped to the current
    page: a dropdown built from one page of results cannot offer the value the user is looking
    for, which is exactly the bug that makes client-side filtering feel broken.
    """
    with session_scope() as session:
        cities = session.scalars(
            select(Lead.city).where(Lead.city.isnot(None)).distinct().order_by(Lead.city)
        ).all()
        property_types = session.scalars(
            select(Lead.property_type)
            .where(Lead.property_type.isnot(None))
            .distinct()
            .order_by(Lead.property_type)
        ).all()
        seller_types = session.scalars(
            select(Lead.seller_type)
            .where(Lead.seller_type.isnot(None))
            .distinct()
            .order_by(Lead.seller_type)
        ).all()
        statuses = session.scalars(
            select(Lead.status).where(Lead.status.isnot(None)).distinct().order_by(Lead.status)
        ).all()
        sources = session.scalars(
            select(Source.name)
            .join(RawPost, RawPost.source_id == Source.id)
            .join(LeadSource, LeadSource.raw_post_id == RawPost.id)
            .distinct()
            .order_by(Source.name)
        ).all()

        bounds = session.execute(
            select(
                func.min(Lead.price),
                func.max(Lead.price),
                func.min(Lead.score),
                func.max(Lead.score),
                func.min(Lead.first_seen_at),
                func.max(Lead.first_seen_at),
                func.count(Lead.id),
            )
        ).one()

    return {
        "cities": list(cities),
        "sources": [name.title() for name in sources],
        "sellerTypes": list(seller_types),
        "propertyTypes": list(property_types),
        "statuses": list(statuses),
        "priceRange": {"min": bounds[0] or 0, "max": bounds[1] or 0},
        "scoreRange": {"min": int(bounds[2] or 0), "max": int(bounds[3] or 0)},
        "dateRange": {
            "earliest": bounds[4].isoformat() if bounds[4] else None,
            "latest": bounds[5].isoformat() if bounds[5] else None,
        },
        "totalLeads": int(bounds[6] or 0),
    }


@router.get("/{lead_id}")
def lead_detail(lead_id: str) -> dict:
    """Everything the detail view renders, including the full gallery and raw metadata."""
    with session_scope() as session:
        lead = session.scalar(
            select(Lead)
            .where(Lead.id == lead_id)
            .options(
                selectinload(Lead.photos),
                selectinload(Lead.sources)
                .selectinload(LeadSource.raw_post)
                .selectinload(RawPost.source),
            )
        )

        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        return _lead_detail(lead)


@router.patch("/{lead_id}/status")
def update_lead_status(lead_id: str, payload: dict) -> dict:
    """Move a lead through review. The Leads page is a workspace, not a read-only report."""
    status = str(payload.get("status") or "").strip().lower()
    allowed = {"new", "reviewed", "assigned", "archived"}
    if status not in allowed:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(allowed)}")

    with session_scope() as session:
        lead = session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead.status = status
        session.flush()
        return {"id": lead.id, "status": lead.status}


__all__ = [
    "router",
    "LeadFilters",
    "LeadPage",
    "apply_filters",
    "apply_sort",
    "parse_moment",
]
