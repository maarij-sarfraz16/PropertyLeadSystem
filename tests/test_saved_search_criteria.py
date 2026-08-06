"""Saved-search criteria: storage shape and defensive rehydration.

Database-free by design, like `test_leads_api.py`. What these protect is that a *stored* blob
— which outlives the code that wrote it — can never produce a broken or silently-dead search.
"""
from __future__ import annotations

from app.notifications.criteria import criteria_to_filters, is_matchable, normalize_criteria


def test_wire_keys_map_onto_lead_filters():
    """Stored criteria use the leads API's camelCase keys, not the dataclass field names."""
    filters = criteria_to_filters(
        {
            "search": " dha ",
            "city": ["Lahore", "Karachi"],
            "source": ["zameen"],
            "sellerType": ["owner"],
            "propertyType": ["House"],
            "status": ["new"],
            "minScore": 70,
            "maxScore": 95,
            "minPrice": 1_000_000,
            "maxPrice": 9_000_000,
            "minBedrooms": 3,
            "maxBedrooms": 5,
        }
    )

    assert filters.search == "dha"
    assert filters.cities == ("Lahore", "Karachi")
    assert filters.sources == ("zameen",)
    assert filters.seller_types == ("owner",)
    assert filters.property_types == ("House",)
    assert filters.statuses == ("new",)
    assert (filters.min_score, filters.max_score) == (70, 95)
    assert (filters.min_price, filters.max_price) == (1_000_000, 9_000_000)
    assert (filters.min_bedrooms, filters.max_bedrooms) == (3, 5)


def test_stored_dates_are_dropped_on_rehydrate():
    """The regression that would silently kill every saved search.

    The dashboard resolves date presets to absolute instants before sending them. If those
    were persisted and reapplied, a search saved with "today" would match only that day
    forever — going quiet the next morning with no error anywhere.
    """
    filters = criteria_to_filters(
        {"city": ["Lahore"], "dateFrom": "2026-01-01T00:00:00Z", "dateTo": "2026-01-02T00:00:00Z"}
    )
    assert filters.date_from is None
    assert filters.date_to is None
    assert filters.cities == ("Lahore",)


def test_normalize_strips_dates_and_presentation_keys():
    stored = normalize_criteria(
        {
            "city": ["Lahore"],
            "dateFrom": "2026-01-01T00:00:00Z",
            "dateTo": "2026-01-02T00:00:00Z",
            "sort": "newest",
            "page": 3,
            "pageSize": 50,
        }
    )
    assert stored == {"city": ["Lahore"]}


def test_unknown_and_malformed_keys_are_ignored_not_raised():
    """A blob written by a future (or past) build must never take the matching cycle down."""
    filters = criteria_to_filters(
        {"city": ["Lahore"], "someFutureFilter": ["x"], "minPrice": "not-a-number"}
    )
    assert filters.cities == ("Lahore",)
    assert filters.min_price is None


def test_none_and_empty_criteria_are_safe():
    assert criteria_to_filters(None).cities == ()
    assert criteria_to_filters({}).search is None
    assert normalize_criteria(None) == {}


def test_list_values_accept_scalars_and_csv_and_dedupe():
    """Mirrors how the query parser tolerates `?city=A&city=B` and `?city=A,B`."""
    assert normalize_criteria({"city": "Lahore"})["city"] == ["Lahore"]
    assert normalize_criteria({"city": "Lahore,Karachi"})["city"] == ["Lahore", "Karachi"]
    # Case-insensitive dedupe, so one predicate rather than two.
    assert normalize_criteria({"city": ["Lahore", "lahore"]})["city"] == ["Lahore"]


def test_empty_values_are_omitted_entirely():
    assert normalize_criteria({"search": "   ", "city": [], "minScore": None}) == {}


class TestIsMatchable:
    """The first layer of the storm guard: a search must actually narrow something."""

    def test_empty_is_not_matchable(self):
        assert is_matchable({}) is False
        assert is_matchable(None) is False

    def test_status_alone_is_not_matchable(self):
        """A new lead is always 'new' or 'incomplete', so a status filter can never make a
        search fire — it would be a search that looks configured but is permanently silent."""
        assert is_matchable({"status": ["reviewed"]}) is False

    def test_a_real_narrowing_filter_is_matchable(self):
        assert is_matchable({"city": ["Lahore"]}) is True
        assert is_matchable({"sellerType": ["owner"]}) is True
        assert is_matchable({"minPrice": 5_000_000}) is True
        assert is_matchable({"search": "dha"}) is True
        assert is_matchable({"minBedrooms": 3}) is True

    def test_presentation_only_keys_do_not_count(self):
        assert is_matchable({"sort": "newest", "page": 2, "pageSize": 50}) is False
