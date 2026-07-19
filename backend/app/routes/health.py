"""Health check endpoints for monitoring and load balancer integration."""
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from app.limits.slowapi import limiter, get_rate_limit
from app.client import supabase_client
import logging
import time
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
@limiter.limit(get_rate_limit("health"))
async def health_check(request: Request):
    """
    Basic health check endpoint for load balancers.
    
    This endpoint:
    - Does not check external dependencies
    - Returns quickly for load balancer health checks
    - Is rate limited to prevent abuse
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "timestamp": int(time.time()),
            "service": "attenly-api",
            "version": "1.0.0"
        }
    )

@router.get("/ready")
@limiter.limit(get_rate_limit("health"))
async def readiness_check(request: Request):
    """
    Comprehensive readiness check that validates all external dependencies.
    
    This endpoint checks:
    - Selected database provider connectivity
    - Persistent filesystem writability for local storage
    - Configuration validity
    
    Returns 503 if any dependency is unavailable.
    """
    start_time = time.time()
    checks = {
        "database": {"status": "unknown", "response_time": None},
        "storage": {"status": "unknown"},
        "configuration": {"status": "unknown"}
    }
    
    overall_status = "healthy"
    status_code = status.HTTP_200_OK
    
    # Check selected database
    try:
        from app import config

        db_start = time.time()
        if config.DATABASE_PROVIDER == "supabase":
            if supabase_client is None:
                raise RuntimeError("Supabase client is not configured")
            supabase_client.table("agents").select("id").limit(1).execute()
        elif config.DATABASE_PROVIDER == "sqlalchemy":
            from sqlalchemy import text
            from app.db import engine

            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        else:
            raise RuntimeError(f"Unsupported database provider: {config.DATABASE_PROVIDER}")

        checks["database"]["status"] = "healthy"
        checks["database"]["response_time"] = round((time.time() - db_start) * 1000, 2)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"]["status"] = "unhealthy"
        checks["database"]["error"] = str(e)
        overall_status = "unhealthy"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # The local self-hosted profile must be able to write to its persistent
    # Docker volume before it is considered ready.
    try:
        from app import config

        if config.STORAGE_PROVIDER == "filesystem":
            storage_root = Path(config.FILESYSTEM_STORAGE_PATH).expanduser().resolve()
            storage_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                prefix=".attenly-readiness-",
                dir=storage_root,
            ) as probe:
                probe.write(b"ready")
                probe.flush()
            checks["storage"]["status"] = "healthy"
            checks["storage"]["provider"] = "filesystem"
        else:
            # External storage is exercised by application operations. Readiness
            # validates its configuration without creating user data.
            checks["storage"]["status"] = "configured"
            checks["storage"]["provider"] = config.STORAGE_PROVIDER
    except Exception as e:
        logger.error(f"Storage readiness check failed: {e}")
        checks["storage"]["status"] = "unhealthy"
        checks["storage"]["error"] = str(e)
        overall_status = "unhealthy"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    # Check configuration
    try:
        from app.config import validate_config
        validate_config()
        checks["configuration"]["status"] = "healthy"
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        checks["configuration"]["status"] = "unhealthy"
        checks["configuration"]["error"] = str(e)
        overall_status = "unhealthy"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    total_time = round((time.time() - start_time) * 1000, 2)
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": int(time.time()),
            "service": "attenly-api",
            "version": "1.0.0",
            "checks": checks,
            "total_response_time_ms": total_time,
            "environment": os.getenv("ENV", "development")
        }
    )

@router.get("/metrics")
@limiter.limit(get_rate_limit("health"))
async def metrics_endpoint(request: Request):
    """
    Basic metrics endpoint in Prometheus format.
    
    This is a placeholder for future metrics integration.
    In production, you might use proper monitoring tools like DataDog or New Relic.
    """
    metrics = [
        "# HELP attently_health_check Health check status",
        "# TYPE attently_health_check gauge",
        "attently_health_check{service=\"attenly-api\",version=\"1.0.0\"} 1",
        "",
        "# HELP attently_uptime_seconds Service uptime in seconds",
        "# TYPE attently_uptime_seconds counter",
        f"attently_uptime_seconds {int(time.time())}",
    ]
    
    return "\n".join(metrics)
