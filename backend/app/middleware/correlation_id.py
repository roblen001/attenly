"""Correlation ID middleware for request tracing."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import uuid
import logging

logger = logging.getLogger(__name__)

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Adds correlation IDs to requests for tracing across services.
    
    - Extracts correlation ID from X-Correlation-ID header if present
    - Generates new UUID if not provided
    - Adds correlation ID to response headers
    - Logs correlation ID with each request
    """
    
    async def dispatch(self, request: Request, call_next):
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Store in request state for access in route handlers
        request.state.correlation_id = correlation_id
        
        # Log request with correlation ID
        logger.info(
            f"Request started",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
        
        # Process request
        response = await call_next(request)
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        # Log response with correlation ID
        logger.info(
            f"Request completed",
            extra={
                "correlation_id": correlation_id,
                "status_code": response.status_code,
                "method": request.method,
                "path": request.url.path
            }
        )
        
        return response
