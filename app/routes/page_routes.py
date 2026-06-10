"""
Content page routes (A).

  GET /p/{spot_id}   -> server-rendered HTML place page (with embedded JSON-LD)

This is the human + crawler landing page that Gemini rich-cards / search results
click through to. Reuses the same Spot data and JSON-LD as the GEO/UCP layers.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.content.faq import demo_faq
from app.data.repository import SpotRepository
from app.page.template import render_spot_page

router = APIRouter(tags=["page"])
repo = SpotRepository()


@router.get("/p/{spot_id}", response_class=HTMLResponse)
async def spot_page(spot_id: int) -> HTMLResponse:
    spot = await repo.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail=f"spot {spot_id} not found")
    html = render_spot_page(spot, qa_pairs=demo_faq(spot))
    return HTMLResponse(content=html)
