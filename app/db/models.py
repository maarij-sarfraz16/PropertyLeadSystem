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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
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
    """One fetched post, stored verbatim.

    `url` is the canonical, deep listing URL on the origin platform and is written exactly as
    the adapter produced it — the pipeline never substitutes a search or homepage URL for a
    missing one (see `app.pipeline.urls`).
    """

    __tablename__ = "raw_posts"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external"),
        # The scanner filters each cycle's fetch against already-ingested ids; this index
        # keeps that lookup an index scan rather than a table scan as raw_posts grows.
        Index("ix_raw_posts_source_posted", "source_id", "posted_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String)  # platform's own post id
    url: Mapped[str | None] = mapped_column(String, nullable=True)  # deep link to the ad
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # untouched provider payload
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # free-text used for extraction
    posted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # publish time on the platform; drives the scan watermark
    scraped_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    source: Mapped[Source] = relationship(back_populates="raw_posts")


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        # Dedup gate: the pipeline computes a stable key per listing and lets the DB reject
        # the second writer, so concurrent scans cannot race a duplicate in.
        UniqueConstraint("dedup_key", name="uq_leads_dedup_key"),
        Index("ix_leads_first_seen", "first_seen_at"),
        Index("ix_leads_last_seen", "last_seen_at"),
        # The leads list filters on these two constantly and sorts by date within them.
        Index("ix_leads_city", "city"),
        Index("ix_leads_property_type", "property_type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)

    # Deep link to the origin advertisement, denormalized from the raw post so the dashboard
    # can render it without a join and it survives raw-post pruning.
    listing_url: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # Extracted (Phase 1a)
    intent: Mapped[str | None] = mapped_column(String, nullable=True)  # buy | sell | rent | wanted
    location_text: Mapped[str | None] = mapped_column(String, nullable=True)
    # Derived once at ingest from location_text / the listing payload (see
    # app.pipeline.classify). Persisted rather than computed at render time so the leads list
    # can filter, facet and paginate on them in SQL.
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    property_type: Mapped[str | None] = mapped_column(String, nullable=True)
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


class SavedSearch(Base):
    """A stored set of lead filters that alerts when new inventory matches it.

    `criteria` holds the **camelCase wire keys** the leads API already speaks (`city`,
    `sellerType`, `minScore`, ...), not the `LeadFilters` field names. That contract is shared
    by `list_leads`' signature and the dashboard's `leadQueryToSearchParams`, so a stored
    search converts to a querystring with no translation layer, and the criteria that fired an
    alert are literally the criteria the click-through list applies.

    Date filters are deliberately never stored here — see `app.notifications.criteria`.
    """

    __tablename__ = "saved_searches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    # Nullable: there is no auth yet, so an unowned "shared" search is legal.
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    criteria: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_realtime: Mapped[bool] = mapped_column(Boolean, default=True)
    # Surfaced in the UI so a search that can never match is visible rather than silently dead.
    last_matched_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    agent: Mapped[Agent | None] = relationship()

    __table_args__ = (Index("ix_saved_searches_enabled", "enabled"),)


class Notification(Base):
    """One delivered alert.

    The `(saved_search_id, lead_id)` unique index is what makes re-alerting structurally
    impossible — a retry, a restart or two overlapping cycles all collapse onto one row via
    `ON CONFLICT DO NOTHING`, the same "let the database reject the second writer" approach
    `leads.dedup_key` uses. It is partial so future notifications with no originating search
    (throttle notices, system messages) never collide with each other.
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    channel: Mapped[str] = mapped_column(String)  # dashboard | slack | whatsapp | webhook
    status: Mapped[str] = mapped_column(String, default="pending")
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    saved_search_id: Mapped[str | None] = mapped_column(
        ForeignKey("saved_searches.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped[Lead] = relationship()
    saved_search: Mapped[SavedSearch | None] = relationship()

    __table_args__ = (
        Index(
            "uq_notification_search_lead",
            "saved_search_id",
            "lead_id",
            unique=True,
            postgresql_where=text("saved_search_id IS NOT NULL"),
        ),
        Index("ix_notifications_unread", "read_at", "created_at"),
    )


class ScanState(Base):
    """Per-source watermark so the worker never reprocesses listings it has already seen.

    `last_posted_at` is the newest publish time successfully ingested. The next cycle only
    considers listings published after it, which keeps LLM calls proportional to genuinely
    new inventory rather than to page size.
    """

    __tablename__ = "scan_state"

    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    last_posted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_new_leads: Mapped[int] = mapped_column(Integer, default=0)

    source: Mapped[Source] = relationship()


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
