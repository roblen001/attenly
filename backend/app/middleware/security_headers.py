"""Security headers middleware for production deployment."""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import os

async def security_headers_middleware(request, call_next):
    """
    Adds essential security headers to all HTTP responses and removes sensitive headers.
    
    Headers added:
    - X-Frame-Options: Prevents clickjacking attacks
    - X-Content-Type-Options: Prevents MIME type sniffing
    - Referrer-Policy: Controls referrer information
    - X-XSS-Protection: Disabled (deprecated, use CSP instead)
    """
    response: Response = await call_next(request)

    # Remove sensitive/branding headers if present
    for h in ("server", "x-powered-by"):
        if h in response.headers:
            del response.headers[h]

    # Set security headers (idempotent overwrites)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"  # XSS filter deprecated; use CSP instead
    
    # Add HSTS header for HTTPS connections
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Example CSP (tune to your app)
    # response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self';"

    return response

# Legacy class wrapper for backward compatibility
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Wrapper class to maintain compatibility with existing middleware registration."""
    
    async def dispatch(self, request: Request, call_next):
        return await security_headers_middleware(request, call_next)
