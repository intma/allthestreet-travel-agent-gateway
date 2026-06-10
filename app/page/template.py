"""
Content page (A) — server-side rendered HTML for a single spot.

This is the *landing page* a Gemini rich-card / search result clicks through to.
Goals:
  - Human-readable, photo-forward place page (name, map, hours, FAQ, buy link).
  - GEO: embed the same Schema.org JSON-LD (so crawlers parse/cite this page).
  - Multilingual-aware (KR primary, shows original/EN as available).

Rendered with plain string templating (no template engine dependency). The page
pulls its data from the same normalized Spot used by GEO/UCP layers.
"""

from __future__ import annotations

import html
import json
from typing import Optional

from app.config import settings
from app.data.images import public_image_url
from app.data.repository import Spot
from app.geo import jsonld


def _esc(v: Optional[str]) -> str:
    return html.escape(v) if v else ""


def _weekday_rows(spot: Spot) -> str:
    """Opening hours table rows (KR weekday labels)."""
    if not spot.opening_periods:
        return ""
    kr_days = {0: "일", 1: "월", 2: "화", 3: "수", 4: "목", 5: "금", 6: "토"}
    rows = []
    for p in sorted(spot.opening_periods, key=lambda x: x.day):
        d = kr_days.get(p.day, "?")
        o = f"{p.open_time[:2]}:{p.open_time[2:]}"
        c = f"{p.close_time[:2]}:{p.close_time[2:]}"
        rows.append(f'<tr><th>{d}</th><td>{o} – {c}</td></tr>')
    return "".join(rows)


def _faq_section(qa_pairs: list[tuple[str, str]]) -> str:
    if not qa_pairs:
        return ""
    items = []
    for q, a in qa_pairs:
        items.append(
            f'<details class="faq"><summary>{_esc(q)}</summary>'
            f'<p>{_esc(a)}</p></details>'
        )
    return f'<section class="block"><h2>자주 묻는 질문</h2>{"".join(items)}</section>'


def _videos_section(spot: Spot) -> str:
    # Prefer structured videos (thumbnail, title, timeframe) when available.
    vids = getattr(spot, "videos", None) or []
    if vids:
        lang_label = {"ko": "한국어", "ja": "日本語", "en": "EN", "other": ""}
        cards = []
        for v in vids:
            title = _esc(v.title or "관련 영상")
            thumb = _esc(v.youtube_thumbnail)
            url = _esc(v.youtube_url)
            lang = lang_label.get(getattr(v, "lang", "other"), "")
            badge = f'<span class="vlang">{lang}</span>' if lang else ""
            tf = ""
            if v.timeframe_sec and v.timeframe_sec > 0:
                m, s = divmod(v.timeframe_sec, 60)
                tf = f'<span class="vid-tf">{m}:{s:02d}</span>'
            cards.append(
                f'<a class="vcard" href="{url}" target="_blank" rel="noopener">'
                f'<span class="vthumb" style="background-image:url(\'{thumb}\')">'
                f'<span class="vplay">▶</span>{tf}</span>'
                f'<span class="vtitle">{badge}{title}</span></a>'
            )
        return (f'<section class="block"><h2>관련 영상</h2>'
                f'<div class="vgrid">{"".join(cards)}</div></section>')
    # Fallback: plain URL list (related_videos strings).
    if not spot.related_videos:
        return ""
    cards = []
    for url in spot.related_videos:
        safe = _esc(url)
        cards.append(
            f'<a class="vid" href="{safe}" target="_blank" rel="noopener">'
            f'<span class="vid-ic">▶</span><span class="vid-tx">{safe}</span></a>'
        )
    return f'<section class="block"><h2>관련 영상</h2><div class="vids">{"".join(cards)}</div></section>'


def _map_block(spot: Spot) -> str:
    if spot.lat is None or spot.lng is None:
        return ""
    # "Open in Google Maps" link (key-free); uses place_id when available.
    if spot.google_place_id:
        maps_url = f"https://www.google.com/maps/place/?q=place_id:{spot.google_place_id}"
    else:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={spot.lat},{spot.lng}"

    key = settings.GOOGLE_MAPS_API_KEY
    if key:
        # Google Maps Embed API. Prefer place mode (richer card) when we have a
        # place_id, else center on coordinates.
        if spot.google_place_id:
            embed = (
                f"https://www.google.com/maps/embed/v1/place?key={key}"
                f"&q=place_id:{spot.google_place_id}"
            )
        else:
            embed = (
                f"https://www.google.com/maps/embed/v1/view?key={key}"
                f"&center={spot.lat},{spot.lng}&zoom=16"
            )
    else:
        # Fallback: key-free OpenStreetMap embed (so the map never renders blank).
        d = 0.004
        bbox = f"{spot.lng - d}%2C{spot.lat - d}%2C{spot.lng + d}%2C{spot.lat + d}"
        embed = (
            f"https://www.openstreetmap.org/export/embed.html?bbox={bbox}"
            f"&marker={spot.lat}%2C{spot.lng}&layer=mapnik"
        )
    return (
        f'<section class="block"><h2>위치</h2>'
        f'<iframe class="map" src="{embed}" loading="lazy" '
        f'title="map" referrerpolicy="no-referrer-when-downgrade" '
        f'allowfullscreen></iframe>'
        f'<a class="btn-map" href="{maps_url}" target="_blank" rel="noopener">'
        f'Google 지도에서 열기 →</a></section>'
    )


