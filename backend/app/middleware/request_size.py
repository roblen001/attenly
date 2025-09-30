"""Request body size limiting middleware for FastAPI."""
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging
import os

logger = logging.getLogger(__name__)

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit request body size at the application level.
    
    This provides a first line of defense against oversized requests,
    complementing the file-level validation in FileSecurityService.
    """
    
    def __init__(self, app, max_upload_size: int = 50 * 1024 * 1024):
        """
        Initialize request size limit middleware.
        
        Args:
            app: FastAPI application instance
            max_upload_size: Maximum request body size in bytes (default: 50MB)
        """
        super().__init__(app)
        self.max_upload_size = max_upload_size
        self.max_upload_size_mb = max_upload_size / (1024 * 1024)
        
        logger.info(f"Request size limit middleware initialized: {self.max_upload_size_mb:.1f}MB max")
    
    async def dispatch(self, request: Request, call_next):
        """
        Check request body size before processing.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler
            
        Returns:
            Response: HTTP response
            
        Raises:
            HTTPException: If request body exceeds size limit
        """
        # Skip size check for certain endpoints that don't need it
        if self._should_skip_size_check(request):
            return await call_next(request)
        
        # Check Content-Length header if present
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                content_length_bytes = int(content_length)
                if content_length_bytes > self.max_upload_size:
                    logger.warning(
                        f"Request body too large: {content_length_bytes / (1024 * 1024):.1f}MB "
                        f"exceeds limit of {self.max_upload_size_mb:.1f}MB",
                        extra={
                            "client_ip": request.client.host if request.client else "unknown",
                            "path": request.url.path,
                            "method": request.method,
                            "content_length_mb": round(content_length_bytes / (1024 * 1024), 2),
                            "limit_mb": self.max_upload_size_mb
                        }
                    )
                    
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "error": "Request body too large",
                            "message": f"Request body size {content_length_bytes / (1024 * 1024):.1f}MB "
                                     f"exceeds maximum allowed size of {self.max_upload_size_mb:.1f}MB",
                            "max_size_mb": self.max_upload_size_mb,
                            "actual_size_mb": round(content_length_bytes / (1024 * 1024), 2)
                        },
                        headers={
                            "Retry-After": "3600"  # Suggest retry after 1 hour
                        }
                    )
            except ValueError:
                # Invalid Content-Length header
                logger.warning(f"Invalid Content-Length header: {content_length}")
        
        # For streaming requests without Content-Length, we'll let the request proceed
        # and rely on FastAPI's built-in protections and file-level validation
        
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Log any errors that might be related to request size
            if "too large" in str(e).lower() or "entity too large" in str(e).lower():
                logger.error(
                    f"Request processing failed, possibly due to size: {str(e)}",
                    extra={
                        "client_ip": request.client.host if request.client else "unknown",
                        "path": request.url.path,
                        "method": request.method
                    }
                )
            raise
    
    def _should_skip_size_check(self, request: Request) -> bool:
        """
        Determine if request should skip size checking.
        
        Args:
            request: HTTP request
            
        Returns:
            bool: True if size check should be skipped
        """
        # Skip for GET requests (no body expected)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        
        # Skip for health check endpoints
        if request.url.path in ("/health", "/ready", "/metrics"):
            return True
        
        # Skip for auth endpoints (typically small payloads)
        if request.url.path.startswith("/auth/"):
            return True
        
        return False


# Factory function for easy configuration
def create_request_size_middleware(max_size_mb: int = 50):
    """
    Create request size limit middleware with specified size limit.
    
    Args:
        max_size_mb: Maximum request size in megabytes
        
    Returns:
        Configured middleware class
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    def middleware_factory(app):
        return RequestSizeLimitMiddleware(app, max_upload_size=max_size_bytes)
    
    return middleware_factory


# Configuration based on environment
def get_request_size_limit() -> int:
    """
    Get request size limit from configuration.
    
    Returns:
        int: Maximum request size in bytes
    """
    # Import here to avoid circular imports
    try:
        from app.config import MAX_FILE_SIZE_MB
        max_size_mb = MAX_FILE_SIZE_MB
    except ImportError:
        # Fallback if config not available
        max_size_mb = 50
    
    # Add some overhead for multipart form data encoding
    # Typically adds ~30% overhead for base64 encoding + form boundaries
    overhead_factor = 1.3
    max_size_bytes = int(max_size_mb * 1024 * 1024 * overhead_factor)
    
    return max_size_bytes
