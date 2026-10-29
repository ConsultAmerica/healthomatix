"""V1.8 application security helpers: headers, rate limits, MFA claim checks."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.auth import ApiError
from app.config import settings


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def apply_security_headers(response: Response) -> None:
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    if settings.environment == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        apply_security_headers(response)
        return response


class InMemoryRateLimiter:
    """Process-local fixed-window limiter. Not a distributed production control."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


_rate_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path.startswith("/api/v1/health"):
            return await call_next(request)
        if not settings.api_rate_limit_enabled:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{path.split('/tenants/')[0]}"
        if not _rate_limiter.allow(
            key,
            limit=settings.api_rate_limit_per_minute,
            window_seconds=60,
        ):
            return Response(
                content='{"error":{"code":"RATE_LIMITED","message":"Too many requests."}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60", "Cache-Control": "no-store"},
            )
        return await call_next(request)


def token_has_mfa(claims: dict[str, Any] | None) -> bool:
    if not claims:
        return False
    amr = claims.get("amr")
    if isinstance(amr, list):
        methods = {str(item).lower() for item in amr}
        if methods & {"mfa", "otp", "sms", "hwk", "pop"}:
            return True
        if any("mfa" in method for method in methods):
            return True
    acr = str(claims.get("acr") or "").lower()
    if "mfa" in acr or acr in {"aal2", "aal3"}:
        return True
    if claims.get("healthomatix_mfa") is True:
        return True
    return False


def enforce_platform_admin_mfa(request: Request) -> None:
    """When enabled, platform admins must present an MFA-satisfied access token."""
    if not settings.require_mfa_for_platform_admin:
        return
    if settings.demo_auth_enabled and request.headers.get("x-demo-user"):
        # Demo mode is synthetic-only; MFA requirement applies to real OIDC.
        return
    claims = getattr(request.state, "access_token_claims", None)
    if not token_has_mfa(claims if isinstance(claims, dict) else None):
        raise ApiError(
            "MFA_REQUIRED",
            "Multi-factor authentication is required for platform administration.",
            403,
        )
