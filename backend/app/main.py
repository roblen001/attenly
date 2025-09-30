# main.py
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.db import Base, engine
from app.routers import auth, agents
from app.routes import health
from app.config import validate_config, get_config_summary
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.correlation_id import CorrelationIDMiddleware
from app.middleware.request_size import RequestSizeLimitMiddleware, get_request_size_limit
from app.limits.slowapi import limiter, rate_limit_handler

import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Attenly", 
    version="1.0.0",
    description="AI-powered document processing and report generation platform",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENV") != "production" else None
)

# Validate configuration on startup
try:
    validate_config()
    config_summary = get_config_summary()
    logger.info("Configuration validation successful")
    logger.info(f"Configuration summary: {config_summary}")
except ValueError as e:
    logger.error(f"Configuration validation failed: {e}")
    sys.exit(1)

# Create database tables (development only)
if os.getenv("ENV") != "production":
    logger.info("Creating database tables for development")
    Base.metadata.create_all(bind=engine)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Add security middlewares (order matters!)
app.add_middleware(RequestSizeLimitMiddleware, max_upload_size=get_request_size_limit())
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIDMiddleware)

# CORS configuration 
cors_origins = os.getenv("CORS_ORIGINS",
    "https://app.attenly.ca,https://attenly.ca,https://www.attenly.ca"
).split(",")
cors_origins = [o.strip() for o in cors_origins]

# dev extras…
if os.getenv("ENV") != "production":
    cors_origins += [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,   # you’re using bearer tokens
    allow_methods=["GET","POST","PUT","DELETE","PATCH","OPTIONS"],
    allow_headers=[
        "Authorization","Content-Type","X-Correlation-ID","Idempotency-Key",
        "Accept","Origin","User-Agent","Apikey","X-Client-Info","Prefer","Range"
    ],
    expose_headers=["Content-Range","X-Content-Range"],
    max_age=86400,
)


# Global exception handler for security
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler that prevents information leakage.
    """
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    
    # Log the actual error with correlation ID
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "method": request.method,
            "client_ip": request.client.host if request.client else "unknown"
        },
        exc_info=True
    )
    
    # Return generic error to client (don't leak internal details)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "correlation_id": correlation_id
        },
        headers={"X-Correlation-ID": correlation_id}
    )

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(agents.router, tags=["agents"])

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0" if os.getenv("ENV") == "production" else "127.0.0.1"
    
    uvicorn.run(
        "app.main:app", 
        host=host, 
        port=port, 
        reload=os.getenv("ENV") != "production",
        access_log=True,
        log_level="info",
        server_header=False
    )
