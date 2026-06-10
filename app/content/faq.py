"""
Shared FAQ generation.

Derives conversational Q&A from structured Spot data only (no LLM here).
Used by both the GEO JSON-LD endpoint and the content page so they stay
consistent. Upstream (the existing Gemini extractor) can later supply richer,
curated FAQs to replace these.
"""

from __future__ import annotations

from app.data.repository import Spot


def demo_faq(spot: Spot) -> list[tuple[str, str]]:
    qa: list[tuple[str, str]] = []
    if spot.opening_periods:
        p = spot.opening_periods[0]
        opens = f"{p.open_time[:2]}:{p.open_time[2:]}"
        closes = f"{p.close_time[:2]}:{p.close_time[2:]}"
        qa.append((
            f"{spot.display_name}의 영업시간은 어떻게 되나요?",
            f"{spot.display_name}은(는) 보통 {opens}부터 {closes}까지 영업합니다.",
        ))
    if spot.address_kr:
        qa.append((
            f"{spot.display_name}은(는) 어디에 있나요?",
            f"{spot.address_kr}에 위치해 있습니다.",
        ))
    if spot.phone:
        qa.append((
            f"{spot.display_name}의 연락처는 무엇인가요?",
            f"전화번호는 {spot.phone}입니다.",
        ))
    return qa
