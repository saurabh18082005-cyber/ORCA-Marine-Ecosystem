"""
API Middleware for ORCA Backend (SIH26176)
Provides CORS configuration, execution timing, structured error handling,
and rate limiting logging.
"""

import time
import logging
import os
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("orca.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class ProcessTimeAndLoggingMiddleware(BaseHTTPMiddleware):
    """Measures API execution time and adds X-Process-Time header."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        path = request.url.path
        method = request.method

        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000.0
            response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
            logger.info(f"{method} {path} - Status: {response.status_code} ({process_time:.2f}ms)")
            return response
        except Exception as exc:
            process_time = (time.time() - start_time) * 1000.0
            logger.error(f"{method} {path} Failed after {process_time:.2f}ms - Exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "detail": str(exc),
                    "path": path,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
            )


def setup_cors_origins():
    """Returns list of allowed CORS origins for development & production."""
    configured = os.getenv("CORS_ORIGINS", "")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]


def setup_cors_origin_regex():
    """
    Optional regex of additionally-allowed CORS origins, layered on top of
    setup_cors_origins().

    Only takes effect when CORS_ORIGINS is NOT explicitly set (an explicit
    production origin list should be exact, not pattern-matched). Its
    purpose is local network testing: when a phone opens the Vite dev
    server at e.g. http://192.168.1.42:5173, its requests to the backend
    carry that Origin header, which isn't in the localhost-only default
    list above and would otherwise be silently blocked by CORS -- the
    request never even reaches your route, so it looks like a broken API
    rather than a permissions issue. This regex matches the private LAN
    address ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x) on any port, so
    same-network mobile testing works without manually editing CORS_ORIGINS
    every time your IP changes. Set CORS_ORIGINS explicitly in production
    to disable this and pin down the exact allowed origin(s).
    """
    if os.getenv("CORS_ORIGINS", ""):
        return None
    return (
        r"^https?://("
        r"192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    )
