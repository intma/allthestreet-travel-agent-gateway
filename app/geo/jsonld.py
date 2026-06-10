"""
GEO layer — Schema.org JSON-LD generation.

Turns a normalized Spot into JSON-LD that Gemini and Google Search can parse,
cite, and surface. Implements the structures called for in the project brief:

  - LocalBusiness / Place  (name, geo, address, telephone, openingHours)
  - ImageObject            (high-res thumbnail)
  - VideoObject + hasPart  (short-form video -> place mapping)
  - FAQPage                (conversational Q&A, the format Gemini likes to cite)

Multilingual: we emit Korean as the primary and keep English/原文 as alternates.
"""

from __future__ import annotations

from typing import Any, Optional

from app.config import settings
from app.data.repository import Spot
from app.data.images import public_image_url

SCHEMA = "https://schema.org"

# Google opening_hours day index (0=Sun..6=Sat) -> Schema.org day URIs
_DAY_URI = {
    0: f"{SCHEMA}/Sunday",
    1: f"{SCHEMA}/Monday",
    2: f"{SCHEMA}/Tuesday",
    3: f"{SCHEMA}/Wednesday",
    4: f"{SCHEMA}/Thursday",
    5: f"{SCHEMA}/Friday",
    6: f"{SCHEMA}/Saturday",
}


def _hhmm(t: str) -> str:
    """'2130' -> '21:30'."""
    t = (t or "").zfill(4)
    return f"{t[:2]}:{t[2:]}"


def _opening_hours_spec(spot: Spot) -> list[dict[str, Any]]:
    specs = []
    for p in spot.opening_periods:
        day_uri = _DAY_URI.get(p.day)
        if not day_uri:
            continue
        specs.append({
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": day_uri,
            "opens": _hhmm(p.open_time),
            "closes": _hhmm(p.close_time),
        })
    return specs


def spot_canonical_url(spot: Spot) -> str:
    return f"{settings.PUBLIC_BASE_URL}/geo/spot/{spot.spot_id}"


