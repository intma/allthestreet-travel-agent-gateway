"""
UCP adapter — convert a normalized Spot into a UCP discovery object.

Reuses the same Spot the GEO layer consumes, so both layers stay in sync.
Category/region ids are mapped to human-readable labels where known; unknown
ids fall back to a generic label so the agent still gets *something* useful.
"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.data.repository import Spot
from app.data.images import public_image_url
from app.ucp.schema import (
    Availability,
    ExternalIds,
    GeoPoint,
    LocalizedText,
    Offer,
    OpeningHours,
    RelatedVideo,
    UCPManifest,
    UCPObject,
    UCPType,
)

_DAY_NAME = {
    0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday",
    4: "Thursday", 5: "Friday", 6: "Saturday",
}


def _hhmm(t: str) -> str:
    t = (t or "").zfill(4)
    return f"{t[:2]}:{t[2:]}"


def _availability_from_status(status: Optional[str]) -> Availability:
    if not status:
        return Availability.unknown
    return Availability.in_stock if status == "OPERATIONAL" else Availability.out_of_stock


def ucp_object_url(spot: Spot) -> str:
    return f"{settings.PUBLIC_BASE_URL}/ucp/spot/{spot.spot_id}"


def spot_to_ucp(spot: Spot) -> UCPObject:
    name = LocalizedText(
        default=spot.display_name,
        kr=spot.name_kr,
        en=spot.name_en,
        original=spot.name,
    )

    address = None
    if spot.address_kr or spot.address_en or spot.address:
        address = LocalizedText(
            default=spot.address_kr or spot.address_en or spot.address,
            kr=spot.address_kr,
            en=spot.address_en,
            original=spot.address,
        )

    geo = None
    if spot.lat is not None and spot.lng is not None:
        geo = GeoPoint(lat=spot.lat, lng=spot.lng)

    hours = [
        OpeningHours(
            day_of_week=_DAY_NAME[p.day],
            opens=_hhmm(p.open_time),
            closes=_hhmm(p.close_time),
        )
        for p in spot.opening_periods
        if p.day in _DAY_NAME
    ]

    videos = [RelatedVideo(url=u) for u in spot.related_videos]

    images = [public_image_url(spot.thumbnail_url)] if spot.thumbnail_url else []

    external = ExternalIds(
        allthestreet_spot_id=spot.spot_id,
        google_place_id=spot.google_place_id,
        naver_place_id=spot.naver_place_id,
    )

    # Offers from linked commerce products (kkday tickets etc.). Each product
    # option becomes an Offer with its price + deep link. No Stripe needed —
    # checkout happens on the external partner (kkday) via the deep link.
    offers: list[Offer] = []
    for prod in getattr(spot, "products", []) or []:
        link = prod.best_link
        if prod.options:
            for opt in prod.options:
                price = opt.price_discount or opt.price_normal
                offers.append(Offer(
                    price=price,
                    price_currency="KRW",
                    availability=(
                        Availability.in_stock if (opt.stock is None or opt.stock > 0)
                        else Availability.out_of_stock
                    ),
                    url=opt.out_link or link,
                    checkout_deep_link=opt.out_link or link,
                    seller=prod.name,
                ))
        elif link:
            offers.append(Offer(
                price=prod.best_price,
                price_currency="KRW",
                availability=Availability.in_stock,
                url=link,
                checkout_deep_link=link,
                seller=prod.name,
            ))

    return UCPObject(
        id=f"ats:spot:{spot.spot_id}",
        type=UCPType.place,
        name=name,
        address=address,
        geo=geo,
        telephone=spot.phone,
        category=str(spot.category_id) if spot.category_id is not None else None,
        region=str(spot.region_id) if spot.region_id is not None else None,
        images=images,
        availability=_availability_from_status(spot.business_status),
        opening_hours=hours,
        offers=offers,
        related_videos=videos,
        external_ids=external,
        url=ucp_object_url(spot),
    )


def build_manifest() -> UCPManifest:
    base = settings.PUBLIC_BASE_URL
    return UCPManifest(
        endpoints={
            "feed": f"{base}/ucp/feed",
            "spot": f"{base}/ucp/spot/{{spot_id}}",
            "search": f"{base}/ucp/feed?search={{query}}",
            "geo_jsonld": f"{base}/geo/spot/{{spot_id}}.jsonld",
        }
    )
