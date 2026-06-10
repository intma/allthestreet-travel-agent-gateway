"""
Image handling.

The upstream `images` field is mixed:
  - real URLs (e.g. https://storage.googleapis.com/kmukbang_images/...) -> use as-is
  - Google Places photo_reference tokens (e.g. "AUc7tX...")              -> proxy

For photo_reference tokens we DO NOT emit a Google URL with the API key in it.
Instead we emit a URL pointing back at THIS gateway's /img/{ref} proxy, which
fetches the bytes server-side with the key kept secret.
"""

from __future__ import annotations

from app.config import settings


def is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def public_image_url(value: str) -> str:
    """
    Map a raw upstream image value to a client-safe URL.
    - real URL  -> returned unchanged
    - photo_ref -> gateway proxy URL (no key exposed)
    """
    if not value:
        return value
    if is_http_url(value):
        return value
    # Treat as Google Places photo_reference token.
    return f"{settings.PUBLIC_BASE_URL}/img/{value}"


def google_photo_url(photo_reference: str) -> str:
    """Server-side Google Places Photo URL (contains the secret key)."""
    return (
        "https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={settings.PLACE_PHOTO_MAX_WIDTH}"
        f"&photo_reference={photo_reference}"
        f"&key={settings.GOOGLE_MAPS_API_KEY}"
    )
