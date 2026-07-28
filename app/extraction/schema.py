"""Structured shape the LLM must return. Reused as the Gemini `response_schema` and as the
validation model, so the extractor cannot drift from the DB columns.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    buy = "buy"
    sell = "sell"
    rent = "rent"
    wanted = "wanted"
    unknown = "unknown"


class SellerType(str, Enum):
    owner = "owner"
    agent = "agent"
    unknown = "unknown"


class ExtractedLead(BaseModel):
    is_property_listing: bool = Field(
        description="True only if this is a genuine property listing (not a blog, ad, or noise)."
    )
    intent: Intent = Field(default=Intent.unknown)
    location_text: str | None = Field(default=None, description="Area / society / city as written.")
    price: float | None = Field(default=None, description="Numeric price in the currency below.")
    currency: str | None = Field(default=None, description="e.g. PKR.")
    area_value: float | None = Field(default=None)
    area_unit: str | None = Field(default=None, description="marla | kanal | sqft | sqyd.")
    bedrooms: int | None = Field(default=None)
    seller_type: SellerType = Field(default=SellerType.unknown)
    contact_phone: str | None = Field(default=None, description="Raw phone digits as written.")
    contact_name: str | None = Field(default=None)
    description: str | None = Field(default=None, description="One-line summary of the listing.")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Model confidence in this extraction, 0 to 1."
    )
