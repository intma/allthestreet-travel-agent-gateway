"""
UCP (Universal Commerce Protocol) schema.

UCP is the discovery layer: a normalized, machine-readable representation of
places and products that a generative agent (Gemini) can read, compare, and
recommend. This is intentionally a *commerce-discovery* shape — distinct from
the GEO/JSON-LD layer which targets search-engine semantic markup.

We keep the schema small, explicit, and stable. Multilingual fields carry KR /
EN / original variants so the agent can answer in the user's language.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UCPType(str, Enum):
    place = "Place"
    product = "Product"


class Availability(str, Enum):
    in_stock = "InStock"
    out_of_stock = "OutOfStock"
    limited = "LimitedAvailability"
    unknown = "Unknown"


class LocalizedText(BaseModel):
    """A value with language variants. `default` is what to show if unsure."""
    default: Optional[str] = None
    kr: Optional[str] = None
    en: Optional[str] = None
    original: Optional[str] = None  # e.g. Japanese source name


class GeoPoint(BaseModel):
    lat: float
    lng: float


class ExternalIds(BaseModel):
    allthestreet_spot_id: Optional[int] = None
    google_place_id: Optional[str] = None
    naver_place_id: Optional[str] = None


class RelatedVideo(BaseModel):
    url: str
    # Time-coded segment for Video-to-Place mapping (filled when available).
    start: Optional[str] = None  # "00:05"
    end: Optional[str] = None    # "00:15"


class Offer(BaseModel):
    """Commerce offer for a product/ticket attached to a place."""
    price: Optional[float] = None
    price_currency: str = "KRW"
    availability: Availability = Availability.unknown
    url: Optional[str] = None         # product/landing page
    checkout_deep_link: Optional[str] = None  # direct checkout (agentic action)
    seller: Optional[str] = None


class OpeningHours(BaseModel):
    day_of_week: str   # "Monday"
    opens: str         # "10:00"
    closes: str        # "21:30"


class UCPObject(BaseModel):
    """The core UCP discovery object."""
    id: str = Field(..., description="Stable UCP id, e.g. 'ats:spot:474'")
    type: UCPType
    name: LocalizedText
    description: Optional[LocalizedText] = None
    geo: Optional[GeoPoint] = None
    address: Optional[LocalizedText] = None
    telephone: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    availability: Availability = Availability.unknown
    opening_hours: list[OpeningHours] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)
    related_videos: list[RelatedVideo] = Field(default_factory=list)
    external_ids: Optional[ExternalIds] = None
    url: Optional[str] = None  # canonical page on this gateway


class UCPFeed(BaseModel):
    """A paginated feed of UCP objects."""
    version: str = "0.1"
    provider: str = "AllTheStreet"
    total: int = 0
    page: int = 1
    page_size: int = 10
    items: list[UCPObject] = Field(default_factory=list)


class UCPManifest(BaseModel):
    """Served at /.well-known/ucp.json — how an agent discovers this provider."""
    version: str = "0.1"
    provider: str = "AllTheStreet"
    description: str = (
        "Short-form-video-driven curation of Korean places, food spots, and "
        "travel products. Discover places and bookable products via UCP."
    )
    endpoints: dict = Field(default_factory=dict)
    languages: list[str] = Field(default_factory=lambda: ["ko", "en", "ja"])
