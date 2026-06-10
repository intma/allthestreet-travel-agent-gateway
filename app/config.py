"""
Configuration for the AllTheStreet Agent Gateway.

All values come from environment variables (12-factor). Nothing sensitive is
hardcoded — on Cloud Run these are injected, ideally from Secret Manager.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Upstream data source (existing Flask backend).
    SOURCE_API_BASE: str = os.getenv(
        "SOURCE_API_BASE", "https://api.allthestreet.com"
    )

    # Public base URL of THIS gateway (used to build canonical @id/url in JSON-LD).
    PUBLIC_BASE_URL: str = os.getenv(
        "PUBLIC_BASE_URL", "https://gateway.allthestreet.com"
    )

    # CORS allowlist (comma-separated). Default is restrictive; widen per deploy.
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS", "https://korea.allthestreet.com"
    )

    # Optional API key to protect MCP / write-ish surfaces later (read endpoints
    # stay public so Gemini & search crawlers can fetch JSON-LD).
    GATEWAY_API_KEY: str = os.getenv("GATEWAY_API_KEY", "")

    # Google Maps/Places key — used SERVER-SIDE ONLY to proxy place photos.
    # Never emitted to clients. Inject via Secret Manager on Cloud Run.
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # Gemini API key for the /demo agent (server-side function-calling over MCP
    # tools). SERVER-ONLY — inject via Secret Manager on Cloud Run, never client.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # gemini-2.0-flash was shut down 2026-06-01; 3.5-flash is current GA.
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    # Hosts/origins the MCP server accepts (DNS-rebinding protection).
    # Comma-separated. On Cloud Run, set to the deployed *.run.app host.
    # Use "*" to disable host checking (simplest for a public read-only MCP).
    MCP_ALLOWED_HOSTS: str = os.getenv("MCP_ALLOWED_HOSTS", "*")

    # Path for fetching one product's full record (with product_extra/commerce).
    # '{id}' is substituted with the product id. Confirmed from admin XHR:
    # GET /api_mukbang/product/{id} (singular). Returns the product with
    # product_extra holding the commerce[] array.
    PRODUCT_DETAIL_PATH: str = os.getenv(
        "PRODUCT_DETAIL_PATH", "/api_mukbang/product/{id}"
    )

    # Max width when fetching Google Place photos (px).
    PLACE_PHOTO_MAX_WIDTH: int = int(os.getenv("PLACE_PHOTO_MAX_WIDTH", "800"))

    ENV: str = os.getenv("ENV", "development")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
