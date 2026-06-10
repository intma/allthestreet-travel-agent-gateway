"""
Demo agent — runs the SAME Gemini function-calling flow as demo/gemini_mcp_demo.py,
but in-process inside the gateway (no external MCP HTTP round-trip).

Flow (verified in B-1 step 1):
  question -> Gemini (with our tool schemas as function_declarations)
           -> Gemini emits function_call(s)
           -> WE execute them against SpotRepository (same data as MCP/GEO/UCP)
           -> feed results back -> Gemini writes the final answer.

We deliberately do NOT hand Gemini a live MCP session object: google-genai
deep-copies the request config and chokes on asyncio objects
(`cannot pickle '_asyncio.Future'`). Passing plain JSON function declarations
and orchestrating the calls ourselves is SDK-version-proof and lets us shape
the results (cards, prices, /p links) for the UI.

Returns a structured dict the /demo page renders:
  {
    "answer": "<final markdown text>",
    "tool_calls": [ {name, args, count}, ... ],   # what Gemini asked us to run
    "spots": [ {spot_id, name, address, url, page_url, products:[...]}, ... ],
  }
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.data.repository import Spot, SpotRepository

# google-genai is only needed for the demo; import lazily so the rest of the
# gateway runs even if the package/key is absent.
try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except Exception:  # pragma: no cover
    _GENAI_AVAILABLE = False


GEMINI_MODEL = settings.GEMINI_MODEL if hasattr(settings, "GEMINI_MODEL") else "gemini-3.5-flash"
MAX_TURNS = 8

_repo = SpotRepository()


# ---- tool declarations (mirror the MCP tools, as plain JSON for Gemini) ------

_TOOL_DECLARATIONS = [
    {
        "name": "search_spots",
        "description": (
            "AllTheStreet 큐레이션 장소를 키워드(이름/주소)로 검색한다. "
            "예: '성수동 카페', '부산 해운대'. 결과는 장소 요약 목록."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "검색어"},
                "limit": {"type": "integer", "description": "최대 결과 수 (1-20)"},
                "lang": {"type": "string", "description": "응답 언어 ko/en"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_spot_detail",
        "description": (
            "장소 하나의 상세 정보(좌표·영업시간·예약 가능한 상품/티켓 등)를 가져온다. "
            "특정 장소의 가격이나 예약 정보가 필요할 때 사용."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "spot_id": {"type": "integer", "description": "AllTheStreet 장소 id"},
                "lang": {"type": "string", "description": "응답 언어 ko/en"},
            },
            "required": ["spot_id"],
        },
    },
]


def _spot_summary(spot: Spot, lang: str = "ko") -> dict[str, Any]:
    # spot data has ko/en only (no ja). Choose with sensible fallback:
    #   en/ja users -> en if present else ko;  ko users -> ko.
    if lang == "ko":
        name = spot.name_kr or spot.name_en or spot.display_name
        addr = spot.address_kr or spot.address_en
    else:  # en, ja, or anything else
        name = spot.name_en or spot.name_kr or spot.display_name
        addr = spot.address_en or spot.address_kr
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return {
        "spot_id": spot.spot_id,
        "name": name or spot.display_name,
        "address": addr,
        "lat": spot.lat,
        "lng": spot.lng,
        "url": f"{base}/ucp/spot/{spot.spot_id}",
        "page_url": f"{base}/p/{spot.spot_id}",
    }


def _video_dicts(spot: Spot, lang: str = "ko", limit: int = 1) -> list[dict[str, Any]]:
    """Compact video info for cards: thumbnail + title + watch url.
    Prefer videos in the user's language; fall back to any available."""
    vids = list(spot.videos or [])
    # user-language videos first, then the rest (stable order otherwise)
    preferred = [v for v in vids if getattr(v, "lang", "") == lang]
    others = [v for v in vids if getattr(v, "lang", "") != lang]
    ordered = (preferred + others)[:limit]
    out = []
    for v in ordered:
        out.append({
            "youtube_id": getattr(v, "youtube_id", ""),
            "title": getattr(v, "title", "") or "",
            "thumbnail": v.youtube_thumbnail if hasattr(v, "youtube_thumbnail") else "",
            "watch_url": v.youtube_url if hasattr(v, "youtube_url") else "",
            "lang": getattr(v, "lang", "other"),
        })
    return out


