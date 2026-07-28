"""Field normalization helpers. Phone normalization matters early: E.164 phone is the
strongest dedup key in Phase 2, so we store it in canonical form from Phase 1a.
"""
from __future__ import annotations

import phonenumbers

DEFAULT_REGION = "PK"


def normalize_phone(raw: str | None, region: str = DEFAULT_REGION) -> str | None:
    """Return an E.164 phone (e.g. +923001234567) or None if unparseable.

    Tolerant of local formats like '0300-1234567', '042 35551234', '+92 321 9876543'.
    """
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
