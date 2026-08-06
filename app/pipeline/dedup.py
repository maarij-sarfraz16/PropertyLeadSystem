"""Duplicate detection.

Three layers, cheapest first:

1. **Already ingested** — the (source, external_id) pair exists in `raw_posts`. This is the
   common case at a 30-second cadence: nearly every listing on a search page was seen last
   cycle. Caught with one indexed query per cycle, before any LLM call, so re-scanning the
   same page costs nothing.

2. **Same property, different ad** — a stable content key over the seller's phone, the price,
   and the size. Agencies routinely repost the same property under a fresh ad id, and the same
   property appears across search paths; those should collapse onto one lead.

3. **Race protection** — the key is written to `leads.dedup_key`, which carries a UNIQUE
   constraint. If two workers (or two cycles) reach the same listing at once, the database
   rejects the loser rather than admitting a duplicate.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Lead, RawPost
from app.extraction.schema import ExtractedLead


def existing_external_ids(session: Session, source_id: str, external_ids: list[str]) -> set[str]:
    """Return the subset of `external_ids` already stored for this source.

    One query for the whole batch — not one per listing — so the per-cycle cost stays flat as
    the table grows.
    """
    if not external_ids:
        return set()
    rows = session.scalars(
        select(RawPost.external_id).where(
            RawPost.source_id == source_id, RawPost.external_id.in_(external_ids)
        )
    ).all()
    return set(rows)


def build_dedup_key(source_name: str, external_id: str, extracted: ExtractedLead) -> str:
    """Return a stable key identifying the underlying property.

    Prefers a content key (phone + price + size) so the same property reposted under a new ad
    id collapses onto the existing lead. Falls back to the ad's own identity when the listing
    is too thin to fingerprint — that is still correct, just less aggressive.
    """
    phone = (extracted.contact_phone or "").strip()
    price = extracted.price
    if phone and price:
        # Round area to the nearest whole unit: portals report slightly different conversions
        # for the same plot, and an exact float would defeat the match.
        area = f"{round(extracted.area_value)}{extracted.area_unit}" if extracted.area_value else ""
        beds = extracted.bedrooms if extracted.bedrooms is not None else ""
        raw = f"content|{phone}|{price:.0f}|{area}|{beds}"
    else:
        raw = f"ad|{source_name}|{external_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def find_duplicate_lead(session: Session, dedup_key: str) -> Lead | None:
    """Return the existing lead for this key, if any."""
    return session.scalar(select(Lead).where(Lead.dedup_key == dedup_key))
