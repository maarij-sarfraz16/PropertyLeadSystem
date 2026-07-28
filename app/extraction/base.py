"""Provider-agnostic extractor interface. Swapping Gemini for Claude/other = new class here,
no pipeline changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.extraction.schema import ExtractedLead


class Extractor(ABC):
    @abstractmethod
    def extract(self, text: str) -> ExtractedLead:  # pragma: no cover - interface
        ...
