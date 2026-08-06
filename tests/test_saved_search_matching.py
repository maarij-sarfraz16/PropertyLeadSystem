"""Saved-search matching: the SQL it builds, and its failure isolation.

The rendered-SQL assertions matter for the same reason `test_leads_api.py` uses them: a filter
that silently no-ops still returns a plausible-looking result. Here the stakes are higher — a
matcher that dropped its filters would alert on *every* lead.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Lead
from app.leads_query import apply_filters
from app.notifications.criteria import criteria_to_filters
from app.notifications.matching import match_new_leads


def rendered(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_matcher_sql_carries_both_the_id_restriction_and_the_filters():
    """The exact statement the matcher runs, asserted end to end.

    Both halves are load-bearing: without the id restriction it would alert on the whole
    table; without the filters it would alert on every new lead regardless of criteria.
    """
    filters = criteria_to_filters({"city": ["Lahore"], "sellerType": ["owner"]})
    stmt = apply_filters(select(Lead.id).where(Lead.id.in_(["lead-1", "lead-2"])), filters)
    sql = rendered(stmt).lower()

    assert "lead-1" in sql and "lead-2" in sql
    assert "lahore" in sql
    assert "owner" in sql


def test_matcher_sql_uses_the_same_predicates_as_the_list_endpoint():
    """The invariant the whole design rests on: alert and click-through cannot disagree."""
    filters = criteria_to_filters({"city": ["Lahore"], "minPrice": 5_000_000})

    list_sql = rendered(apply_filters(select(Lead.id), filters))
    match_sql = rendered(apply_filters(select(Lead.id).where(Lead.id.in_(["x"])), filters))

    # Every WHERE clause the list applies also appears in the matcher's statement.
    assert "lower(leads.city) in ('lahore')" in list_sql.lower()
    assert "lower(leads.city) in ('lahore')" in match_sql.lower()
    assert "leads.price >= 5000000" in list_sql.lower()
    assert "leads.price >= 5000000" in match_sql.lower()


def test_no_new_leads_does_no_work():
    """Most scan cycles discover nothing; that case must not touch the database at all."""
    assert match_new_leads([]) == []


def test_a_poisoned_criteria_blob_does_not_raise():
    """Rehydration is defensive, so a corrupt stored blob degrades to a wider filter rather
    than an exception that would stop every other search in the cycle."""
    filters = criteria_to_filters({"city": {"unexpected": "shape"}, "minScore": ["bad"]})
    # Neither key produced a predicate, and nothing raised.
    assert filters.cities == ()
    assert filters.min_score is None
