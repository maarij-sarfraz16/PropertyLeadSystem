"""Agents — who a saved search and its alerts belong to.

Deliberately minimal. There is no authentication in this system, so an agent is a label used
for grouping and assignment, not an identity: anyone can read anyone's alerts. Keeping the
model thin now means adding real auth later replaces this file rather than unpicking it.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.models import Agent
from app.db.session import session_scope

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _serialize(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "email": agent.email,
        "phone": agent.phone,
        "active": bool(agent.active),
    }


@router.get("")
def list_agents() -> dict:
    """Active agents first, then by name."""
    with session_scope() as session:
        agents = session.scalars(
            select(Agent).order_by(Agent.active.desc(), Agent.name.asc())
        ).all()
        return {"items": [_serialize(agent) for agent in agents]}


@router.post("", status_code=201)
def create_agent(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="An agent needs a name.")

    with session_scope() as session:
        agent = Agent(
            name=name,
            email=(payload.get("email") or None),
            phone=(payload.get("phone") or None),
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        return _serialize(agent)


@router.patch("/{agent_id}")
def update_agent(agent_id: str, payload: dict) -> dict:
    with session_scope() as session:
        agent = session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise HTTPException(status_code=422, detail="An agent needs a name.")
            agent.name = name
        for field in ("email", "phone"):
            if field in payload:
                setattr(agent, field, payload.get(field) or None)
        if "active" in payload:
            agent.active = bool(payload.get("active"))
        session.commit()
        session.refresh(agent)
        return _serialize(agent)
