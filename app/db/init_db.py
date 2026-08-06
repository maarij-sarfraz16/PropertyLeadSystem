"""Bootstrap the database: enable pgvector, create tables, apply additive column migrations,
and seed the pilot source.

    python -m app.db.init_db

`create_all` never alters an existing table, so the additive migrations below are what let an
already-populated database pick up the columns the automated scanner needs (listing_url,
dedup_key, posted_at, the scan_state watermark table) without a drop-and-recreate. Each
statement is idempotent, so re-running this is always safe.

Alembic replaces this once the schema stops moving; until then this keeps the pilot runnable
with one command.
"""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.db.models import Base, Lead, LeadSource, Source
from app.db.session import get_engine, session_scope
from app.logging_config import configure_logging, get_logger
from app.pipeline.classify import derive_city, derive_property_type
from app.serializers import latest_raw_post

log = get_logger(__name__)

# Additive and idempotent. Ordered so indexes follow the columns they cover.
_MIGRATIONS: list[str] = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS listing_url VARCHAR",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS title TEXT",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS dedup_key VARCHAR",
    # Filter facets for the leads workspace. Backfilled below for pre-existing rows.
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS city VARCHAR",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS property_type VARCHAR",
    "CREATE INDEX IF NOT EXISTS ix_leads_city ON leads (city)",
    "CREATE INDEX IF NOT EXISTS ix_leads_property_type ON leads (property_type)",
    "ALTER TABLE raw_posts ADD COLUMN IF NOT EXISTS title TEXT",
    "ALTER TABLE raw_posts ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ",
    # Partial unique index: rows created before dedup existed have a NULL key and must not
    # collide with each other, while every new lead is still gated on uniqueness.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_dedup_key ON leads (dedup_key) "
    "WHERE dedup_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_leads_first_seen ON leads (first_seen_at)",
    "CREATE INDEX IF NOT EXISTS ix_leads_last_seen ON leads (last_seen_at)",
    "CREATE INDEX IF NOT EXISTS ix_raw_posts_source_posted ON raw_posts (source_id, posted_at)",
    # Saved-search alerts. `saved_searches` itself is created by create_all; these bring an
    # already-populated `notifications` table (created before alerts existed) up to date.
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS saved_search_id VARCHAR",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title VARCHAR",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS body TEXT",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ",
    # Partial, for the same reason as uq_leads_dedup_key: a notification with no originating
    # search (a throttle notice) must not collide with another one.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_search_lead "
    "ON notifications (saved_search_id, lead_id) WHERE saved_search_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_notifications_unread ON notifications (read_at, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_saved_searches_enabled ON saved_searches (enabled)",
]


def init_db() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    _apply_migrations()
    filled = backfill_lead_facets()
    _seed_sources()
    log.info("db.initialized", extra={"facets_backfilled": filled})
    print(
        "DB ready (pgvector enabled, tables created, migrations applied, "
        f"{filled} lead(s) backfilled, sources seeded)."
    )


def _apply_migrations() -> None:
    engine = get_engine()
    for statement in _MIGRATIONS:
        # Each in its own transaction: one failure must not roll back the others.
        with engine.begin() as conn:
            try:
                conn.execute(text(statement))
            except Exception as exc:
                log.warning("db.migration_skipped", extra={"sql": statement, "error": str(exc)})


def backfill_lead_facets(batch_size: int = 500, *, refresh: bool = False) -> int:
    """Populate `city` / `property_type` on leads that predate those columns.

    Runs in Python rather than as an UPDATE ... CASE so it uses the exact same derivation the
    pipeline uses (`app.pipeline.classify`) — a SQL copy of those rules would drift the moment
    either side changed, and the drift would show up as leads missing from a filtered page.

    Default pass only touches rows with no city yet, so re-running it is a no-op. `refresh`
    recomputes every row instead, which is how an improvement to the derivation rules reaches
    leads that were classified under the old ones.
    """
    filled = 0
    cursor = ""  # keyset over id: a refresh pass rewrites rows it has already visited
    while True:
        with session_scope() as session:
            stmt = (
                select(Lead)
                .where(Lead.id > cursor if refresh else Lead.city.is_(None))
                .order_by(Lead.id)
                .options(selectinload(Lead.sources).selectinload(LeadSource.raw_post))
                .limit(batch_size)
            )
            leads = session.scalars(stmt).all()
            if not leads:
                return filled

            for lead in leads:
                raw_post = latest_raw_post(lead)
                # Always non-NULL, so the default pass cannot re-select the same row forever.
                lead.city = derive_city(lead.location_text) or "Unknown"
                lead.property_type = derive_property_type(
                    raw_post.raw_json if raw_post is not None else None,
                    (
                        raw_post.title if raw_post is not None else None,
                        raw_post.text if raw_post is not None else None,
                        lead.title,
                        lead.description,
                    ),
                )
                filled += 1

            cursor = leads[-1].id

        if len(leads) < batch_size:
            return filled


def _seed_sources() -> None:
    """Seed the pilot source if absent.

    `apify_actor_id` is deliberately left unset: with no actor configured the Zameen adapter
    uses its built-in web scraper, so a fresh install scans for real without any token.
    """
    with session_scope() as s:
        existing = s.scalar(select(Source).where(Source.name == "zameen"))
        if existing is not None:
            return
        s.add(
            Source(
                name="zameen",
                type="portal",
                config={"query": "Lahore property for sale"},
                scan_interval_seconds=900,
                enabled=True,
            )
        )
        log.info("source.seeded", extra={"source": "zameen"})


if __name__ == "__main__":
    import sys

    if "--refresh-facets" in sys.argv:
        # Reclassify every lead's city / property type under the current rules.
        configure_logging()
        print(f"Reclassified {backfill_lead_facets(refresh=True)} lead(s).")
    else:
        init_db()
