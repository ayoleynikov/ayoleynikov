"""ASGI middleware: API rate limiting."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pulse.config import Settings
from pulse.security.rate_limit import ApiRateLimiter

# Paths excluded from rate limiting (probes / metrics scrapes).
_EXEMPT_PREFIXES = ("/health", "/ready", "/metrics")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings: Settings, limiter: ApiRateLimiter | None = None) -> None:
        super().__init__(app)
        self.settings = settings
        self.limiter = limiter or ApiRateLimiter(
            max_requests=settings.api_rate_limit_requests,
            window_seconds=settings.api_rate_limit_window_seconds,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.settings.api_rate_limit_enabled:
            return await call_next(request)
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _EXEMPT_PREFIXES):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{path.split('/')[1] if path.startswith('/') else path}"
        if not self.limiter.allow(key):
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={"Retry-After": str(int(self.settings.api_rate_limit_window_seconds))},
            )
        return await call_next(request)
