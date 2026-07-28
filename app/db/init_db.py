"""Bootstrap the database for Phase 1a: enable pgvector, create tables, seed the pilot source.

Alembic migrations replace this in Phase 1b. For the pilot, create_all is enough to get a
runnable, testable slice fast.

    python -m app.db.init_db
"""
from __future__ import annotations

from sqlalchemy import select, text

from app.db.models import Base, Source
from app.db.session import get_engine, session_scope


def init_db() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    _seed_sources()
    print("DB initialized (pgvector enabled, tables created, sources seeded).")


def _seed_sources() -> None:
    """Seed the Phase 1a pilot source if absent."""
    with session_scope() as s:
        exists = s.scalar(select(Source).where(Source.name == "zameen"))
        if exists:
            return
        s.add(
            Source(
                name="zameen",
                type="portal",
                config={
                    # Apify actor + input filled when a token is provided; fixtures used otherwise.
                    "apify_actor_id": "",
                    "query": "Lahore property for sale",
                },
                scan_interval_seconds=900,
                enabled=True,
            )
        )


if __name__ == "__main__":
    init_db()
