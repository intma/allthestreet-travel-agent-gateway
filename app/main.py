"""
AllTheStreet Agent Gateway — FastAPI entrypoint.

A read-only service that exposes AllTheStreet's curated place/product data to
Gemini and search engines via three layers:
  - GEO  : Schema.org JSON-LD            (search / semantic markup)
  - UCP  : Universal Commerce JSON       (commerce discovery)
  - MCP  : Model Context Protocol tools  (live agent queries)

The MCP server is mounted into THIS app at /mcp, so the whole gateway deploys
as a single Cloud Run service. Runs read-only; reads upstream over HTTP.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.mcp.server import mcp
from app.routes import demo_routes, geo_routes, health, image_routes, page_routes, ucp_routes

# MCP streamable-HTTP ASGI app (Starlette). It owns a session manager that must
# be started/stopped via lifespan, so we bridge its lifespan into FastAPI's.
mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Drive the MCP session manager's lifespan alongside the FastAPI app.
    async with mcp.session_manager.run():
        # Warm the spot index in the background so the first /p/{id} request is
        # fast (tier-1 full build runs off the request path). Failure is
        # non-fatal — get_spot will lazily build on demand if this didn't finish.
        import asyncio
        from app.data.repository import SpotRepository

        async def _warm():
            try:
                await SpotRepository().build_spot_index()
            except Exception:
                pass
            try:
                from app.data.videos import video_index
                await video_index.build()
            except Exception:
                pass

        task = asyncio.create_task(_warm())
        try:
            yield
        finally:
            task.cancel()


class MCPSlashMiddleware(BaseHTTPMiddleware):
    """
    The MCP app is mounted at /mcp and its internal route is '/', so the real
    endpoint is '/mcp/'. A bare '/mcp' would normally 307-redirect to '/mcp/',
    but MCP's streamable-HTTP POST stream breaks across that redirect.

    This middleware rewrites an exact '/mcp' path to '/mcp/' in-place (no
    redirect), so clients work whether or not they include the trailing slash.
    """

    async def dispatch(self, request, call_next):
        if request.scope["path"] == "/mcp":
            request.scope["path"] = "/mcp/"
        return await call_next(request)


app = FastAPI(
    title="AllTheStreet Agent Gateway",
    version="0.4.0",
    description=(
        "Read-only gateway exposing AllTheStreet places/products to Gemini "
        "and search engines via GEO (JSON-LD), UCP, and MCP."
    ),
    lifespan=lifespan,
)

app.add_middleware(MCPSlashMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(geo_routes.router)
app.include_router(ucp_routes.router)
app.include_router(image_routes.router)
app.include_router(page_routes.router)
app.include_router(demo_routes.router)

# Mount the MCP server. Clients connect to {PUBLIC_BASE_URL}/mcp.
app.mount("/mcp", mcp_app)


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "service": "allthestreet-agent-gateway",
        "version": app.version,
        "layers": {
            "geo": ["/geo/spot/{id}.jsonld", "/geo/spots.jsonld", "/sitemap.xml", "/robots.txt"],
            "ucp": ["/.well-known/ucp.json", "/ucp/feed", "/ucp/spot/{id}"],
            "page": ["/p/{id}"],
            "demo": "/demo",
            "mcp": {
                "endpoint": "/mcp",
                "tools": ["search_spots", "get_spot_detail", "list_recent_spots"],
            },
        },
        "docs": "/docs",
    }