def _offer_dicts(spot: Spot, lang: str = "ko") -> list[dict[str, Any]]:
    """Turn attached ProductOffer objects into compact dicts for cards.
    Products carry per-language offers (ko/en/ja); pick the user's language,
    fall back to ko, then to whatever exists."""
    all_offers = list(spot.products or [])
    if not all_offers:
        return []
    chosen = [o for o in all_offers if getattr(o, "lang", "ko") == lang]
    if not chosen:
        chosen = [o for o in all_offers if getattr(o, "lang", "ko") == "ko"]
    if not chosen:
        chosen = all_offers
    out = []
    for off in chosen:
        options = []
        for opt in getattr(off, "options", []) or []:
            price = getattr(opt, "price", None) or {}
            options.append({
                "name": getattr(opt, "name", ""),
                "normal": price.get("normal") if isinstance(price, dict) else getattr(price, "normal", None),
                "discount": price.get("discount") if isinstance(price, dict) else getattr(price, "discount", None),
                "out_link": getattr(opt, "best_link", None) or getattr(opt, "out_link", None),
            })
        out.append({
            "name": getattr(off, "name", "") or "",
            "out_link": getattr(off, "best_link", None) or getattr(off, "out_link", None),
            "options": options,
        })
    return out


def _spots_in_answer_order(answer: str, collected: dict[int, dict]) -> list[dict[str, Any]]:
    """Return only the spots the answer actually recommends, in answer order.

    Hybrid matching, because Gemini doesn't always include our /p|/ucp links:
      1) link match  — /ucp/spot/{id} or /p/{id} URLs in the answer
      2) name match  — the spot's name appearing in the answer text
    Each matched spot is keyed by its FIRST position in the answer, then we
    sort by position. Falls back to all collected spots only if nothing
    matches at all (never an empty card row)."""
    import re
    text = answer or ""
    pos_by_id: dict[int, int] = {}

    def _norm(s: str) -> str:
        return re.sub(r"[^0-9a-z\uac00-\ud7a3]+", "", (s or "").lower())

    norm_text = _norm(text)

    # 1) explicit links to our pages (position converted into normalized
    #    coordinates so it sorts consistently with name matches below)
    for m in re.finditer(r"/(?:ucp/spot|p)/(\d+)", text):
        sid = int(m.group(1))
        if sid in collected and sid not in pos_by_id:
            pos_by_id[sid] = len(_norm(text[: m.start()]))

    # 2) spot names mentioned in the text, compared on the normalized form so
    #    "SPA & WATERPARK" matches "SPA&WATERPARK" and "Blueline Park
    #    (Cheongsapo)" matches "bluelinepark Cheongsapo". Skip very short
    #    normalized names to avoid accidental substring hits.
    for sid, summary in collected.items():
        if sid in pos_by_id:
            continue
        norm_name = _norm(summary.get("name") or "")
        if len(norm_name) < 5:
            continue
        idx = norm_text.find(norm_name)
        if idx >= 0:
            pos_by_id[sid] = idx

    if not pos_by_id:
        return list(collected.values())
    ordered_ids = sorted(pos_by_id, key=pos_by_id.get)
    return [collected[sid] for sid in ordered_ids]


async def _run_tool(name: str, args: dict[str, Any], collected: dict[int, dict],
                    user_lang: str = "ko") -> str:
    """Execute one tool against the repo; record spots for the UI cards.
    Gemini's per-call `lang` arg shapes the JSON we hand back to the model,
    but the UI cards always use `user_lang` (the toggle/auto choice) so the
    card language stays consistent regardless of how Gemini phrased each call."""
    lang = args.get("lang", user_lang)
    if name == "search_spots":
        keyword = args.get("keyword", "") or ""
        limit = max(1, min(int(args.get("limit", 5) or 5), 20))
        _, spots = await _repo.list_spots(page=1, page_size=limit, search=keyword or None)
        for s in spots:
            collected.setdefault(s.spot_id, _spot_summary(s, user_lang))
        return json.dumps([_spot_summary(s, lang) for s in spots], ensure_ascii=False)

    if name == "get_spot_detail":
        spot_id = int(args.get("spot_id"))
        spot = await _repo.get_spot(spot_id, with_videos=True, with_products=True)
        if not spot:
            return json.dumps({"error": "not found"}, ensure_ascii=False)
        summary = _spot_summary(spot, user_lang)
        summary["products"] = _offer_dicts(spot, user_lang)
        summary["videos"] = _video_dicts(spot, user_lang)
        collected[spot_id] = summary  # overwrite with richer detail
        return json.dumps(summary, ensure_ascii=False)

    return json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False)


