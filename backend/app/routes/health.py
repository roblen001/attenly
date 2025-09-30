"""Health check endpoints for monitoring and load balancer integration."""
from fastapi import APIRouter, status, Depends
from fastapi.responses import JSONResponse
from app.limits.slowapi import limiter, get_rate_limit
from app.limits.redis_bucket import get_token_bucket
from app.client import supabase_client
import logging
import time
import os

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
@limiter.limit(get_rate_limit("health"))
async def health_check(request):
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
async def readiness_check(request):
    """
    Comprehensive readiness check that validates all external dependencies.
    
    This endpoint checks:
    - Supabase database connectivity
    - Redis connectivity (if configured)
    - Configuration validity
    
    Returns 503 if any dependency is unavailable.
    """
    start_time = time.time()
    checks = {
        "database": {"status": "unknown", "response_time": None},
        "redis": {"status": "unknown", "response_time": None},
        "configuration": {"status": "unknown"}
    }
    
    overall_status = "healthy"
    status_code = status.HTTP_200_OK
    
    # Check Supabase database
    try:
        db_start = time.time()
        # Simple query to test database connectivity
        result = supabase_client.table("agents").select("id").limit(1).execute()
        checks["database"]["status"] = "healthy"
        checks["database"]["response_time"] = round((time.time() - db_start) * 1000, 2)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"]["status"] = "unhealthy"
        checks["database"]["error"] = str(e)
        overall_status = "unhealthy"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    # Check Redis (optional - fail gracefully if not configured)
    try:
        redis_start = time.time()
        token_bucket = get_token_bucket()
        if token_bucket.redis_client:
            token_bucket.redis_client.ping()
            checks["redis"]["status"] = "healthy"
            checks["redis"]["response_time"] = round((time.time() - redis_start) * 1000, 2)
        else:
            checks["redis"]["status"] = "not_configured"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        checks["redis"]["status"] = "unhealthy"
        checks["redis"]["error"] = str(e)
        # Redis failure doesn't make the service unhealthy (fail gracefully)
    
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
async def metrics_endpoint(request):
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
