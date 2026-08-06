"""Query-construction tests for the leads endpoints.

Deliberately database-free: they assert on the compiled SQL and on the pure helpers, so the
filter contract is verified without a live Postgres. What they protect is the property that
every filter reaches the database — a filter that silently no-ops would still return a
plausible-looking page, which is exactly the failure a rendered-SQL assertion catches.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.leads import (
    DEFAULT_PAGE_SIZE,
    LeadFilters,
    LeadPage,
    _csv,
    apply_filters,
    apply_sort,
    parse_moment,
)
from app.db.models import Lead
from app.pipeline.classify import derive_city, derive_property_type


def rendered(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_no_filters_adds_no_where_clause():
    sql = rendered(apply_filters(select(Lead.id), LeadFilters()))
    assert "WHERE" not in sql


def test_search_covers_title_location_and_contact():
    sql = rendered(apply_filters(select(Lead.id), LeadFilters(search="DHA")))

    assert "%DHA%" in sql
    # The default dialect renders ILIKE as `lower(col) LIKE lower(...)`; assert on the column
    # being case-insensitively matched rather than on Postgres' spelling of the operator.
    for column in ("title", "description", "location_text", "city", "contact_phone"):
        assert f"lower(leads.{column}) LIKE" in sql


def test_scalar_filters_are_case_insensitive():
    filters = LeadFilters(
        cities=("Lahore",),
        property_types=("House",),
        seller_types=("Owner",),
        statuses=("New",),
    )
    sql = rendered(apply_filters(select(Lead.id), filters))

    assert "lower(leads.city) IN ('lahore')" in sql
    assert "lower(leads.property_type) IN ('house')" in sql
    assert "lower(leads.seller_type) IN ('owner')" in sql
    assert "lower(leads.status) IN ('new')" in sql


def test_source_filter_uses_exists_not_join():
    """A lead linked to two posts from one source must not be counted twice."""
    sql = rendered(apply_filters(select(Lead.id), LeadFilters(sources=("Zameen",))))

    assert "EXISTS" in sql
    assert "lower(sources.name) IN ('zameen')" in sql
    assert "JOIN lead_sources" not in sql


def test_date_range_filters_on_discovery_time():
    filters = LeadFilters(
        date_from=dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
        date_to=dt.datetime(2026, 7, 31, tzinfo=dt.UTC),
    )
    sql = rendered(apply_filters(select(Lead.id), filters))

    assert "leads.first_seen_at >=" in sql
    assert "leads.first_seen_at <=" in sql


def test_numeric_bounds_are_applied():
    filters = LeadFilters(min_score=70, max_score=84, min_price=1_000_000, max_price=5_000_000)
    sql = rendered(apply_filters(select(Lead.id), filters))

    assert "leads.score >= 70" in sql
    assert "leads.score <= 84" in sql
    assert "leads.price >= 1000000" in sql
    assert "leads.price <= 5000000" in sql


def test_filters_apply_identically_to_the_count_query():
    """`total` must describe the same rows as the page, or pagination lies."""
    filters = LeadFilters(cities=("Lahore",), min_score=80)
    page_sql = rendered(apply_filters(select(Lead), filters))
    count_sql = rendered(apply_filters(select(func.count(Lead.id)), filters))

    assert "lower(leads.city) IN ('lahore')" in page_sql
    assert "lower(leads.city) IN ('lahore')" in count_sql
    assert "leads.score >= 80" in count_sql


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("newest", "leads.first_seen_at DESC"),
        ("oldest", "leads.first_seen_at ASC"),
        ("price_high", "leads.price DESC"),
        ("price_low", "leads.price ASC"),
        ("score_high", "leads.score DESC"),
        ("score_low", "leads.score ASC"),
    ],
)
def test_sort_options(sort, expected):
    sql = rendered(apply_sort(select(Lead.id), sort))
    assert expected in sql
    # Rows missing the sort value must never outrank rows that have it.
    assert "NULLS LAST" in sql


def test_unknown_sort_falls_back_to_newest():
    assert "leads.first_seen_at DESC" in rendered(apply_sort(select(Lead.id), "nonsense"))


# -- date parsing ------------------------------------------------------------
def test_parse_moment_accepts_bare_date_as_utc_day():
    assert parse_moment("2026-08-05") == dt.datetime(2026, 8, 5, 0, 0, tzinfo=dt.UTC)


def test_parse_moment_end_of_day_includes_the_whole_day():
    moment = parse_moment("2026-08-05", end_of_day=True)
    assert moment is not None
    assert (moment.hour, moment.minute, moment.second) == (23, 59, 59)


def test_parse_moment_accepts_iso_instants():
    assert parse_moment("2026-08-05T19:00:00Z") == dt.datetime(2026, 8, 5, 19, 0, tzinfo=dt.UTC)


def test_parse_moment_assumes_utc_for_naive_input():
    assert parse_moment("2026-08-05T19:00:00").tzinfo == dt.UTC


def test_parse_moment_ignores_blank_values():
    assert parse_moment(None) is None
    assert parse_moment("   ") is None


def test_parse_moment_rejects_garbage():
    with pytest.raises(HTTPException) as excinfo:
        parse_moment("last tuesday")
    assert excinfo.value.status_code == 422


# -- multi-value params ------------------------------------------------------
def test_csv_accepts_repeated_and_comma_joined_values():
    assert _csv(["Lahore", "Karachi,Islamabad"]) == ("Lahore", "Karachi", "Islamabad")


def test_csv_dedupes_case_insensitively_and_drops_blanks():
    assert _csv(["Lahore", "lahore", " ", ""]) == ("Lahore",)


def test_csv_of_nothing_is_empty():
    assert _csv(None) == ()
    assert _csv([]) == ()


# -- page envelope -----------------------------------------------------------
def test_page_reports_total_pages_and_more():
    page = LeadPage(items=[{}] * 25, total=51, page=1, page_size=25).to_dict()

    assert page["totalPages"] == 3
    assert page["hasMore"] is True
    assert page["pageSize"] == 25


def test_last_page_has_no_more():
    page = LeadPage(items=[{}], total=51, page=3, page_size=25).to_dict()

    assert page["hasMore"] is False


def test_empty_result_still_reports_one_page():
    page = LeadPage(items=[], total=0, page=1, page_size=DEFAULT_PAGE_SIZE).to_dict()

    assert page["totalPages"] == 1
    assert page["hasMore"] is False


# -- derivations backing the city / property-type filters --------------------
@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("DHA Phase 6, Lahore", "Lahore"),
        ("Clifton , Karachi", "Karachi"),
        ("Lahore", "Lahore"),
        ("Lahore Cantt", "Lahore"),
        # Rightmost known city wins: these read as roads/societies, not as their namesake city.
        ("Multan Road, Lahore", "Lahore"),
        ("Karachi Company, Islamabad", "Islamabad"),
        ("", None),
        (None, None),
    ],
)
def test_derive_city(location, expected):
    assert derive_city(location) == expected


@pytest.mark.parametrize(
    "location",
    [
        # Real extracted locations that named no city. Guessing from these is what filled the
        # city filter with "sector C" and "DHA Phase 3 commercial"; they must resolve to
        # nothing instead, and surface as "Unknown".
        "Bahria Town, sector C",
        "Johar Town near Emporium",
        "DHA Phase 3 commercial",
        "Model Town",
    ],
)
def test_derive_city_returns_nothing_for_unrecognised_locations(location):
    assert derive_city(location) is None


@pytest.mark.parametrize(
    ("payload", "texts", "expected"),
    [
        ({"propertyType": "flat"}, (), "Apartment"),
        ({}, ("10 Marla House in DHA",), "House"),
        ({}, ("5 marla residential plot",), "Plot"),
        ({}, ("Ground floor shop for sale",), "Commercial"),
        ({}, ("Upper portion 3 bed for rent",), "House"),
        ({}, ("Something entirely unrelated",), None),
        (None, (None, ""), None),
    ],
)
def test_derive_property_type(payload, texts, expected):
    assert derive_property_type(payload, texts) == expected


def test_provider_category_beats_free_text():
    """The source's own label is more trustworthy than keyword matching on a title."""
    assert derive_property_type({"category": "Apartment"}, ("Plot for sale",)) == "Apartment"