def _buy_block(spot: Spot) -> str:
    """Commerce products linked to this spot: price + external purchase link.

    Checkout happens on the partner site (kkday) via the deep link, so this
    works regardless of Stripe/region — we only surface the offer + link.
    """
    products = getattr(spot, "products", None) or []
    if not products:
        return ""
    # Prefer Korean-language entry for the page; fall back to first.
    by_lang = {p.lang: p for p in products}
    prod = by_lang.get("ko") or products[0]

    rows = []
    if prod.options:
        for opt in prod.options:
            link = _esc(opt.out_link or prod.best_link or "")
            name = _esc(opt.name or prod.name or "상품")
            price_html = ""
            if opt.price_discount and opt.price_normal and opt.price_discount < opt.price_normal:
                price_html = (f'<span class="p-was">{opt.price_normal:,.0f}원</span>'
                              f'<span class="p-now">{opt.price_discount:,.0f}원</span>')
            elif opt.price_normal:
                price_html = f'<span class="p-now">{opt.price_normal:,.0f}원</span>'
            btn = (f'<a class="buybtn" href="{link}" target="_blank" rel="noopener">예약하기 →</a>'
                   if link else "")
            rows.append(
                f'<div class="prow"><div class="pinfo"><span class="pname">{name}</span>'
                f'{price_html}</div>{btn}</div>'
            )
    else:
        link = _esc(prod.best_link or "")
        name = _esc(prod.name or "상품")
        btn = (f'<a class="buybtn" href="{link}" target="_blank" rel="noopener">예약하기 →</a>'
               if link else "")
        rows.append(f'<div class="prow"><div class="pinfo"><span class="pname">{name}</span></div>{btn}</div>')

    return (f'<section class="block buy"><h2>예약 · 티켓</h2>'
            f'{"".join(rows)}'
            f'<p class="buynote">외부 예약처(kkday 등)에서 결제가 진행됩니다.</p></section>')


def render_spot_page(spot: Spot, qa_pairs: Optional[list[tuple[str, str]]] = None) -> str:
    qa_pairs = qa_pairs or []
    name = _esc(spot.display_name)
    sub = _esc(spot.name_en or spot.name) if (spot.name_en or spot.name) and (spot.name_en or spot.name) != spot.display_name else ""
    addr = _esc(spot.address_kr or spot.address_en or spot.address)
    img = public_image_url(spot.thumbnail_url) if spot.thumbnail_url else ""
    status_kr = "영업 중" if spot.business_status == "OPERATIONAL" else ""
    phone = _esc(spot.phone)
    canonical = jsonld.spot_canonical_url(spot)

    # Same JSON-LD graph the GEO endpoint serves — embedded for crawlers.
    graph = jsonld.build_full_graph(spot, qa_pairs=qa_pairs)
    ld = json.dumps(graph, ensure_ascii=False)

    hero_style = f'style="background-image:url(\'{_esc(img)}\')"' if img else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} · AllTheStreet</title>
