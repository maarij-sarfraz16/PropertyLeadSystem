"""Extraction service: picks the extractor, merges in facts the source already knows.

Two concerns live here so neither the worker nor the CLI has to repeat them.

**Resilience.** The LLM is the preferred extractor, but a quota error or an outage must not
stop lead production. On failure the service degrades to the heuristic extractor and logs the
reason; the pipeline keeps running and the resulting lead carries a lower confidence.

**Cost and accuracy.** Zameen's search payload already states price, area, bedrooms, location
and contact authoritatively. Overwriting those with a model's re-reading of the same ad is
both a regression in accuracy and a waste. So structured source facts win, and the model is
consulted for what the portal does not state: intent nuance, owner-vs-agent, and a summary.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.extraction.base import Extractor
from app.extraction.heuristic import HeuristicExtractor
from app.extraction.schema import ExtractedLead, Intent, SellerType
from app.logging_config import get_logger

log = get_logger(__name__)


class ExtractionService:
    """Resolves an extractor once, then extracts with fallback."""

    def __init__(self, extractor: Extractor | None = None) -> None:
        settings = get_settings()
        self._fallback = HeuristicExtractor()
        self._fallback_enabled = settings.extraction_fallback_enabled
        self._primary: Extractor | None = extractor
        self._primary_name = type(extractor).__name__ if extractor else "heuristic"

        if extractor is None and settings.extraction_enabled and settings.gemini_api_key:
            try:
                # Imported lazily so the system runs without the LLM SDK configured.
                from app.extraction.gemini import GeminiExtractor

                self._primary = GeminiExtractor()
                self._primary_name = "gemini"
            except Exception as exc:  # pragma: no cover - depends on env
                log.warning(
                    "extraction.primary_unavailable",
                    extra={"error": str(exc), "fallback": "heuristic"},
                )

    @property
    def extractor_name(self) -> str:
        return self._primary_name

    def extract(self, text: str, facts: dict[str, Any] | None = None) -> ExtractedLead:
        """Extract structured lead data, then overlay authoritative source facts."""
        extracted, used = self._extract_raw(text)
        merged = self._merge_facts(extracted, facts or {})
        log.info(
            "extraction.completed",
            extra={
                "extractor": used,
                "is_listing": merged.is_property_listing,
                "intent": merged.intent.value,
                "confidence": round(merged.confidence, 2),
            },
        )
        return merged

    # -- internals -----------------------------------------------------------
    def _extract_raw(self, text: str) -> tuple[ExtractedLead, str]:
        if self._primary is None:
            return self._fallback.extract(text), "heuristic"
        try:
            return self._primary.extract(text), self._primary_name
        except Exception as exc:
            if not self._fallback_enabled:
                raise
            log.warning(
                "extraction.failed",
                extra={"extractor": self._primary_name, "error": str(exc), "fallback": "heuristic"},
            )
            return self._fallback.extract(text), "heuristic"

    @staticmethod
    def _merge_facts(extracted: ExtractedLead, facts: dict[str, Any]) -> ExtractedLead:
        """Source facts override model output; model fills the gaps the source leaves."""
        if not facts:
            return extracted

        data = extracted.model_dump()
        for field in (
            "location_text",
            "price",
            "currency",
            "area_value",
            "area_unit",
            "bedrooms",
            "contact_phone",
            "contact_name",
        ):
            value = facts.get(field)
            if value not in (None, "", []):
                data[field] = value

        if facts.get("intent"):
            data["intent"] = Intent(facts["intent"])
        # Only upgrade seller_type from the source; never downgrade a confident model read
        # of "direct owner, no agents" just because an agency block was attached to the ad.
        unknown_seller = (None, SellerType.unknown, "unknown")
        if facts.get("seller_type") and data.get("seller_type") in unknown_seller:
            data["seller_type"] = SellerType(facts["seller_type"])

        return ExtractedLead.model_validate(data)


_service: ExtractionService | None = None


def get_extraction_service() -> ExtractionService:
    """Process-wide singleton.

    The Gemini client holds connection state; constructing one per scan cycle would leak
    sockets at a 30-second cadence.
    """
    global _service
    if _service is None:
        _service = ExtractionService()
    return _service
