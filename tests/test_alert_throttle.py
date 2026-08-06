"""The alert storm guard.

At peak the scanner discovers ~140 leads an hour. A saved search broad enough to match most
of them would bury the inbox within the hour, so delivery is capped per search on a rolling
window — and the user is told once why their alerts went quiet.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.db.models import Lead, Notification, SavedSearch
from app.db.session import session_scope
from app.notifications.matching import _is_throttled


class _Settings:
    def __init__(self, cap: int) -> None:
        self.alerts_max_per_search_per_hour = cap


ALERT_COUNT = 3


@pytest.fixture
def search_with_alerts():
    """A saved search carrying exactly ALERT_COUNT recent alerts.

    One alert per lead: the partial unique index on (saved_search_id, lead_id) means the same
    lead cannot be alerted twice for one search, which is the point of that index.
    """
    with session_scope() as session:
        lead_ids = list(session.scalars(select(Lead.id).limit(ALERT_COUNT)).all())
        if len(lead_ids) < ALERT_COUNT:
            pytest.skip(f"need {ALERT_COUNT} leads in the database to alert on")

        search = SavedSearch(name="pytest throttle", criteria={"city": ["Lahore"]})
        session.add(search)
        session.flush()

        now = dt.datetime.now(dt.UTC)
        for lead_id in lead_ids:
            session.add(
                Notification(
                    lead_id=lead_id,
                    saved_search_id=search.id,
                    channel="dashboard",
                    status="delivered",
                    created_at=now,
                    sent_at=now,
                )
            )
        session.commit()
        search_id = search.id

    yield search_id

    with session_scope() as session:
        session.query(Notification).filter(
            Notification.saved_search_id == search_id
        ).delete(synchronize_session=False)
        obj = session.get(SavedSearch, search_id)
        if obj:
            session.delete(obj)
        session.commit()


def test_under_the_cap_is_not_throttled(search_with_alerts):
    with session_scope() as session:
        search = session.get(SavedSearch, search_with_alerts)
        assert _is_throttled(session, search, _Settings(cap=ALERT_COUNT + 1)) is False


def test_at_the_cap_throttles(search_with_alerts):
    """The cap is inclusive: having already sent N in the window stops the N+1th."""
    with session_scope() as session:
        search = session.get(SavedSearch, search_with_alerts)
        assert _is_throttled(session, search, _Settings(cap=ALERT_COUNT)) is True


def test_a_zero_cap_disables_throttling(search_with_alerts):
    with session_scope() as session:
        search = session.get(SavedSearch, search_with_alerts)
        assert _is_throttled(session, search, _Settings(cap=0)) is False


def test_only_one_notice_per_throttle_episode(search_with_alerts):
    """The notice explains the silence; repeating it every cycle would be its own spam."""
    with session_scope() as session:
        search = session.get(SavedSearch, search_with_alerts)
        _is_throttled(session, search, _Settings(cap=1))
        _is_throttled(session, search, _Settings(cap=1))
        _is_throttled(session, search, _Settings(cap=1))

    with session_scope() as session:
        notices = (
            session.query(Notification)
            .filter(
                Notification.saved_search_id.is_(None),
                Notification.status == "throttled",
                Notification.title == "pytest throttle",
            )
            .all()
        )
        assert len(notices) == 1
        assert "Narrow it" in (notices[0].body or "")

        # Cleanup: these hang off no saved search, so the fixture cannot remove them.
        for notice in notices:
            session.delete(notice)
        session.commit()
