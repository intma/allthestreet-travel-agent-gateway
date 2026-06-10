"""
Video index — connect short-form videos to spots WITHOUT touching the backend VM.

The existing `/api_mukbang/get_video_data` endpoint already returns, for each
video, the spots it features (and each spot also carries `spot_videos`). We pull
that feed once, invert it into a `{spot_id: [VideoRef, ...]}` index, and cache it
in memory. Page/UCP/GEO then attach videos to a spot by lookup — no new backend
endpoint, no VM access required.

The feed is large (~6.5k videos), so we page through it once and cache with a
TTL. Cloud Run keeps this in process memory; a cold instance rebuilds on first use.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings


@dataclass
class VideoRef:
    video_id: int
    youtube_id: str            # e.g. "GR9dicceTPE" (the API's video_url)
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    timeframe_sec: Optional[int] = None  # spot_timeframe, seconds into the clip
    lang: str = "other"        # "ko" | "ja" | "en" | "other" (detected from title)
    published: float = 0.0     # sort key for "latest" (epoch seconds)

    @property
    def youtube_url(self) -> str:
        base = f"https://www.youtube.com/watch?v={self.youtube_id}"
        if self.timeframe_sec and self.timeframe_sec > 0:
            return f"{base}&t={self.timeframe_sec}s"
        return base

    @property
    def youtube_thumbnail(self) -> str:
        return self.thumbnail_url or f"https://i.ytimg.com/vi/{self.youtube_id}/hqdefault.jpg"


def _to_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _detect_lang(title: Optional[str]) -> str:
    """Detect video language from its title by script.

    Kana (hiragana/katakana) => Japanese; Hangul => Korean; otherwise if it has
    Latin letters => English; else 'other'. Kana is checked first because a
    Japanese title may also contain shared Han characters.
    """
    if not title:
        return "other"
    has_kana = any(
        ("\u3040" <= ch <= "\u309f") or ("\u30a0" <= ch <= "\u30ff")
        for ch in title
    )
    if has_kana:
        return "ja"
    has_hangul = any("\uac00" <= ch <= "\ud7a3" for ch in title)
    if has_hangul:
        return "ko"
    has_latin = any(("a" <= ch.lower() <= "z") for ch in title)
    if has_latin:
        return "en"
    return "other"


def _parse_published(v: dict) -> float:
    """Best-effort 'latest' sort key. Prefer publish_time, fall back to create_time."""
    pt = v.get("video_publish_time")
    if pt:
        try:
            from datetime import datetime
            return datetime.strptime(pt, "%Y-%m-%dT%H:%M:%SZ").timestamp()
        except (ValueError, TypeError):
            pass
    ct = v.get("create_time")
    try:
        return float(ct)
    except (TypeError, ValueError):
        return 0.0


class VideoIndex:
    """In-memory spot_id -> [VideoRef] index, built from get_video_data."""

    def __init__(self, ttl_seconds: int = 12 * 3600, max_pages: int = 200, page_size: int = 100):
        self.ttl = ttl_seconds
        self.max_pages = max_pages
        self.page_size = page_size
        self._index: dict[int, list[VideoRef]] = {}
        self._built_at: float = 0.0
        self._building = False
        self._lock: Optional["asyncio.Lock"] = None

    def _get_lock(self) -> "asyncio.Lock":
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()
        return self._lock

    def _fresh(self) -> bool:
        return self._index and (time.time() - self._built_at) < self.ttl

    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list[dict]:
        url = f"{settings.SOURCE_API_BASE}/api_mukbang/get_video_data"
        resp = await client.get(url, params={"page": page, "pageSize": self.page_size})
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    async def build(self) -> None:
        """Page through the video feed and (re)build the spot->videos index.

        A lock serializes concurrent builds: the first request builds, the rest
        wait and then reuse the fresh index (instead of returning an empty one,
        which is what caused videos to silently vanish on serverless cold start)."""
        async with self._get_lock():
            if self._fresh():  # another coroutine just finished building
                return
            index: dict[int, list[VideoRef]] = {}
            seen: dict[int, set[int]] = {}  # spot_id -> set(video_id) to dedupe
            self._building = True
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    for page in range(1, self.max_pages + 1):
                        rows = await self._fetch_page(client, page)
                        if not rows:
                            break
                        for v in rows:
                            for s in v.get("spots", []) or []:
                                sid = _to_int(s.get("spot_id"))
                                if sid is None:
                                    continue
                                vid = _to_int(v.get("video_id"))
                                yt = v.get("video_url") or s.get("spot_videos", [{}])[0].get("video_url")
                                if not yt:
                                    continue
                                bucket = index.setdefault(sid, [])
                                seenset = seen.setdefault(sid, set())
                                if vid in seenset:
                                    continue
                                seenset.add(vid)
                                bucket.append(VideoRef(
                                    video_id=vid or 0,
                                    youtube_id=yt,
                                    title=v.get("video_title"),
                                    thumbnail_url=v.get("video_thumbnail_url"),
                                    timeframe_sec=_to_int(s.get("spot_timeframe")),
                                    lang=_detect_lang(v.get("video_title")),
                                    published=_parse_published(v),
                                ))
                if index:
                    self._index = index
                    self._built_at = time.time()
            finally:
                self._building = False

    async def get(self, spot_id: int, per_lang: bool = True) -> list[VideoRef]:
        if not self._fresh():
            if self._index:
                # Stale-while-revalidate: serve the old index now, rebuild in
                # the background (the lock in build() prevents duplicates).
                import asyncio as _aio
                _aio.create_task(self.build())
            else:
                await self.build()
        refs = self._index.get(spot_id, [])
        if not per_lang:
            return refs
        return self._latest_per_lang(refs)

    @staticmethod
    def _latest_per_lang(refs: list[VideoRef]) -> list[VideoRef]:
        """Keep the single most-recent video for each of ko / ja / en.

        Returns up to 3 videos, ordered ko, ja, en (languages that exist).
        'other'-language videos are only used if none of ko/ja/en exist.
        """
        best: dict[str, VideoRef] = {}
        for r in refs:
            cur = best.get(r.lang)
            if cur is None or r.published > cur.published:
                best[r.lang] = r
        ordered = [best[l] for l in ("ko", "ja", "en") if l in best]
        if ordered:
            return ordered
        # Fallback: nothing matched the three languages -> newest 'other'.
        if "other" in best:
            return [best["other"]]
        return []


# Singleton index shared across requests.
video_index = VideoIndex()
