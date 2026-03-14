
"""
Security Headers Middleware

Adds security headers to all HTTP responses to protect against common web vulnerabilities.
Uses config-driven HSTS max-age and conditionally skips headers in development.

Non-breaking improvements:
- Adds X-Content-Type-Options: nosniff
- Adds Cross-Origin-* isolation headers (COOP/CORP, optional COEP in production)
- Uses settings.API_PREFIX (instead of hardcoded '/api/') when disabling cache
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Skip entirely when ENABLE_SECURITY_HEADERS is False (development).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Skip entirely when disabled (commonly for development)
        if not settings.ENABLE_SECURITY_HEADERS:
            return response

        # -------------------------
        # Basic hardening headers
        # -------------------------

        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Enable XSS filter (legacy browsers; modern Chromium ignores it)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Prevent MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # -------------------------
        # HSTS (HTTPS only)
        # -------------------------
        # HSTS should only be enabled when you're sure you're serving HTTPS.
        # We keep your existing behavior (not DEBUG) and add an extra safety guard:
        # - in production OR when COOKIE_SECURE is True (if setting exists)
        if not settings.DEBUG:
            cookie_secure = getattr(settings, "COOKIE_SECURE", None)
            should_set_hsts = settings.is_production if hasattr(settings, "is_production") else True
            if cookie_secure is not None:
                should_set_hsts = should_set_hsts or bool(cookie_secure)

            if should_set_hsts:
                max_age = settings.HSTS_MAX_AGE
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={max_age}; includeSubDomains; preload"
                )

        # -------------------------
        # Content Security Policy (CSP)
        # -------------------------
        if getattr(settings, "is_production", False):
            # Tighter CSP for production (no unsafe-eval)
            csp_directives = [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data:",
                "font-src 'self' data:",
                "connect-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "upgrade-insecure-requests",
            ]
        else:
            # Relaxed CSP for development/staging (allows Vue.js HMR)
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https:",
                "font-src 'self' data:",
                "connect-src 'self' https: ws: wss:",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # -------------------------
        # Referrer + Permissions
        # -------------------------
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        permissions_policy = [
            "accelerometer=()",
            "camera=()",
            "geolocation=()",
            "gyroscope=()",
            "magnetometer=()",
            "microphone=()",
            "payment=()",
            "usb=()",
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions_policy)

        # -------------------------
        # Cross-Origin isolation headers
        # -------------------------
        # Safe defaults for APIs. COEP can break some integrations; enable only in production.
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        if getattr(settings, "is_production", False):
            # Optional: enforce embedder policy in production
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

        # -------------------------
        # Prevent caching of sensitive API responses
        # -------------------------
        api_prefix = getattr(settings, "API_PREFIX", "/api")
        if request.url.path.startswith(api_prefix):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response