"""ORM models. Schema-forward: `leads` carries every field dedup (Phase 2) and scoring
(Phase 2) will need — phone, photos, seller_type, embedding — even though Phase 1a only
populates extraction output. Avoids migration churn later.
"""
from __future__ import annotations

import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Embedding dim for sentence-transformers all-MiniLM-L6-v2 (used in Phase 2 dedup).
EMBEDDING_DIM = 384


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)  # e.g. "zameen"
    type: Mapped[str] = mapped_column(String)  # portal | marketplace | group | social
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # actor id, query, area filters
    scan_interval_seconds: Mapped[int] = mapped_column(Integer, default=900)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    raw_posts: Mapped[list[RawPost]] = relationship(back_populates="source")


class RawPost(Base):
    __tablename__ = "raw_posts"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String)  # platform's own post id
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # untouched provider payload
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # free-text used for extraction
    scraped_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    source: Mapped[Source] = relationship(back_populates="raw_posts")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)

    # Extracted (Phase 1a)
    intent: Mapped[str | None] = mapped_column(String, nullable=True)  # buy | sell | rent | wanted
    location_text: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_unit: Mapped[str | None] = mapped_column(String, nullable=True)  # marla | kanal | sqft
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # owner | agent | unknown
    seller_type: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)  # E.164
    contact_name: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Populated in Phase 2 (dedup + scoring). Present now to avoid later migrations.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    primary_photo_phash: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="new")  # new | reviewed | notified | ...

    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    sources: Mapped[list[LeadSource]] = relationship(back_populates="lead")
    photos: Mapped[list[Photo]] = relationship(back_populates="lead")


class LeadSource(Base):
    """Join: one canonical lead links many source posts (dedup collapses duplicates here)."""

    __tablename__ = "lead_sources"
    __table_args__ = (UniqueConstraint("lead_id", "raw_post_id", name="uq_lead_rawpost"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    raw_post_id: Mapped[str] = mapped_column(ForeignKey("raw_posts.id"))

    lead: Mapped[Lead] = relationship(back_populates="sources")
    raw_post: Mapped[RawPost] = relationship()


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    url: Mapped[str] = mapped_column(String)
    phash: Mapped[str | None] = mapped_column(String, nullable=True)  # Phase 2 dedup

    lead: Mapped[Lead] = relationship(back_populates="photos")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    channel: Mapped[str] = mapped_column(String)  # dashboard | slack | whatsapp | webhook
    status: Mapped[str] = mapped_column(String, default="pending")
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
