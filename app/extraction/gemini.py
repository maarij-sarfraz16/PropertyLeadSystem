"""Gemini extractor. Uses `response_schema` so the model returns JSON that already matches
`ExtractedLead` (google-genai parses it into the pydantic model for us).

Two-tier: run the cheap model first; if its confidence is below the threshold, escalate the
same post to the stronger model once. Keeps cost low while catching the ambiguous tail.
"""
from __future__ import annotations

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.extraction.base import Extractor
from app.extraction.schema import ExtractedLead

_SYSTEM = (
    "You extract structured real estate lead data from short online property posts written in "
    "English, Urdu, or Roman-Urdu (Pakistani market). Convert prices to a plain number: 'lakh' "
    "= 100000, 'crore' = 10000000. Use PKR as currency unless another is stated. If the post is "
    "not a genuine property listing (blog, ad, unrelated), set is_property_listing to false. "
    "Report honest confidence between 0 and 1."
)


class GeminiExtractor(Extractor):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey "
                "and put it in .env."
            )
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.extraction_model
        self._escalation_model = settings.escalation_model
        self._threshold = settings.extraction_confidence_threshold

    def extract(self, text: str) -> ExtractedLead:
        result = self._call(self._model, text)
        if result.confidence < self._threshold and self._escalation_model != self._model:
            result = self._call(self._escalation_model, text)
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _call(self, model: str, text: str) -> ExtractedLead:
        resp = self._client.models.generate_content(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                response_mime_type="application/json",
                response_schema=ExtractedLead,
                temperature=0.0,
            ),
        )
        parsed = resp.parsed
        if isinstance(parsed, ExtractedLead):
            return parsed
        # Fallback if the SDK returned raw JSON text instead of a parsed model.
        return ExtractedLead.model_validate_json(resp.text)