async def _enrich_with_media(collected: dict[int, dict], user_lang: str = "ko") -> None:
    """Ensure every collected spot has product + video info for the cards,
    even if Gemini only called search (not get_spot_detail)."""
    for spot_id, summary in collected.items():
        if "products" in summary and "videos" in summary:
            continue
        spot = await _repo.get_spot(spot_id, with_videos=True, with_products=True)
        if spot:
            summary.setdefault("products", _offer_dicts(spot, user_lang))
            summary.setdefault("videos", _video_dicts(spot, user_lang))
        else:
            summary.setdefault("products", [])
            summary.setdefault("videos", [])


async def run_demo_agent(question: str, lang: str = "ko") -> dict[str, Any]:
    """Main entry. Returns {answer, tool_calls, spots}."""
    if not _GENAI_AVAILABLE:
        raise RuntimeError("google-genai 패키지가 없습니다. requirements에 추가하세요.")
    if not getattr(settings, "GEMINI_API_KEY", ""):
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다 (Secret Manager).")

    gemini = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Answer-language instruction. "auto" lets Gemini reply in the question's
    # language; an explicit ko/en/ja pins it (toggle override).
    lang_directive = {
        "ko": "한국어로 답해줘.",
        "en": "Respond in English.",
        "ja": "日本語で答えてください。",
    }.get(lang, "사용자가 질문한 언어와 동일한 언어로 답해줘. "
                "Reply in the same language as the user's question.")
    system_instruction = (
        "너는 AllTheStreet 여행 가이드 에이전트다. 제공된 도구(search_spots, "
        "get_spot_detail)로 장소·티켓 정보를 찾아 추천한다. 추천하는 각 장소에는 "
        "도구 결과의 page_url 링크를 본문에 반드시 포함해라(마크다운 링크). "
        + lang_directive
    )
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[types.Tool(function_declarations=_TOOL_DECLARATIONS)],
    )
    # user_lang for the cards: explicit choice, or "ko" default when auto
    # (cards use repo data which is ko/en only; en covers ja via fallback).
    user_lang = lang if lang in ("ko", "en", "ja") else "ko"

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    tool_log: list[dict[str, Any]] = []
    collected: dict[int, dict] = {}

    final_directive = {
        "ko": "더 이상 도구를 호출하지 말고, 지금까지 검색한 장소 정보만으로 "
              "사용자 질문에 대한 최종 답변을 한국어로 작성해줘. 각 추천 장소는 "
              "이름과 간단한 설명을 포함해줘.",
        "en": "Do not call any more tools. Using only the places found so far, "
              "write the final answer to the user's question in English. Include "
              "each recommended place's name and a short description.",
        "ja": "これ以上ツールを呼び出さず、これまでに検索した場所の情報だけで "
              "ユーザーの質問への最終回答を日本語で作成してください。各おすすめ "
              "場所には名前と簡単な説明を含めてください。",
    }.get(user_lang) if lang in ("ko", "en", "ja") else (
        "Do not call any more tools. Using only the places found so far, write "
        "the final answer in the SAME LANGUAGE as the user's original question. "
        "Include each recommended place's name and a short description.")

    for turn in range(MAX_TURNS):
        is_last = turn == MAX_TURNS - 1
        if is_last:
            turn_config = types.GenerateContentConfig(
                system_instruction=system_instruction,
            )
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=final_directive)],
            ))
        else:
            turn_config = config

        response = await gemini.aio.models.generate_content(
            model=GEMINI_MODEL, contents=contents, config=turn_config,
        )
        cand = response.candidates[0]
        parts = cand.content.parts or []
        fcalls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not fcalls:
            answer = response.text or ""
            await _enrich_with_media(collected, user_lang)
            return {
                "answer": answer,
                "tool_calls": tool_log,
                "spots": _spots_in_answer_order(answer, collected),
                "lang": user_lang,
            }

        contents.append(cand.content)
        tool_response_parts = []
        for fc in fcalls:
            args = dict(fc.args) if fc.args else {}
            result_text = await _run_tool(fc.name, args, collected, user_lang)
            tool_log.append({
                "name": fc.name,
                "args": args,
                "count": (len(json.loads(result_text)) if result_text.startswith("[") else 1),
            })
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name, response={"result": result_text},
                )
            )
        contents.append(types.Content(role="user", parts=tool_response_parts))

    # Should not reach here (last turn forces a text answer), but just in case:
    await _enrich_with_media(collected, user_lang)
    return {"answer": "(최종 답변 생성에 실패했습니다.)", "tool_calls": tool_log,
            "spots": list(collected.values()), "lang": user_lang}
