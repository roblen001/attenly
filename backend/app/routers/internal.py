"""
Internal API Router

Endpoints for internal use (cron jobs, admin tasks, etc.)
These endpoints use header-based authentication, not JWT.
"""

import logging
from fastapi import APIRouter, Request, HTTPException, status, Header
from fastapi.responses import JSONResponse

from app.config import INBOUND_EMAIL_PROVIDER, INTERNAL_CRON_SECRET
from app.services.email_job_service import get_email_job_service

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_cron_secret(x_cron_secret: str = Header(None)) -> bool:
    """
    Verify the cron secret from request headers.
    
    Args:
        x_cron_secret: Secret from X-Cron-Secret header
        
    Returns:
        True if valid, raises HTTPException if invalid
    """
    if not x_cron_secret:
        logger.warning("Cron endpoint called without secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Cron-Secret header"
        )
    
    # Get expected secret from config
    expected_secret = INTERNAL_CRON_SECRET
    
    if not expected_secret or expected_secret == "change-me-in-production":
        logger.error("INTERNAL_CRON_SECRET not configured properly")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal configuration error"
        )
    
    if x_cron_secret != expected_secret:
        logger.warning("Invalid cron secret provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Cron-Secret"
        )
    
    return True


def poll_inbound_email_if_configured() -> dict | None:
    if INBOUND_EMAIL_PROVIDER != "microsoft_graph":
        return None

    from app.services.microsoft_graph_inbound_service import get_microsoft_graph_inbound_poller

    return get_microsoft_graph_inbound_poller().poll_messages()


@router.post("/internal/process-email-jobs")
async def process_email_jobs(
    request: Request,
    x_cron_secret: str = Header(None, alias="X-Cron-Secret")
):
    """
    Process pending email jobs (called by cron scheduler).
    
    This endpoint is designed to be called every 1-2 minutes by an external cron service.
    It processes up to 10 pending jobs per invocation to avoid long-running requests.
    
    Security: Requires X-Cron-Secret header matching INTERNAL_CRON_SECRET env var.
    
    Response:
        - 200: Processing complete (may have processed 0 jobs)
        - 401: Invalid/missing secret
        - 500: Processing error
    """
    # Verify authentication
    verify_cron_secret(x_cron_secret)
    
    logger.info("Cron endpoint triggered - processing email jobs")
    
    try:
        inbound_poll = poll_inbound_email_if_configured()

        # Get email job service
        email_job_service = get_email_job_service()
        
        # Process up to 10 jobs
        result = await email_job_service.process_pending_jobs(max_jobs=10)
        
        # Log summary
        if result["jobs_processed"] > 0:
            logger.info(
                f"Processed {result['jobs_processed']} jobs: "
                f"{result['jobs_successful']} successful, {result['jobs_failed']} failed"
            )
        else:
            logger.info("No pending jobs to process")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Email job processing complete",
                "inbound_poll": inbound_poll,
                "summary": result
            }
        )
    
    except Exception as e:
        logger.error(f"Error in cron endpoint: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Internal processing error",
                "message": str(e)
            }
        )


@router.post("/internal/poll-inbound-email")
async def poll_inbound_email(
    request: Request,
    x_cron_secret: str = Header(None, alias="X-Cron-Secret")
):
    """Poll configured inbound email provider without processing queued jobs."""
    verify_cron_secret(x_cron_secret)

    if INBOUND_EMAIL_PROVIDER != "microsoft_graph":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "No polling provider configured",
                "provider": INBOUND_EMAIL_PROVIDER,
            },
        )

    try:
        result = poll_inbound_email_if_configured()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Inbound email polling complete",
                "summary": result,
            },
        )
    except Exception as e:
        logger.error(f"Error polling inbound email: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Inbound polling error",
                "message": str(e),
            },
        )


@router.get("/internal/health")
async def internal_health_check(x_cron_secret: str = Header(None, alias="X-Cron-Secret")):
    """
    Health check endpoint for internal monitoring.
    Can be used to verify cron configuration without processing jobs.
    """
    # Verify authentication
    verify_cron_secret(x_cron_secret)
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "email-job-processor",
            "message": "Internal API is operational"
        }
    )
