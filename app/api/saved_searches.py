"""Saved-search CRUD — the criteria that turn new inventory into an alert.

A saved search is a persisted `LeadFilters`, stored in the leads API's own camelCase wire
shape so opening one replays it straight back into the list view. See
`app.notifications.criteria` for why dates are stripped and why criteria are whitelisted
rather than trusted.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.db.models import Agent, Lead, Notification, SavedSearch
from app.db.session import session_scope
from app.leads_query import count_matching
from app.notifications.criteria import criteria_to_filters, is_matchable, normalize_criteria

router = APIRouter(prefix="/api/saved-searches", tags=["saved-searches"])


def _serialize(search: SavedSearch, unread: int = 0) -> dict[str, Any]:
    return {
        "id": search.id,
        "name": search.name,
        "agentId": search.agent_id,
        "agentName": search.agent.name if search.agent else None,
        "criteria": search.criteria or {},
        "enabled": bool(search.enabled),
        "notifyRealtime": bool(search.notify_realtime),
        "matchCount": search.match_count or 0,
        "lastMatchedAt": search.last_matched_at.isoformat() if search.last_matched_at else None,
        "createdAt": search.created_at.isoformat() if search.created_at else None,
        "unreadCount": unread,
    }


def _validated_criteria(raw: Any) -> dict[str, Any]:
    """Normalize submitted criteria, rejecting a search that would match everything.

    The 422 is the first layer of the storm guard: at peak the scanner finds ~140 leads an
    hour, so an unnarrowed search would bury the inbox — and "tell me about every lead" is
    what the existing lead.created stream already does.
    """
    if raw is not None and not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="criteria must be an object.")
    criteria = normalize_criteria(raw)
    if not is_matchable(criteria):
        raise HTTPException(
            status_code=422,
            detail=(
                "This search has no narrowing filter, so it would alert on every new lead. "
                "Add a city, price range, property type, seller type or search term."
            ),
        )
    return criteria


def _require(session, search_id: str) -> SavedSearch:
    search = session.get(SavedSearch, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail=f"Saved search '{search_id}' not found.")
    return search


@router.get("")
def list_saved_searches(agentId: Annotated[str | None, Query()] = None) -> dict:  # noqa: N803
    """Every saved search, with its unread alert count."""
    with session_scope() as session:
        stmt = select(SavedSearch).order_by(SavedSearch.created_at.desc())
        if agentId:
            stmt = stmt.where(SavedSearch.agent_id == agentId)
        searches = session.scalars(stmt).all()

        # One grouped query for every count, rather than one per search.
        unread_rows = session.execute(
            select(Notification.saved_search_id, func.count(Notification.id))
            .where(Notification.read_at.is_(None), Notification.saved_search_id.is_not(None))
            .group_by(Notification.saved_search_id)
        ).all()
        unread = {search_id: count for search_id, count in unread_rows}

        return {"items": [_serialize(s, unread.get(s.id, 0)) for s in searches]}


@router.post("", status_code=201)
def create_saved_search(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A saved search needs a name.")

    criteria = _validated_criteria(payload.get("criteria"))

    with session_scope() as session:
        agent_id = payload.get("agentId") or None
        if agent_id and session.get(Agent, agent_id) is None:
            raise HTTPException(status_code=422, detail=f"Agent '{agent_id}' not found.")

        search = SavedSearch(
            name=name,
            agent_id=agent_id,
            criteria=criteria,
            notify_realtime=bool(payload.get("notifyRealtime", True)),
        )
        session.add(search)
        session.commit()
        session.refresh(search)
        return _serialize(search)


@router.patch("/{search_id}")
def update_saved_search(search_id: str, payload: dict) -> dict:
    with session_scope() as session:
        search = _require(session, search_id)

        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise HTTPException(status_code=422, detail="A saved search needs a name.")
            search.name = name
        if "criteria" in payload:
            search.criteria = _validated_criteria(payload.get("criteria"))
        if "agentId" in payload:
            agent_id = payload.get("agentId") or None
            if agent_id and session.get(Agent, agent_id) is None:
                raise HTTPException(status_code=422, detail=f"Agent '{agent_id}' not found.")
            search.agent_id = agent_id
        if "enabled" in payload:
            search.enabled = bool(payload.get("enabled"))
        if "notifyRealtime" in payload:
            search.notify_realtime = bool(payload.get("notifyRealtime"))

        session.commit()
        session.refresh(search)
        return _serialize(search)


@router.delete("/{search_id}")
def delete_saved_search(search_id: str) -> dict:
    with session_scope() as session:
        search = _require(session, search_id)
        # No FK cascade is configured, so its alerts are removed explicitly in the same
        # transaction — otherwise they would linger in the inbox pointing at nothing.
        removed = (
            session.query(Notification)
            .filter(Notification.saved_search_id == search_id)
            .delete(synchronize_session=False)
        )
        session.delete(search)
        session.commit()
        return {"deleted": True, "notificationsRemoved": int(removed)}


@router.post("/{search_id}/preview")
def preview_saved_search(search_id: str) -> dict:
    """How many existing leads this search matches.

    The honest way to answer "how noisy will this be?" before the alerts start arriving —
    and the real fix for alert storms, since it stops the too-broad search being saved at all.
    Runs the same `apply_filters` the matcher and the list endpoint run.
    """
    with session_scope() as session:
        search = _require(session, search_id)
        return _preview_for(session, search.criteria)


@router.post("/preview")
def preview_criteria(payload: dict) -> dict:
    """Preview criteria that have not been saved yet, for the save dialog."""
    criteria = normalize_criteria(payload.get("criteria"))
    with session_scope() as session:
        return {**_preview_for(session, criteria), "matchable": is_matchable(criteria)}


def _preview_for(session, criteria: dict[str, Any] | None) -> dict:
    filters = criteria_to_filters(criteria)
    total = count_matching(session, filters)

    # Rate is derived from the observed history window rather than assumed, so a quiet
    # database does not advertise an alarming number.
    earliest = session.scalar(select(func.min(Lead.first_seen_at)))
    latest = session.scalar(select(func.max(Lead.first_seen_at)))
    per_day = None
    if earliest and latest and total:
        days = max((latest - earliest).total_seconds() / 86400, 1 / 24)
        per_day = round(total / days, 1)

    return {"total": total, "estimatedPerDay": per_day}
