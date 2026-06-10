"""Health & readiness endpoints for Cloud Run."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness — process is up."""
    return {"status": "ok", "env": settings.ENV}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness — report which upstream we read from."""
    return {
        "status": "ready",
        "source_api": settings.SOURCE_API_BASE,
        "public_base": settings.PUBLIC_BASE_URL,
    }
