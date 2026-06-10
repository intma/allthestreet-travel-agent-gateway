"""
Image proxy — serves Google Places photos without exposing the API key.

GET /img/{photo_reference}
  -> server fetches https://maps.googleapis.com/.../photo?...&key=SECRET
  -> follows Google's redirect to the actual image
  -> streams the image bytes back to the client

The client only ever sees /img/{ref}; the key stays on the server.
Responses are cached at the edge via Cache-Control for performance.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Response

from app.config import settings
from app.data.images import google_photo_url

router = APIRouter(tags=["image"])


@router.get("/img/{photo_reference}")
async def place_photo(photo_reference: str) -> Response:
    if not settings.GOOGLE_MAPS_API_KEY:
        # Misconfigured deployment — fail clearly rather than leaking anything.
        raise HTTPException(
            status_code=503,
            detail="image proxy not configured (GOOGLE_MAPS_API_KEY missing)",
        )

    url = google_photo_url(photo_reference)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream image error: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="photo not available")

    content_type = resp.headers.get("content-type", "image/jpeg")
    return Response(
        content=resp.content,
        media_type=content_type,
        headers={
            # Photos are immutable for a given reference; cache aggressively.
            "Cache-Control": "public, max-age=86400",
        },
    )