def _lang_values(*pairs: tuple[str, Optional[str]]) -> Any:
    """Build a language-tagged value list for JSON-LD.

    Each pair is (lang, text). Skips empties and de-duplicates identical text.
    Returns a single {"@language","@value"} dict if only one, a list if many,
    or None if nothing. This lets Gemini/crawlers know which language each
    string is in, so they can translate/cite appropriately for any user.
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for lang, text in pairs:
        if not text or text in seen:
            continue
        seen.add(text)
        out.append({"@language": lang, "@value": text})
    if not out:
        return None
    return out[0] if len(out) == 1 else out


def build_place_jsonld(spot: Spot) -> dict[str, Any]:
    """Primary LocalBusiness/Place node for a spot."""
    node: dict[str, Any] = {
        "@context": SCHEMA,
        "@type": "LocalBusiness",
        "@id": spot_canonical_url(spot) + "#place",
        "url": spot_canonical_url(spot),
    }

    # Name — language-tagged across the languages we actually have.
    # `name` carries the primary (KR); `alternateName` carries the rest, each
    # tagged with its language so Gemini can serve any user's language.
    node["name"] = _lang_values(("ko", spot.name_kr)) or spot.display_name
    alt = _lang_values(
        ("en", spot.name_en),
        ("ja", spot.name if spot.name and spot.name != spot.name_kr else None),
    )
    if alt:
        node["alternateName"] = alt

    # Geo
    if spot.lat is not None and spot.lng is not None:
        node["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": spot.lat,
            "longitude": spot.lng,
        }

    # Address — language-tagged street address (KR primary, EN if available).
    street = _lang_values(
        ("ko", spot.address_kr),
        ("en", spot.address_en),
        ("ja", spot.address if spot.address and spot.address != spot.address_kr else None),
    )
    if street:
        node["address"] = {
            "@type": "PostalAddress",
            "streetAddress": street,
            "addressCountry": "KR",
        }

    if spot.phone:
        node["telephone"] = spot.phone

    oh = _opening_hours_spec(spot)
    if oh:
        node["openingHoursSpecification"] = oh

    if spot.thumbnail_url:
        node["image"] = {
            "@type": "ImageObject",
            "url": public_image_url(spot.thumbnail_url),
        }

    # External identifiers: Google Place ID is the strongest Maps/Gemini anchor.
    same_as = []
    if spot.google_place_id:
        same_as.append(
            f"https://www.google.com/maps/place/?q=place_id:{spot.google_place_id}"
        )
        node["additionalProperty"] = [{
            "@type": "PropertyValue",
            "propertyID": "googlePlaceId",
            "value": spot.google_place_id,
        }]
    if same_as:
        node["sameAs"] = same_as

    if spot.business_status:
        # Map Google status to a human-readable note
        node["disambiguatingDescription"] = f"business_status: {spot.business_status}"

    # Commerce offers (kkday tickets etc.) — makesOffer with price + deep link.
    offers_ld = _build_offers_ld(spot)
    if offers_ld:
        node["makesOffer"] = offers_ld

    return node


def _build_offers_ld(spot: Spot) -> list[dict[str, Any]]:
    """Schema.org Offers from linked commerce products (price + purchase URL)."""
    out: list[dict[str, Any]] = []
    for prod in getattr(spot, "products", []) or []:
        link = prod.best_link
        if prod.options:
            for opt in prod.options:
                price = opt.price_discount or opt.price_normal
                if not (opt.out_link or link):
                    continue
                offer: dict[str, Any] = {
                    "@type": "Offer",
                    "name": opt.name or prod.name,
                    "url": opt.out_link or link,
                    "availability": "https://schema.org/InStock",
                }
                if price:
                    offer["price"] = price
                    offer["priceCurrency"] = "KRW"
                out.append(offer)
        elif link:
            offer = {
                "@type": "Offer",
                "name": prod.name,
                "url": link,
                "availability": "https://schema.org/InStock",
            }
            if prod.best_price:
                offer["price"] = prod.best_price
                offer["priceCurrency"] = "KRW"
            out.append(offer)
    return out


def build_video_jsonld(spot: Spot) -> Optional[dict[str, Any]]:
    """VideoObject(s) linking short-form clips to this place (Video-to-Place)."""
    structured = getattr(spot, "videos", None) or []
    videos = []
    if structured:
        for v in structured:
            node = {
                "@type": "VideoObject",
                "name": v.title or f"{spot.display_name} — short-form clip",
                "description": f"Short-form video featuring {spot.display_name}.",
                "thumbnailUrl": v.youtube_thumbnail,
                "embedUrl": f"https://www.youtube.com/embed/{v.youtube_id}",
                "contentUrl": v.youtube_url,
                "about": {"@id": spot_canonical_url(spot) + "#place"},
            }
            # Time-coded segment: where this place appears in the clip.
            if v.timeframe_sec and v.timeframe_sec > 0:
                node["hasPart"] = {
                    "@type": "Clip",
                    "name": f"{spot.display_name} 등장",
                    "startOffset": v.timeframe_sec,
                    "url": v.youtube_url,
                }
            videos.append(node)
    elif spot.related_videos:
        for i, url in enumerate(spot.related_videos):
            videos.append({
                "@type": "VideoObject",
                "name": f"{spot.display_name} — short-form clip {i + 1}",
                "description": f"Short-form video featuring {spot.display_name}.",
                "contentUrl": url,
                "thumbnailUrl": public_image_url(spot.thumbnail_url) if spot.thumbnail_url else None,
                "about": {"@id": spot_canonical_url(spot) + "#place"},
            })
    if not videos:
        return None
    if len(videos) == 1:
        return {"@context": SCHEMA, **videos[0]}
    return {
        "@context": SCHEMA,
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": v}
            for i, v in enumerate(videos)
        ],
    }


def build_faq_jsonld(spot: Spot, qa_pairs: list[tuple[str, str]]) -> Optional[dict[str, Any]]:
    """
    FAQPage — the conversational Q&A structure Gemini prefers to cite.
    qa_pairs: list of (question, answer). Generated/curated upstream.
    """
    if not qa_pairs:
        return None
    return {
        "@context": SCHEMA,
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in qa_pairs
        ],
    }


def build_full_graph(spot: Spot, qa_pairs: Optional[list[tuple[str, str]]] = None) -> dict[str, Any]:
    """A single @graph document bundling all nodes for one spot page."""
    graph: list[dict[str, Any]] = [build_place_jsonld(spot)]
    video = build_video_jsonld(spot)
    if video:
        graph.append(video)
    faq = build_faq_jsonld(spot, qa_pairs or [])
    if faq:
        graph.append(faq)
    return {"@context": SCHEMA, "@graph": graph}
