"""
Data access layer for the AllTheStreet Agent Gateway.

Strategy (confirmed during recon):
- The existing Flask backend (api.allthestreet.com) exposes
  /api_mukbang/get_spot_data_admin which returns spots WITH coordinates,
  google_place_id, thumbnail, detail (raw Google Places JSON), etc.
- That endpoint currently passes through when no Authorization header is sent
  (legacy-app compatibility), so we can read it without credentials.
- We never write. This gateway is strictly read-only.

We additionally NORMALIZE each spot: the `spot_detail` field contains a raw
Google Places payload (as a JSON string) that includes geometry, opening hours,
phone number, business status. We parse it into a clean internal shape that the
UCP adapter and GEO/JSON-LD builder can consume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.config import settings


# ---------------------------------------------------------------------------
# Internal normalized shape
# ---------------------------------------------------------------------------

@dataclass
class OpeningPeriod:
    day: int            # 0 = Sunday ... 6 = Saturday (Google convention)
    open_time: str      # "1000"
    close_time: str     # "2130"


@dataclass
class Spot:
    spot_id: int
    name: Optional[str] = None            # original (may be Japanese/etc.)
    name_kr: Optional[str] = None
    name_en: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    address_kr: Optional[str] = None
    address_en: Optional[str] = None
    google_place_id: Optional[str] = None
    naver_place_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    phone: Optional[str] = None
    business_status: Optional[str] = None
    category_id: Optional[int] = None
    region_id: Optional[int] = None
    product_id: Optional[int] = None
    opening_periods: list[OpeningPeriod] = field(default_factory=list)
    weekday_text: list[str] = field(default_factory=list)
    related_videos: list[str] = field(default_factory=list)
    videos: list = field(default_factory=list)  # list[VideoRef], attached on demand
    products: list = field(default_factory=list)  # list[ProductOffer], attached on demand
    raw_detail: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name_kr or self.name_en or self.name or f"Spot {self.spot_id}"


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_spot_detail(detail_str: Optional[str]) -> dict[str, Any]:
    """spot_detail is a JSON *string* holding a Google Places payload.

    Some rows store malformed/empty/non-object values (e.g. a bare string or
    already-parsed dict), so we always normalize to a dict.
    """
    if not detail_str:
        return {}
    if isinstance(detail_str, dict):
        return detail_str
    try:
        parsed = json.loads(detail_str)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_spot(raw: dict[str, Any]) -> Spot:
    detail = _parse_spot_detail(raw.get("spot_detail"))

    # Coordinates: prefer the explicit columns, fall back to Places geometry.
    lat = _safe_float(raw.get("spot_lat"))
    lng = _safe_float(raw.get("spot_lng"))
    geometry = detail.get("geometry")
    geom = (geometry.get("location") if isinstance(geometry, dict) else None) or {}
    if not isinstance(geom, dict):
        geom = {}
    if lat is None:
        lat = _safe_float(geom.get("lat"))
    if lng is None:
        lng = _safe_float(geom.get("lng"))

    # Opening hours from Places payload
    periods: list[OpeningPeriod] = []
    oh = detail.get("opening_hours")
    oh = oh if isinstance(oh, dict) else {}
    for p in oh.get("periods", []) or []:
        if not isinstance(p, dict):
            continue
        o = p.get("open") or {}
        c = p.get("close") or {}
        if "day" in o and o.get("time") and c.get("time"):
            periods.append(
                OpeningPeriod(day=o["day"], open_time=o["time"], close_time=c["time"])
            )

    # related videos: stored as a text field, may be comma/JSON; keep tolerant
    related: list[str] = []
    rv = raw.get("spot_relate_video")
    if rv:
        try:
            parsed = json.loads(rv)
            if isinstance(parsed, list):
                related = [str(x) for x in parsed]
            elif isinstance(parsed, str):
                related = [parsed]
        except (json.JSONDecodeError, TypeError):
            related = [s.strip() for s in str(rv).split(",") if s.strip()]

    return Spot(
        spot_id=raw.get("spot_id"),
        name=raw.get("spot_name"),
        name_kr=raw.get("spot_name_kr"),
        name_en=raw.get("spot_name_en"),
        lat=lat,
        lng=lng,
        address=raw.get("spot_address"),
        address_kr=raw.get("spot_address_kr"),
        address_en=raw.get("spot_address_en"),
        google_place_id=raw.get("spot_google_place_id"),
        naver_place_id=raw.get("spot_naver_place_id"),
        thumbnail_url=raw.get("spot_thumbnail_url"),
        phone=detail.get("formatted_phone_number"),
        business_status=detail.get("business_status"),
        category_id=raw.get("category_id"),
        region_id=raw.get("region_id"),
        product_id=raw.get("product_id"),
        opening_periods=periods,
        weekday_text=oh.get("weekday_text", []) or [],
        related_videos=related,
        raw_detail=detail,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

# Module-level spot index cache (shared across SpotRepository instances).
_SPOT_INDEX: dict[int, "Spot"] = {}
_SPOT_INDEX_AT: float = 0.0
_SPOT_INDEX_TTL: float = 12 * 3600.0  # 12 hours: full rebuild interval
_SPOT_INDEX_BUILDING: bool = False
# Serialize full rebuilds so concurrent cold-start requests don't each kick off
# their own (slow) full scan. The first acquirer builds; the rest reuse it.
_SPOT_INDEX_LOCK: Optional["asyncio.Lock"] = None


def _spot_index_lock() -> "asyncio.Lock":
    global _SPOT_INDEX_LOCK
    if _SPOT_INDEX_LOCK is None:
        import asyncio
        _SPOT_INDEX_LOCK = asyncio.Lock()
    return _SPOT_INDEX_LOCK


class SpotRepository:
    """Read-only access to spot data via the existing backend API."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 60.0):
        self.base_url = (base_url or settings.SOURCE_API_BASE).rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # No Authorization header on purpose (legacy passthrough, read-only).
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def list_spots(
        self, page: int = 1, page_size: int = 10, search: Optional[str] = None
    ) -> tuple[int, list[Spot]]:
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["searchKey"] = search
        data = await self._get("/api_mukbang/get_spot_data_admin", params)
        total = data.get("total", 0)
        spots = [normalize_spot(s) for s in data.get("spots", [])]
        return total, spots

    async def build_spot_index(self, force: bool = False) -> dict[int, Spot]:
        """Tier 1 — full rebuild of the {spot_id: Spot} index.

        The backend has no single-spot lookup (spot_id param is ignored), so we
        page the whole admin feed once and cache it. A lock serializes rebuilds:
        if several requests hit a cold cache at once, the first builds and the
        rest reuse the freshly built index instead of each re-scanning ~10k rows.
        """
        import time as _t
        global _SPOT_INDEX, _SPOT_INDEX_AT, _SPOT_INDEX_BUILDING
        async with _spot_index_lock():
            # Another coroutine may have finished building while we waited.
            if not force and _SPOT_INDEX and (_t.time() - _SPOT_INDEX_AT) < _SPOT_INDEX_TTL:
                return _SPOT_INDEX
            _SPOT_INDEX_BUILDING = True
            try:
                index: dict[int, Spot] = {}
                page, page_size = 1, 500
                while page <= 60:  # safety cap (~30k)
                    data = await self._get(
                        "/api_mukbang/get_spot_data_admin",
                        {"page": page, "pageSize": page_size},
                    )
                    rows = data.get("spots", []) if isinstance(data, dict) else []
                    if not rows:
                        break
                    for raw in rows:
                        sid = raw.get("spot_id")
                        if sid is not None:
                            index[int(sid)] = normalize_spot(raw)
                    if len(rows) < page_size:
                        break
                    page += 1
                if index:
                    _SPOT_INDEX = index
                    _SPOT_INDEX_AT = _t.time()
                return _SPOT_INDEX
            finally:
                _SPOT_INDEX_BUILDING = False

    async def _ensure_spot_index(self) -> dict[int, Spot]:
        """Return the cache. Empty -> build synchronously (first ever call).
        Expired but present -> serve the stale index IMMEDIATELY and refresh in
        the background (stale-while-revalidate), so TTL expiry never makes a
        user request wait for a ~10k-row rebuild."""
        import asyncio as _aio
        import time as _t
        if _SPOT_INDEX:
            if (_t.time() - _SPOT_INDEX_AT) >= _SPOT_INDEX_TTL:
                # Expired: kick off a background rebuild (the asyncio.Lock inside
                # build_spot_index prevents duplicate concurrent builds).
                _aio.create_task(self.build_spot_index(force=True))
            return _SPOT_INDEX
        return await self.build_spot_index()

    async def _lazy_find_spot(self, spot_id: int) -> Optional[Spot]:
        """Tier 3 — cache miss. A missing id is almost always a spot created
        AFTER the last full build. New spots get the largest ids, so we scan the
        most recent pages only (cheap) and add any found to the cache."""
        global _SPOT_INDEX
        page, page_size, max_recent_pages = 1, 100, 5
        for page in range(1, max_recent_pages + 1):
            data = await self._get(
                "/api_mukbang/get_spot_data_admin",
                {"page": page, "pageSize": page_size},
            )
            rows = data.get("spots", []) if isinstance(data, dict) else []
            if not rows:
                break
            found = None
            for raw in rows:
                sid = raw.get("spot_id")
                if sid is None:
                    continue
                sp = normalize_spot(raw)
                _SPOT_INDEX[int(sid)] = sp  # opportunistically warm the cache
                if int(sid) == spot_id:
                    found = sp
            if found is not None:
                return found
        return None

    async def get_spot(self, spot_id: int, with_videos: bool = True,
                       with_products: bool = True) -> Optional[Spot]:
        index = await self._ensure_spot_index()   # tier 1 (build if needed)
        spot = index.get(spot_id)                  # tier 2 (cache hit)
        if spot is None:
            # tier 3a — maybe a brand-new spot: scan most-recent pages cheaply.
            spot = await self._lazy_find_spot(spot_id)
        if spot is None:
            # tier 3b — the index may be incomplete (e.g. a background warm-up
            # that didn't finish on a serverless instance). Force a full,
            # synchronous rebuild on this request, then look again. This makes
            # the first request after a cold start slow but correct.
            index = await self.build_spot_index(force=True)
            spot = index.get(spot_id)
        if spot is None:
            return None
        if with_videos:
            await self._attach_videos(spot)
        if with_products:
            await self._attach_products(spot)
        return spot

    async def _attach_products(self, spot: Spot) -> None:
        """Attach commerce offers. The spot row carries product_id directly, so
        we fetch just that one product detail (1 HTTP call) instead of scanning
        all products. Falls back to the spot-index lookup if product_id absent."""
        if not spot.product_id:
            return
        from app.data.products import fetch_product_offers
        try:
            offers = await fetch_product_offers(spot.product_id)
        except Exception:
            offers = []
        if offers:
            spot.products = offers

    async def _attach_videos(self, spot: Spot) -> None:
        """Attach short-form videos from the cached video index (no VM access)."""
        # Imported here to avoid a circular import at module load.
        from app.data.videos import video_index
        try:
            refs = await video_index.get(spot.spot_id)
        except Exception:
            refs = []
        if not refs:
            return
        spot.videos = refs
        # Keep related_videos (URL strings) populated for backward compatibility
        # with the GEO/UCP layers that already read it.
        spot.related_videos = [r.youtube_url for r in refs]
