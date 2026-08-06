"""Lead query construction: the filter/sort/paginate vocabulary, independent of HTTP.

This lives outside `app.api` on purpose. Narrowing a set of leads is domain logic, and it has
two consumers with very different lifecycles: the leads endpoints, and the saved-search
matcher that the background worker runs. Importing `app.api.leads` from the worker would drag
the entire FastAPI app in behind it (`app/api/__init__.py` imports `main`), which is a genuine
import cycle — worker -> matcher -> api -> main -> worker.

Keeping the vocabulary here means the alert matcher and the list endpoint apply *literally the
same predicates*. That is the property that matters: an alert that disagrees with the list it
links to is worse than no alert at all.

`app.api.leads` re-exports these names, so existing imports keep working.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Lead, LeadSource, RawPost, Source

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 25

# `nulls_last` on every ordering column: a lead with no price must not outrank a priced one
# just because SQL sorts NULL first on DESC.
_SORTS: dict[str, list[Any]] = {
    "newest": [Lead.first_seen_at.desc().nulls_last(), Lead.id.desc()],
    "oldest": [Lead.first_seen_at.asc().nulls_last(), Lead.id.asc()],
    "price_high": [Lead.price.desc().nulls_last(), Lead.first_seen_at.desc()],
    "price_low": [Lead.price.asc().nulls_last(), Lead.first_seen_at.desc()],
    "score_high": [Lead.score.desc().nulls_last(), Lead.first_seen_at.desc()],
    "score_low": [Lead.score.asc().nulls_last(), Lead.first_seen_at.desc()],
}


@dataclass(frozen=True)
class LeadFilters:
    """Everything the list can be narrowed by. Empty fields are simply not applied."""

    search: str | None = None
    cities: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    seller_types: tuple[str, ...] = ()
    property_types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    min_score: float | None = None
    max_score: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_bedrooms: float | None = None
    max_bedrooms: float | None = None
    date_from: dt.datetime | None = None
    date_to: dt.datetime | None = None


@dataclass
class LeadPage:
    items: list[dict] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def total_pages(self) -> int:
        return max(1, -(-self.total // self.page_size))  # ceil division

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "pageSize": self.page_size,
            "totalPages": self.total_pages,
            "hasMore": self.page < self.total_pages,
        }


def _source_matches(names: tuple[str, ...]) -> ColumnElement[bool]:
    """A lead matches a source if any of its linked raw posts came from it.

    Expressed as EXISTS rather than a JOIN so a lead that dedup collapsed across two portals
    is not returned twice — which would corrupt both the page size and `total`.
    """
    lowered = [name.lower() for name in names]
    return Lead.sources.any(
        LeadSource.raw_post.has(RawPost.source.has(func.lower(Source.name).in_(lowered)))
    )


def apply_filters(stmt: Select, filters: LeadFilters) -> Select:
    """Attach every populated filter as a WHERE clause."""
    if filters.search:
        term = f"%{filters.search.strip()}%"
        stmt = stmt.where(
            or_(
                Lead.title.ilike(term),
                Lead.description.ilike(term),
                Lead.location_text.ilike(term),
                Lead.city.ilike(term),
                Lead.property_type.ilike(term),
                Lead.contact_name.ilike(term),
                Lead.contact_phone.ilike(term),
            )
        )
    if filters.cities:
        stmt = stmt.where(func.lower(Lead.city).in_([c.lower() for c in filters.cities]))
    if filters.property_types:
        stmt = stmt.where(
            func.lower(Lead.property_type).in_([t.lower() for t in filters.property_types])
        )
    if filters.seller_types:
        stmt = stmt.where(
            func.lower(Lead.seller_type).in_([s.lower() for s in filters.seller_types])
        )
    if filters.statuses:
        stmt = stmt.where(func.lower(Lead.status).in_([s.lower() for s in filters.statuses]))
    if filters.sources:
        stmt = stmt.where(_source_matches(filters.sources))
    if filters.min_score is not None:
        stmt = stmt.where(Lead.score >= filters.min_score)
    if filters.max_score is not None:
        stmt = stmt.where(Lead.score <= filters.max_score)
    if filters.min_price is not None:
        stmt = stmt.where(Lead.price >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Lead.price <= filters.max_price)
    if filters.min_bedrooms is not None:
        stmt = stmt.where(Lead.bedrooms >= filters.min_bedrooms)
    if filters.max_bedrooms is not None:
        stmt = stmt.where(Lead.bedrooms <= filters.max_bedrooms)
    if filters.date_from is not None:
        stmt = stmt.where(Lead.first_seen_at >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Lead.first_seen_at <= filters.date_to)
    return stmt


def apply_sort(stmt: Select, sort: str) -> Select:
    return stmt.order_by(*_SORTS.get(sort, _SORTS["newest"]))


def csv_values(values: list[str] | None) -> tuple[str, ...]:
    """Filters arrive either repeated (`?city=A&city=B`) or comma-joined; accept both."""
    if not values:
        return ()
    out: list[str] = []
    for value in values:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    # Order-preserving dedupe, so `?city=Lahore&city=lahore` is one predicate.
    seen: set[str] = set()
    return tuple(item for item in out if not (item.lower() in seen or seen.add(item.lower())))


def count_matching(session, filters: LeadFilters) -> int:
    """How many leads match, over the whole table."""
    return int(session.scalar(apply_filters(select(func.count(Lead.id)), filters)) or 0)
