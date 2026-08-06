"""Match newly-discovered leads against saved searches and record the alerts.

The whole design rests on one decision: matching runs the **same SQL the leads list runs**.
A saved search is a persisted `LeadFilters`, and testing it is
`apply_filters(select(Lead.id).where(Lead.id.in_(new_ids)), filters)`. Reimplementing the
predicates in Python would be faster per row and would drift from the list endpoint the first
time either side changed — and an alert that disagrees with the list it links to is worse than
no alert.

Cost is bounded by inverting the obvious loop: one query per *search* over the cycle's new
ids, not one per (search, lead). `scan_max_new_per_cycle` caps the cycle at 10 leads, and most
cycles discover none at all — in which case this does no work whatsoever.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db.models import Lead, LeadSource, Notification, RawPost, SavedSearch
from app.db.session import session_scope
from app.leads_query import apply_filters
from app.logging_config import get_logger
from app.notifications.criteria import criteria_to_filters
from app.serializers import lead_summary

log = get_logger(__name__)


def match_new_leads(lead_ids: list[str]) -> list[dict[str, Any]]:
    """Alert every enabled saved search that matches any of `lead_ids`.

    Returns one detached dict per newly-created alert, ready to publish. Nothing ORM-bound
    escapes the session, so the caller can serialize freely after it closes.

    Never raises: a malformed criteria blob, a throttled search or a database hiccup on one
    search is logged and skipped so the others still deliver.
    """
    if not lead_ids:
        return []

    settings = get_settings()
    alerts: list[dict[str, Any]] = []

    with session_scope() as session:
        searches = session.scalars(
            select(SavedSearch).where(SavedSearch.enabled.is_(True))
        ).all()
        if not searches:
            return []

        summaries: dict[str, dict[str, Any]] = {}

        for search in searches:
            if len(alerts) >= settings.alerts_max_per_cycle:
                log.warning(
                    "alerts.cycle_capped",
                    # Not "created": logging reserves that name on LogRecord and raises.
                    extra={"cap": settings.alerts_max_per_cycle, "alerts_created": len(alerts)},
                )
                break
            try:
                new_alerts = _alert_for_search(session, search, lead_ids, summaries, settings)
            except Exception as exc:
                # One broken search must never silence the rest.
                session.rollback()
                log.exception(
                    "alerts.search_failed",
                    extra={"saved_search_id": search.id, "error": str(exc)},
                )
                continue
            alerts.extend(new_alerts)

    return alerts


def _alert_for_search(
    session: Session,
    search: SavedSearch,
    lead_ids: list[str],
    summaries: dict[str, dict[str, Any]],
    settings,
) -> list[dict[str, Any]]:
    """Match one saved search and persist its alerts. Returns the newly-created ones."""
    filters = criteria_to_filters(search.criteria)
    matched_ids = list(
        session.scalars(
            apply_filters(select(Lead.id).where(Lead.id.in_(lead_ids)), filters)
        ).all()
    )
    if not matched_ids:
        return []

    if _is_throttled(session, search, settings):
        return []

    # ON CONFLICT DO NOTHING against the partial unique index: re-running a cycle, or two
    # cycles racing, can only ever produce one alert per (search, lead). RETURNING tells us
    # which rows were genuinely new, and only those are worth pushing to a browser.
    now = dt.datetime.now(dt.UTC)
    stmt = (
        pg_insert(Notification)
        .values(
            [
                {
                    "lead_id": lead_id,
                    "saved_search_id": search.id,
                    "agent_id": search.agent_id,
                    "channel": "dashboard",
                    "status": "delivered",
                    "title": search.name,
                    "sent_at": now,
                    "created_at": now,
                }
                for lead_id in matched_ids
            ]
        )
        # `index_where` is required, not optional: the unique index is partial, and Postgres
        # will not infer a partial index from the column list alone.
        .on_conflict_do_nothing(
            index_elements=["saved_search_id", "lead_id"],
            index_where=Notification.saved_search_id.is_not(None),
        )
        .returning(Notification.id, Notification.lead_id)
    )
    created = session.execute(stmt).all()
    if not created:
        return []

    _load_summaries(session, [lead_id for _, lead_id in created], summaries)

    search.match_count = (search.match_count or 0) + len(created)
    search.last_matched_at = now
    session.commit()

    log.info(
        "alerts.created",
        extra={
            "saved_search_id": search.id,
            "saved_search": search.name,
            "matched": len(matched_ids),
            "alerts_created": len(created),
        },
    )

    return [
        {
            "id": notification_id,
            "savedSearchId": search.id,
            "savedSearchName": search.name,
            "agentId": search.agent_id,
            "notifyRealtime": bool(search.notify_realtime),
            "leadId": lead_id,
            "title": search.name,
            "createdAt": now.isoformat(),
            "readAt": None,
            "lead": summaries.get(lead_id),
        }
        for notification_id, lead_id in created
    ]


def _load_summaries(
    session: Session, lead_ids: list[str], summaries: dict[str, dict[str, Any]]
) -> None:
    """Fill `summaries` with the dashboard row shape for any id not already loaded.

    Cached across searches within a cycle: two saved searches matching the same lead cost one
    read, not two. Eager-loads the same relationships `_summarize` does, so the payload is
    complete once the session closes.
    """
    missing = [lead_id for lead_id in lead_ids if lead_id not in summaries]
    if not missing:
        return
    rows = session.scalars(
        select(Lead)
        .where(Lead.id.in_(missing))
        .options(
            selectinload(Lead.photos),
            selectinload(Lead.sources)
            .selectinload(LeadSource.raw_post)
            .selectinload(RawPost.source),
        )
    ).all()
    for lead in rows:
        summaries[lead.id] = lead_summary(lead)


def _is_throttled(session: Session, search: SavedSearch, settings) -> bool:
    """True when this search has already alerted its hourly allowance.

    Self-healing by construction: the window is a rolling count with no stored state, so a
    search that stops matching so broadly simply starts delivering again. One notice is
    recorded per episode to tell the user *why* their alerts went quiet.
    """
    cap = settings.alerts_max_per_search_per_hour
    if cap <= 0:
        return False

    window_start = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    recent = int(
        session.scalar(
            select(func.count(Notification.id)).where(
                Notification.saved_search_id == search.id,
                Notification.created_at >= window_start,
            )
        )
        or 0
    )
    if recent < cap:
        return False

    log.warning(
        "alerts.throttled",
        extra={"saved_search_id": search.id, "saved_search": search.name, "recent": recent},
    )
    _record_throttle_notice(session, search, recent)
    return True


def _record_throttle_notice(session: Session, search: SavedSearch, recent: int) -> None:
    """Tell the user their search is too broad — once per throttle episode, not per lead."""
    window_start = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    already = session.scalar(
        select(Notification.id).where(
            Notification.saved_search_id.is_(None),
            Notification.status == "throttled",
            Notification.title == search.name,
            Notification.created_at >= window_start,
        )
    )
    if already:
        return

    # Needs a lead_id (the column is NOT NULL), so it hangs off the most recent lead this
    # search alerted on — which is also the most useful one to open from the notice.
    last_lead_id = session.scalar(
        select(Notification.lead_id)
        .where(Notification.saved_search_id == search.id)
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    if not last_lead_id:
        return

    session.add(
        Notification(
            lead_id=last_lead_id,
            saved_search_id=None,
            agent_id=search.agent_id,
            channel="dashboard",
            status="throttled",
            title=search.name,
            body=(
                f"'{search.name}' matched {recent} leads in the last hour and has been paused "
                "until the hour rolls over. Narrow it — add a price range, a city, or an "
                "owner-only filter."
            ),
            sent_at=dt.datetime.now(dt.UTC),
        )
    )
    session.commit()
