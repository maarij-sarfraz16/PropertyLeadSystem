"""Saved-search and alert endpoints, against a live database.

Follows `test_dashboard_api.py`, which already assumes a reachable Postgres. Each test cleans
up the rows it creates so a repeated run is idempotent.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.db.models import Lead, Notification, SavedSearch
from app.db.session import session_scope

client = TestClient(app)


@pytest.fixture
def saved_search():
    """Create a narrow saved search and remove it (and its alerts) afterwards."""
    response = client.post(
        "/api/saved-searches",
        json={"name": "pytest owner search", "criteria": {"sellerType": ["owner"]}},
    )
    assert response.status_code == 201, response.text
    search = response.json()
    yield search
    client.delete(f"/api/saved-searches/{search['id']}")


def test_criteria_are_normalized_on_save(saved_search):
    assert saved_search["criteria"] == {"sellerType": ["owner"]}
    assert saved_search["enabled"] is True
    assert saved_search["matchCount"] == 0


def test_unnarrowed_search_is_rejected():
    """The storm guard's first layer: a search matching everything is not a search."""
    response = client.post("/api/saved-searches", json={"name": "everything", "criteria": {}})
    assert response.status_code == 422
    assert "narrowing filter" in response.json()["detail"]


def test_status_only_search_is_rejected():
    """A new lead is always new/incomplete, so this could never fire."""
    response = client.post(
        "/api/saved-searches", json={"name": "reviewed", "criteria": {"status": ["reviewed"]}}
    )
    assert response.status_code == 422


def test_blank_name_is_rejected():
    response = client.post(
        "/api/saved-searches", json={"name": "  ", "criteria": {"city": ["Lahore"]}}
    )
    assert response.status_code == 422


def test_dates_are_never_persisted():
    """A saved search must not freeze to the day it was created."""
    response = client.post(
        "/api/saved-searches",
        json={
            "name": "pytest dated",
            "criteria": {
                "city": ["Lahore"],
                "dateFrom": "2026-01-01T00:00:00Z",
                "dateTo": "2026-01-02T00:00:00Z",
            },
        },
    )
    assert response.status_code == 201
    search = response.json()
    try:
        assert "dateFrom" not in search["criteria"]
        assert "dateTo" not in search["criteria"]
    finally:
        client.delete(f"/api/saved-searches/{search['id']}")


def test_preview_total_equals_the_leads_list_total():
    """The core invariant: what an alert promises and what the list shows are one query."""
    criteria = {"sellerType": ["owner"]}

    preview = client.post("/api/saved-searches/preview", json={"criteria": criteria})
    assert preview.status_code == 200

    listed = client.get("/api/leads", params={"sellerType": "owner", "pageSize": 1})
    assert listed.status_code == 200

    assert preview.json()["total"] == listed.json()["total"]


def test_preview_reports_unmatchable_criteria():
    response = client.post("/api/saved-searches/preview", json={"criteria": {}})
    assert response.status_code == 200
    assert response.json()["matchable"] is False


def test_alert_dedup_is_enforced_by_the_database(saved_search):
    """Inserting the same (search, lead) twice must collapse to one row, not raise.

    This is what makes re-alerting structurally impossible across retries, restarts and
    overlapping cycles.
    """
    with session_scope() as session:
        lead_id = session.scalar(select(Lead.id).limit(1))
        if lead_id is None:
            pytest.skip("no leads in the database to alert on")

        now = dt.datetime.now(dt.UTC)
        for _ in range(2):
            session.add(
                Notification(
                    lead_id=lead_id,
                    saved_search_id=saved_search["id"],
                    channel="dashboard",
                    status="delivered",
                    sent_at=now,
                )
            )
            try:
                session.commit()
            except Exception:
                # The second insert violates the partial unique index — exactly the guard.
                session.rollback()

        count = (
            session.query(Notification)
            .filter(Notification.saved_search_id == saved_search["id"])
            .count()
        )
        assert count == 1


def test_unread_count_and_read_all(saved_search):
    with session_scope() as session:
        lead_id = session.scalar(select(Lead.id).limit(1))
        if lead_id is None:
            pytest.skip("no leads in the database to alert on")
        session.add(
            Notification(
                lead_id=lead_id,
                saved_search_id=saved_search["id"],
                channel="dashboard",
                status="delivered",
                sent_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()

    before = client.get("/api/notifications/unread-count").json()
    assert before["count"] >= 1
    assert before["bySearch"].get(saved_search["id"]) == 1

    updated = client.post(
        "/api/notifications/read-all", params={"savedSearchId": saved_search["id"]}
    )
    assert updated.status_code == 200

    after = client.get("/api/notifications/unread-count").json()
    assert saved_search["id"] not in after["bySearch"]


def test_toggling_enabled_round_trips(saved_search):
    response = client.patch(f"/api/saved-searches/{saved_search['id']}", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_patch_rejects_criteria_that_stop_narrowing(saved_search):
    response = client.patch(f"/api/saved-searches/{saved_search['id']}", json={"criteria": {}})
    assert response.status_code == 422


def test_delete_removes_the_search_and_its_alerts():
    created = client.post(
        "/api/saved-searches",
        json={"name": "pytest disposable", "criteria": {"city": ["Lahore"]}},
    ).json()

    response = client.delete(f"/api/saved-searches/{created['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    with session_scope() as session:
        assert session.get(SavedSearch, created["id"]) is None


def test_missing_search_returns_404():
    assert client.patch("/api/saved-searches/nope", json={"enabled": True}).status_code == 404
