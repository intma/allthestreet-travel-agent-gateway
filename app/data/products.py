"""
Product index — connect commerce products (kkday tickets etc.) to spots.

The existing `/api_mukbang/products` endpoint lists products with `linked_spots`
(which places each product belongs to). Each product's commerce detail lives in
`product_extra` — a JSON blob with a `commerce[]` array (one entry per language),
each carrying `out_link` (kkday deep link), `price{normal,discount}`, `stock`,
and `options[]`.

We build a `{spot_id: [ProductOffer, ...]}` index in memory (same pattern as the
video index) so Page/UCP/GEO can attach offers to a spot. No VM access; reads the
existing API only.

NOTE: the list endpoint returns a summary (id, name, linked_spots). The full
`product_extra` comes from the detail endpoint. PRODUCT_DETAIL_PATH is the
configurable path for that detail call; set once the exact URL is confirmed.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings


@dataclass
class ProductOption:
    name: Optional[str] = None
    out_link: Optional[str] = None
    price_normal: Optional[float] = None
    price_discount: Optional[float] = None
    stock: Optional[int] = None
    thumbnail: Optional[str] = None


@dataclass
class ProductOffer:
    product_id: int
    name: Optional[str] = None
    lang: str = "ko"
    out_link: Optional[str] = None          # product-level deep link
    summary: Optional[str] = None
    thumbnail: Optional[str] = None
    options: list[ProductOption] = field(default_factory=list)

    @property
    def best_price(self) -> Optional[float]:
        """Lowest available price across options (discount preferred)."""
        prices = []
        for o in self.options:
            if o.price_discount:
                prices.append(o.price_discount)
            elif o.price_normal:
                prices.append(o.price_normal)
        return min(prices) if prices else None

    @property
    def best_link(self) -> Optional[str]:
        """A usable purchase deep link: product-level, else first option's."""
        if self.out_link:
            return self.out_link
        for o in self.options:
            if o.out_link:
                return o.out_link
        return None


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first(lst):
    return lst[0] if isinstance(lst, list) and lst else None


def _parse_commerce(product_extra: str) -> list[ProductOffer]:
    """Parse the product_extra JSON blob into per-language ProductOffers."""
    if not product_extra:
        return []
    try:
        data = json.loads(product_extra) if isinstance(product_extra, str) else product_extra
    except (json.JSONDecodeError, TypeError):
        return []
    offers: list[ProductOffer] = []
    for c in data.get("commerce", []) or []:
        opts = []
        for o in c.get("options", []) or []:
            price = o.get("price") or {}
            opts.append(ProductOption(
                name=o.get("name"),
                out_link=o.get("out_link"),
                price_normal=_num(price.get("normal")),
                price_discount=_num(price.get("discount")),
                stock=o.get("stock"),
                thumbnail=_first(o.get("thumbnail")),
            ))
        offers.append(ProductOffer(
            product_id=0,  # set by caller
            name=c.get("name"),
            lang=c.get("lang", "ko"),
            out_link=c.get("out_link"),
            summary=c.get("summary"),
            thumbnail=_first(c.get("thumbnail")),
            options=opts,
        ))
    return offers


class ProductIndex:
    """In-memory spot_id -> [ProductOffer] index from the products endpoint."""

    def __init__(self, ttl_seconds: int = 1800, max_pages: int = 200, page_size: int = 50):
        self.ttl = ttl_seconds
        self.max_pages = max_pages
        self.page_size = page_size
        self._index: dict[int, list[ProductOffer]] = {}
        self._built_at: float = 0.0
        self._building = False

    def _fresh(self) -> bool:
        return bool(self._index) and (time.time() - self._built_at) < self.ttl

    async def _fetch_list(self, client: httpx.AsyncClient, page: int) -> dict:
        url = f"{settings.SOURCE_API_BASE}/api_mukbang/products"
        resp = await client.get(url, params={"page": page, "pageSize": self.page_size})
        resp.raise_for_status()
        return resp.json()

    async def _fetch_detail(self, client: httpx.AsyncClient, product_id: int) -> Optional[dict]:
        """Fetch one product's full record (with product_extra).

        PRODUCT_DETAIL_PATH is configurable; '{id}' is substituted. Returns the
        product dict or None. Tolerates failure so the gateway still works.
        """
        path = settings.PRODUCT_DETAIL_PATH.replace("{id}", str(product_id))
        try:
            resp = await client.get(f"{settings.SOURCE_API_BASE}{path}")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        # Detail may be {product:{...}} or {products:[{...}]} or {...}
        if isinstance(data, dict):
            if "product" in data:
                return data["product"]
            if "products" in data and data["products"]:
                return data["products"][0]
            return data
        return None

    async def build(self) -> None:
        if self._building:
            return
        self._building = True
        index: dict[int, list[ProductOffer]] = {}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for page in range(1, self.max_pages + 1):
                    payload = await self._fetch_list(client, page)
                    products = payload.get("products", []) if isinstance(payload, dict) else []
                    if not products:
                        break
                    for p in products:
                        pid = p.get("id")
                        linked = p.get("linked_spots", []) or []
                        if not linked:
                            continue
                        # Detail holds product_extra (commerce). Fetch per product.
                        extra = p.get("product_extra")
                        if extra is None:
                            detail = await self._fetch_detail(client, pid)
                            extra = (detail or {}).get("product_extra")
                        offers = _parse_commerce(extra)
                        for off in offers:
                            off.product_id = pid
                        if not offers:
                            continue
                        for ls in linked:
                            sid = ls.get("spot_id")
                            if sid is None:
                                continue
                            index.setdefault(int(sid), []).extend(offers)
            self._index = index
            self._built_at = time.time()
        finally:
            self._building = False

    async def get(self, spot_id: int, lang: Optional[str] = None) -> list[ProductOffer]:
        if not self._fresh():
            await self.build()
        offers = self._index.get(spot_id, [])
        if lang:
            filtered = [o for o in offers if o.lang == lang]
            return filtered or offers
        return offers


# Singleton index shared across requests.
product_index = ProductIndex()


async def fetch_product_offers(product_id: int) -> list[ProductOffer]:
    """Fetch one product's detail by id and parse its commerce offers.

    Used when a spot row already carries product_id, so we avoid scanning the
    whole product catalog — a single HTTP call per spot page.
    """
    path = settings.PRODUCT_DETAIL_PATH.replace("{id}", str(product_id))
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(f"{settings.SOURCE_API_BASE}{path}")
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, dict):
        if "product" in data:
            data = data["product"]
        elif "products" in data and data["products"]:
            data = data["products"][0]
    extra = (data or {}).get("product_extra")
    offers = _parse_commerce(extra)
    for off in offers:
        off.product_id = product_id
    return offers
