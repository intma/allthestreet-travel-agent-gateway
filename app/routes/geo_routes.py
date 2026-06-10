"""
GEO routes — expose Schema.org JSON-LD so Gemini and search crawlers can
discover, parse, and cite AllTheStreet places.

Endpoints:
  GET /geo/spot/{spot_id}.jsonld   -> JSON-LD @graph for one spot
  GET /geo/spots.jsonld            -> ItemList of spots (page)
  GET /robots.txt                  -> allow Gemini/Google/OpenAI crawlers
  GET /sitemap.xml                 -> spot URLs for indexing
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from app.config import settings
from app.content.faq import demo_faq as _demo_faq
from app.data.repository import SpotRepository
from app.geo import jsonld

router = APIRouter(tags=["geo"])
repo = SpotRepository()


@router.get("/geo/spot/{spot_id}.jsonld")
async def geo_spot(spot_id: int):
    spot = await repo.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail=f"spot {spot_id} not found")
    graph = jsonld.build_full_graph(spot, qa_pairs=_demo_faq(spot))
    return Response(
        content=__import__("json").dumps(graph, ensure_ascii=False, indent=2),
        media_type="application/ld+json; charset=utf-8",
    )


@router.get("/geo/spots.jsonld")
async def geo_spots(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    search: str | None = None,
):
    total, spots = await repo.list_spots(page=page, page_size=page_size, search=search)
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "url": jsonld.spot_canonical_url(s),
            "item": jsonld.build_place_jsonld(s),
        }
        for i, s in enumerate(spots)
    ]
    doc = {
        "@context": jsonld.SCHEMA,
        "@type": "ItemList",
        "numberOfItems": total,
        "itemListElement": items,
    }
    return Response(
        content=__import__("json").dumps(doc, ensure_ascii=False, indent=2),
        media_type="application/ld+json; charset=utf-8",
    )


@router.get("/robots.txt")
async def robots() -> Response:
    # Explicitly allow generative-engine & search crawlers (project requirement).
    body = "\n".join([
        "User-agent: Googlebot",
        "Allow: /",
        "User-agent: Google-InspectionTool",
        "Allow: /",
        "User-agent: GPTBot",
        "Allow: /",
        "User-agent: OAI-SearchBot",
        "Allow: /",
        "User-agent: *",
        "Allow: /",
        "",
        f"Sitemap: {settings.PUBLIC_BASE_URL}/sitemap.xml",
        "",
    ])
    return Response(content=body, media_type="text/plain")


@router.get("/sitemap.xml")
async def sitemap() -> Response:
    total, spots = await repo.list_spots(page=1, page_size=50)
    urls = "".join(
        f"<url><loc>{jsonld.spot_canonical_url(s)}</loc></url>" for s in spots
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )
    return Response(content=xml, media_type="application/xml")
