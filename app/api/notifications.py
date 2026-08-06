"""The alert inbox: what matched, and what has not been looked at yet.

Rows carry the full lead summary rather than just an id, so the bell dropdown renders lead
cards from one request instead of a fetch per alert.
"""
from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Lead, LeadSource, Notification, RawPost
from app.db.session import session_scope
from app.serializers import lead_summary

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

MAX_LIMIT = 200


def _serialize(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "savedSearchId": notification.saved_search_id,
        "savedSearchName": (
            notification.saved_search.name
            if notification.saved_search
            else notification.title
        ),
        "agentId": notification.agent_id,
        "leadId": notification.lead_id,
        "title": notification.title,
        "body": notification.body,
        "status": notification.status,
        "channel": notification.channel,
        "readAt": notification.read_at.isoformat() if notification.read_at else None,
        "createdAt": notification.created_at.isoformat() if notification.created_at else None,
        "lead": lead_summary(notification.lead) if notification.lead else None,
    }


@router.get("")
def list_notifications(
    unreadOnly: Annotated[bool, Query()] = False,  # noqa: N803
    savedSearchId: Annotated[str | None, Query()] = None,  # noqa: N803
    agentId: Annotated[str | None, Query()] = None,  # noqa: N803
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> dict:
    """Recent alerts, newest first."""
    with session_scope() as session:
        stmt = (
            select(Notification)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .options(
                selectinload(Notification.saved_search),
                selectinload(Notification.lead).selectinload(Lead.photos),
                selectinload(Notification.lead)
                .selectinload(Lead.sources)
                .selectinload(LeadSource.raw_post)
                .selectinload(RawPost.source),
            )
        )
        if unreadOnly:
            stmt = stmt.where(Notification.read_at.is_(None))
        if savedSearchId:
            stmt = stmt.where(Notification.saved_search_id == savedSearchId)
        if agentId:
            stmt = stmt.where(Notification.agent_id == agentId)

        rows = session.scalars(stmt).all()
        return {"items": [_serialize(row) for row in rows]}


@router.get("/unread-count")
def unread_count(agentId: Annotated[str | None, Query()] = None) -> dict:  # noqa: N803
    """Total unread plus a per-search breakdown, in one grouped query.

    Polled by the bell as a safety net: the realtime stream drops events for a lagging client
    by design, so the count must not depend on having received every push.
    """
    with session_scope() as session:
        stmt = select(
            Notification.saved_search_id, func.count(Notification.id)
        ).where(Notification.read_at.is_(None))
        if agentId:
            stmt = stmt.where(Notification.agent_id == agentId)
        rows = session.execute(stmt.group_by(Notification.saved_search_id)).all()

        by_search = {search_id: count for search_id, count in rows if search_id}
        return {"count": sum(count for _, count in rows), "bySearch": by_search}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str) -> dict:
    with session_scope() as session:
        notification = session.get(Notification, notification_id)
        if notification is None:
            raise HTTPException(
                status_code=404, detail=f"Notification '{notification_id}' not found."
            )
        if notification.read_at is None:
            notification.read_at = dt.datetime.now(dt.UTC)
            session.commit()
        return {"id": notification_id, "readAt": notification.read_at.isoformat()}


@router.post("/read-all")
def mark_all_read(
    savedSearchId: Annotated[str | None, Query()] = None,  # noqa: N803
    agentId: Annotated[str | None, Query()] = None,  # noqa: N803
) -> dict:
    with session_scope() as session:
        query = session.query(Notification).filter(Notification.read_at.is_(None))
        if savedSearchId:
            query = query.filter(Notification.saved_search_id == savedSearchId)
        if agentId:
            query = query.filter(Notification.agent_id == agentId)
        updated = query.update(
            {Notification.read_at: dt.datetime.now(dt.UTC)}, synchronize_session=False
        )
        session.commit()
        return {"updated": int(updated)}