<meta name="description" content="{addr}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{name}">
<meta property="og:type" content="place">
{f'<meta property="og:image" content="{_esc(img)}">' if img else ''}
<script type="application/ld+json">{ld}</script>
<style>
  :root{{
    --ink:#1a1714; --paper:#f7f3ec; --muted:#8a8178; --line:#e2d9cb;
    --accent:#c2562b; --card:#fffdf8;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Pretendard','Apple SD Gothic Neo',-apple-system,sans-serif;
    background:var(--paper);color:var(--ink);line-height:1.6}}
  .hero{{height:46vh;min-height:280px;background-size:cover;background-position:center;
    position:relative;display:flex;align-items:flex-end;
    background-color:#ddd2c0}}
  .hero::after{{content:"";position:absolute;inset:0;
    background:linear-gradient(180deg,rgba(0,0,0,0) 40%,rgba(0,0,0,.6))}}
  .hero-in{{position:relative;z-index:1;padding:28px 22px;color:#fff;max-width:760px;
    margin:0 auto;width:100%}}
  .hero h1{{font-size:2rem;font-weight:800;letter-spacing:-.02em;
    text-shadow:0 2px 12px rgba(0,0,0,.4)}}
  .hero .sub{{opacity:.9;font-size:.95rem;margin-top:4px}}
  .badge{{display:inline-block;background:var(--accent);color:#fff;font-size:.75rem;
    font-weight:700;padding:3px 10px;border-radius:99px;margin-bottom:10px}}
  main{{max-width:760px;margin:0 auto;padding:22px}}
  .meta{{display:flex;flex-wrap:wrap;gap:10px;margin:-30px 0 18px;position:relative;z-index:2}}
  .chip{{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:10px 14px;font-size:.9rem;box-shadow:0 4px 14px rgba(0,0,0,.05)}}
  .chip b{{display:block;font-size:.7rem;color:var(--muted);font-weight:600;
    text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}}
  .block{{background:var(--card);border:1px solid var(--line);border-radius:16px;
    padding:20px;margin-bottom:16px}}
  .block h2{{font-size:1.05rem;margin-bottom:12px;letter-spacing:-.01em}}
  table{{width:100%;border-collapse:collapse;font-size:.92rem}}
  table th{{text-align:left;width:48px;color:var(--muted);font-weight:600}}
  table td{{padding:3px 0}}
  .map{{width:100%;height:260px;border:0;border-radius:12px;background:#eee}}
  .btn-map{{display:inline-block;margin-top:12px;color:var(--accent);
    font-weight:700;text-decoration:none}}
  .faq{{border-top:1px solid var(--line);padding:12px 0}}
  .faq:first-of-type{{border-top:0}}
  .faq summary{{cursor:pointer;font-weight:600;list-style:none}}
  .faq summary::-webkit-details-marker{{display:none}}
  .faq summary::before{{content:"+ ";color:var(--accent);font-weight:800}}
  .faq[open] summary::before{{content:"– "}}
  .faq p{{margin-top:8px;color:#4a443d}}
  .vids{{display:flex;flex-direction:column;gap:8px}}
  .vid{{display:flex;align-items:center;gap:10px;padding:10px 12px;
    border:1px solid var(--line);border-radius:10px;text-decoration:none;
    color:var(--ink);font-size:.85rem;word-break:break-all}}
  .vid-ic{{color:var(--accent);font-size:1.1rem}}
  .vgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
    gap:14px}}
  .vcard{{text-decoration:none;color:var(--ink)}}
  .vthumb{{display:block;position:relative;aspect-ratio:16/9;border-radius:12px;
    background:#ddd2c0 center/cover no-repeat;overflow:hidden;
    box-shadow:0 3px 10px rgba(0,0,0,.08)}}
  .vplay{{position:absolute;inset:0;display:flex;align-items:center;
    justify-content:center;color:#fff;font-size:1.6rem;
    background:rgba(0,0,0,.25);transition:background .2s}}
  .vcard:hover .vplay{{background:rgba(0,0,0,.45)}}
  .vid-tf{{position:absolute;right:6px;bottom:6px;background:rgba(0,0,0,.78);
    color:#fff;font-size:.72rem;padding:1px 6px;border-radius:5px}}
  .vtitle{{display:block;margin-top:8px;font-size:.85rem;line-height:1.35;
    font-weight:600;display:-webkit-box;-webkit-line-clamp:2;
    -webkit-box-orient:vertical;overflow:hidden}}
  .vlang{{display:inline-block;background:var(--accent);color:#fff;font-size:.66rem;
    font-weight:700;padding:1px 6px;border-radius:5px;margin-right:5px;
    vertical-align:middle}}
  .buy{{border-color:var(--accent)}}
  .prow{{display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:12px 0;border-top:1px solid var(--line)}}
  .prow:first-of-type{{border-top:0}}
  .pinfo{{display:flex;flex-direction:column;gap:3px}}
  .pname{{font-weight:600;font-size:.95rem}}
  .p-was{{color:var(--muted);text-decoration:line-through;font-size:.82rem;
    margin-right:6px}}
  .p-now{{color:var(--accent);font-weight:800;font-size:1.02rem}}
  .buybtn{{flex-shrink:0;background:var(--accent);color:#fff;text-decoration:none;
    font-weight:700;font-size:.9rem;padding:9px 16px;border-radius:10px;
    white-space:nowrap;transition:transform .12s}}
  .buybtn:hover{{transform:translateY(-1px)}}
  .buynote{{margin-top:12px;color:var(--muted);font-size:.76rem}}
  footer{{max-width:760px;margin:0 auto;padding:22px;color:var(--muted);
    font-size:.8rem;border-top:1px solid var(--line)}}
  footer a{{color:var(--accent)}}
</style>
</head>
<body>
  <div class="hero" {hero_style}>
    <div class="hero-in">
      {f'<span class="badge">{status_kr}</span>' if status_kr else ''}
      <h1>{name}</h1>
      {f'<div class="sub">{sub}</div>' if sub else ''}
    </div>
  </div>
  <main>
    {_videos_section(spot)}
    <div class="meta">
      {f'<div class="chip"><b>주소</b>{addr}</div>' if addr else ''}
      {f'<div class="chip"><b>전화</b>{phone}</div>' if phone else ''}
    </div>
    {f'<section class="block"><h2>영업시간</h2><table>{_weekday_rows(spot)}</table></section>' if spot.opening_periods else ''}
    {_buy_block(spot)}
    {_map_block(spot)}
    {_faq_section(qa_pairs)}
  </main>
  <footer>
    데이터 제공 · <a href="{settings.PUBLIC_BASE_URL}">AllTheStreet</a><br>
    이 페이지는 구조화 데이터(JSON-LD)를 포함하여 검색·생성형 AI가 인용할 수 있습니다.
  </footer>
</body>
</html>"""
