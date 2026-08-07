"""IP-based rate limiting using SlowAPI."""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException, status
import logging

logger = logging.getLogger(__name__)

# Create limiter instance
limiter = Limiter(key_func=get_remote_address)

def get_limiter():
    """Get the configured rate limiter instance."""
    return limiter

def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom rate limit handler that logs attempts and returns structured error.
    """
    client_ip = get_remote_address(request)
    
    # Log rate limit violation
    logger.warning(
        "Rate limit exceeded",
        extra={
            "client_ip": client_ip,
            "path": request.url.path,
            "method": request.method,
            "rate_limit": str(exc.detail),
            "correlation_id": getattr(request.state, 'correlation_id', 'unknown')
        }
    )
    
    # Return structured error response
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please wait before trying again.",
            "retry_after": exc.retry_after if hasattr(exc, 'retry_after') else 60
        },
        headers={"Retry-After": str(getattr(exc, 'retry_after', 60))}
    )

# Common rate limit configurations
RATE_LIMITS = {
    "auth": "10/minute",      # Login attempts
    "oidc_login": "300/minute",  # Enterprise users may share a corporate NAT
    "oidc_callback": "600/minute",  # Do not strand completed IdP sign-ins
    "upload": "5/minute",     # File uploads
    "llm": "3/minute",        # LLM processing
    "general": "100/minute",  # General API calls
    "health": "60/minute"     # Health checks
}

def get_rate_limit(limit_type: str) -> str:
    """Get rate limit string for a specific endpoint type."""
    return RATE_LIMITS.get(limit_type, RATE_LIMITS["general"])
