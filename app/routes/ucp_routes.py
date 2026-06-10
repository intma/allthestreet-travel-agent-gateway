"""
UCP routes — the discovery API a generative agent reads.

  GET /.well-known/ucp.json    -> provider manifest (discovery entry point)
  GET /ucp/feed                -> paginated UCP feed (optional ?search=)
  GET /ucp/spot/{spot_id}      -> single UCP object
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.data.repository import SpotRepository
from app.ucp import adapter
from app.ucp.schema import UCPFeed, UCPManifest, UCPObject

router = APIRouter(tags=["ucp"])
repo = SpotRepository()


@router.get("/.well-known/ucp.json", response_model=UCPManifest)
async def ucp_manifest() -> UCPManifest:
    return adapter.build_manifest()


@router.get("/ucp/feed", response_model=UCPFeed)
async def ucp_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    search: str | None = None,
) -> UCPFeed:
    total, spots = await repo.list_spots(page=page, page_size=page_size, search=search)
    return UCPFeed(
        total=total,
        page=page,
        page_size=page_size,
        items=[adapter.spot_to_ucp(s) for s in spots],
    )


@router.get("/ucp/spot/{spot_id}", response_model=UCPObject)
async def ucp_spot(spot_id: int) -> UCPObject:
    spot = await repo.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail=f"spot {spot_id} not found")
    return adapter.spot_to_ucp(spot)
