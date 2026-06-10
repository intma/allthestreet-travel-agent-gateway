"""
MCP server — exposes AllTheStreet data to Gemini (and any MCP client) as tools.

This is the "connection / context" layer. While GEO (JSON-LD) and UCP make data
*discoverable*, MCP lets an agent *actively query* it during a conversation:

  - search_spots        : find places by keyword / region / category
  - get_spot_detail     : full detail for one place (geo, hours, ids, videos)
  - list_recent_spots   : a sample of curated places

Tools reuse the same read-only SpotRepository as the GEO/UCP layers, so all
three layers stay consistent. The MCP app is mounted into the FastAPI service
(see app/main.py), so the whole gateway deploys as ONE Cloud Run service.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.config import settings
from app.data.repository import Spot, SpotRepository
from app.ucp.adapter import spot_to_ucp


def _build_transport_security() -> TransportSecuritySettings:
    """
    By default FastMCP only accepts localhost (DNS-rebinding protection), which
    rejects Cloud Run's *.run.app host with HTTP 421. We widen the allowlist
    from config. MCP_ALLOWED_HOSTS="*" disables host checking entirely, which is
    acceptable here because the MCP surface is public and strictly read-only.
    """
    raw = settings.MCP_ALLOWED_HOSTS.strip()
    if raw == "*" or not raw:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"],
            allowed_origins=["*"],
        )
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    origins = []
    for h in hosts:
        origins.append(f"https://{h}")
        origins.append(f"http://{h}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


mcp = FastMCP("allthestreet")
# We mount this app at /mcp in main.py, so the server's own path must be root
# to avoid a doubled /mcp/mcp path.
mcp.settings.streamable_http_path = "/"
# Allow the deployed host (Cloud Run *.run.app), otherwise MCP returns 421.
mcp.settings.transport_security = _build_transport_security()
_repo = SpotRepository()


def _spot_summary(spot: Spot, lang: str = "ko") -> dict[str, Any]:
    """Compact, language-aware view for tool results."""
    name = (
        spot.name_kr if lang == "ko"
        else spot.name_en if lang == "en"
        else spot.display_name
    ) or spot.display_name
    addr = spot.address_kr if lang == "ko" else (spot.address_en or spot.address_kr)
    return {
        "spot_id": spot.spot_id,
        "name": name,
        "address": addr,
        "lat": spot.lat,
        "lng": spot.lng,
        "google_place_id": spot.google_place_id,
        "url": f"https://gateway.allthestreet.com/ucp/spot/{spot.spot_id}",
    }


@mcp.tool()
async def search_spots(
    keyword: str = "",
    limit: int = 5,
    lang: str = "ko",
) -> list[dict[str, Any]]:
    """
    Search AllTheStreet curated places by keyword (name or address).

    Args:
        keyword: search term, e.g. "성수동 카페" or "부산 빵집". Empty = recent.
        limit: max results (1-20).
        lang: response language for name/address ("ko", "en").

    Returns a list of compact place summaries (id, name, address, coordinates,
    Google Place ID, and a UCP detail URL).
    """
    limit = max(1, min(limit, 20))
    _, spots = await _repo.list_spots(page=1, page_size=limit, search=keyword or None)
    return [_spot_summary(s, lang) for s in spots]


@mcp.tool()
async def get_spot_detail(spot_id: int, lang: str = "ko") -> Optional[dict[str, Any]]:
    """
    Get full detail for a single place, as a UCP object: multilingual name &
    address, geo coordinates, opening hours, availability, related short-form
    videos, and external ids (Google/Naver Place IDs).

    Args:
        spot_id: AllTheStreet spot id.
        lang: preferred language hint (the UCP object carries all variants).
    """
    spot = await _repo.get_spot(spot_id)
    if not spot:
        return None
    return spot_to_ucp(spot).model_dump()


@mcp.tool()
async def list_recent_spots(limit: int = 5, lang: str = "ko") -> list[dict[str, Any]]:
    """
    List a sample of recently curated AllTheStreet places.

    Args:
        limit: max results (1-20).
        lang: response language for name/address.
    """
    limit = max(1, min(limit, 20))
    _, spots = await _repo.list_spots(page=1, page_size=limit)
    return [_spot_summary(s, lang) for s in spots]
