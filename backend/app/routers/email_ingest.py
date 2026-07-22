"""
Email Ingest API Router - User-Facing Email Settings Endpoints

Provides JWT-protected endpoints for users to manage their email ingest
settings, verified senders, and default agents.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from app import config
from app.core.deps import get_current_user
from app.services.email_ingest_service import email_ingest_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email-ingest", tags=["email-ingest"])

EMAIL_INGEST_DISABLED_MESSAGE = (
    "Email ingest is disabled by server configuration. Set "
    "INBOUND_EMAIL_PROVIDER to resend or microsoft_graph to enable it."
)


def is_email_ingest_enabled() -> bool:
    return config.INBOUND_EMAIL_PROVIDER in {"resend", "microsoft_graph"}


def disabled_email_ingest_settings() -> dict:
    return {
        "endpoint": None,
        "delivery_address": None,
        "delivery_mode": None,
        "verified_senders": [],
        "usage_summary": {
            "jobs_last_24h": 0,
            "rate_limit": 0,
        },
        "enabled_by_config": False,
        "provider": config.INBOUND_EMAIL_PROVIDER,
        "message": EMAIL_INGEST_DISABLED_MESSAGE,
    }


def with_delivery_config(settings: dict) -> dict:
    """Add the address operators should give to email senders.

    The generated endpoint remains the internal routing identity. A trusted
    local-auth Microsoft Graph deployment has one workspace and already routes
    the configured mailbox to that endpoint, so advertising the mailbox avoids
    requiring an unnecessary Exchange alias for the one-workspace setup.
    """
    endpoint = settings.get("endpoint") or {}
    generated_address = (endpoint.get("full_address") or "").strip().lower()
    graph_mailbox = (config.GRAPH_MAILBOX or "").strip().lower()
    uses_local_graph_mailbox = (
        config.INBOUND_EMAIL_PROVIDER == "microsoft_graph"
        and config.AUTH_PROVIDER == "local"
        and bool(graph_mailbox)
    )

    return {
        **settings,
        "delivery_address": graph_mailbox if uses_local_graph_mailbox else generated_address or None,
        "delivery_mode": (
            "graph_mailbox"
            if uses_local_graph_mailbox
            else "generated_alias" if generated_address else None
        ),
    }


def sender_verification_redirect(result: str) -> RedirectResponse:
    """Return the browser to the Email Ingest settings with a safe result code."""
    app_url = config.APP_URL.rstrip("/")
    target = f"{app_url}/settings?tab=email&sender_verification={result}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


def require_email_ingest_enabled() -> None:
    if not is_email_ingest_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMAIL_INGEST_DISABLED_MESSAGE,
        )


def extract_jwt_token(authorization: Optional[str] = Header(None, alias="Authorization")) -> str:
    """Extract JWT access token from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return authorization.split(" ")[1]


# =============================================================================
# Pydantic Schemas
# =============================================================================

class EmailIngestEndpoint(BaseModel):
    """Email endpoint information."""
    id: str
    full_address: str
    is_active: bool
    default_agent_id: Optional[str] = None


class VerifiedSenderResponse(BaseModel):
    """Verified sender information for settings response."""
    id: str
    email: str
    is_verified: bool
    created_at: str


class UsageSummary(BaseModel):
    """Usage statistics summary."""
    jobs_last_24h: int
    rate_limit: int


class EmailIngestSettings(BaseModel):
    """User's email ingest settings."""
    endpoint: Optional[EmailIngestEndpoint] = None
    delivery_address: Optional[str] = None
    delivery_mode: Optional[str] = None
    verified_senders: List[VerifiedSenderResponse]
    usage_summary: UsageSummary
    enabled_by_config: bool = True
    provider: str = "resend"
    message: Optional[str] = None


class VerifiedSender(BaseModel):
    """Verified sender information."""
    id: str
    email: str
    status: str  # pending, verified, disabled
    created_at: str
    verified_at: Optional[str] = None


class AddSenderRequest(BaseModel):
    """Request to add a new verified sender."""
    email: EmailStr


class UpdateDefaultAgentRequest(BaseModel):
    """Request to update default agent."""
    agent_id: Optional[str] = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/settings", response_model=EmailIngestSettings)
async def get_settings(current_user = Depends(get_current_user), jwt_token: str = Depends(extract_jwt_token)):
    """
    Get current email ingest settings for the authenticated user.
    
    Returns:
        EmailIngestSettings with endpoint, verified senders, and usage summary
    """
    try:
        if not is_email_ingest_enabled():
            return disabled_email_ingest_settings()

        user_id = current_user.id
        
        # Service now returns the complete structure matching our schema
        settings = email_ingest_service.get_user_settings(jwt_token, user_id)
        
        # The service returns a dict that matches EmailIngestSettings schema exactly
        return with_delivery_config(settings)
        
    except Exception as e:
        user_id = getattr(current_user, "id", "unknown")
        logger.error(f"Failed to get email settings for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve email settings"
        )


@router.post("/enable", response_model=EmailIngestSettings)
async def enable_email_ingest(current_user = Depends(get_current_user), jwt_token: str = Depends(extract_jwt_token)):
    """
    Enable email ingest and generate a unique email alias for the user.
    
    If the user already has an alias, it will be reactivated.
    
    Returns:
        EmailIngestSettings with the generated or reactivated alias
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        # Enable the endpoint
        result = email_ingest_service.enable_email_ingest(jwt_token, user_id)
        
        # Get full settings to return (now in correct format)
        settings = email_ingest_service.get_user_settings(jwt_token, user_id)
        
        return with_delivery_config(settings)
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        user_id = getattr(current_user, "id", "unknown")
        logger.error(f"Failed to enable email ingest for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable email ingest"
        )


@router.post("/disable", response_model=MessageResponse)
async def disable_email_ingest(current_user = Depends(get_current_user), jwt_token: str = Depends(extract_jwt_token)):
    """
    Disable email ingest for the user.
    
    The alias is preserved and can be reactivated later.
    
    Returns:
        Success message
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        success = email_ingest_service.disable_email_ingest(jwt_token, user_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to disable email ingest"
            )
        
        return MessageResponse(
            message="Email ingest disabled successfully",
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable email ingest for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable email ingest"
        )


@router.get("/verified-senders", response_model=List[VerifiedSender])
async def get_verified_senders(current_user = Depends(get_current_user), jwt_token: str = Depends(extract_jwt_token)):
    """
    Get list of verified senders for the authenticated user.
    
    Returns:
        List of verified senders with their status
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        senders = email_ingest_service.get_verified_senders(jwt_token, user_id)
        
        return [
            VerifiedSender(
                id=sender["id"],
                email=sender["email"],
                status=sender["status"],
                created_at=sender["created_at"],
                verified_at=sender.get("verified_at")
            )
            for sender in senders
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        user_id = getattr(current_user, "id", "unknown")
        logger.error(f"Failed to get verified senders for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve verified senders"
        )


@router.post("/verified-senders", response_model=VerifiedSender)
async def add_verified_sender(
    request: AddSenderRequest,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """
    Add a new sender email address and send verification email.
    
    The sender must verify their email address before they can submit
    documents to the user's alias.
    
    Args:
        request: AddSenderRequest with email address
        
    Returns:
        VerifiedSender with pending status
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        result = email_ingest_service.add_verified_sender(
            jwt_token,
            user_id,
            request.email
        )
        
        return VerifiedSender(
            id=result["id"],
            email=result["email"],
            status=result["status"],
            created_at=result["created_at"],
            verified_at=None
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        user_id = getattr(current_user, "id", "unknown")
        logger.error(f"Failed to add verified sender for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add sender"
        )


@router.post("/verified-senders/{sender_id}/resend", response_model=MessageResponse)
async def resend_verification(
    sender_id: str,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """
    Resend verification email to a pending sender.
    
    This creates a new token and sends a new verification email.
    
    Args:
        sender_id: ID of the sender to resend verification to
        
    Returns:
        Success message
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        # Get the sender to verify it belongs to this user and get email
        senders = email_ingest_service.get_verified_senders(jwt_token, user_id)
        sender = next((s for s in senders if s["id"] == sender_id), None)
        
        if not sender:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sender not found"
            )
        
        if sender["status"] == "verified":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sender is already verified"
            )
        
        # Delete existing sender and re-add (creates new token)
        email_ingest_service.remove_verified_sender(jwt_token, user_id, sender_id)
        email_ingest_service.add_verified_sender(jwt_token, user_id, sender["email"])
        
        return MessageResponse(
            message="Verification email sent",
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resend verification for sender {sender_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification"
        )


@router.delete("/verified-senders/{sender_id}", response_model=MessageResponse)
async def remove_verified_sender(
    sender_id: str,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """
    Remove a verified sender.
    
    The sender will no longer be able to submit documents to the user's alias.
    
    Args:
        sender_id: ID of the sender to remove
        
    Returns:
        Success message
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        success = email_ingest_service.remove_verified_sender(jwt_token, user_id, sender_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sender not found or already removed"
            )
        
        return MessageResponse(
            message="Sender removed successfully",
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove sender {sender_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove sender"
        )


@router.put("/default-agent", response_model=MessageResponse)
async def update_default_agent(
    request: UpdateDefaultAgentRequest,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """
    Update the default agent for email-submitted documents.
    
    If no agent_id is provided, the default is cleared and the system
    will use the first available prebuilt agent.
    
    Args:
        request: UpdateDefaultAgentRequest with optional agent_id
        
    Returns:
        Success message
    """
    try:
        require_email_ingest_enabled()
        user_id = current_user.id
        
        success = email_ingest_service.update_default_agent(
            jwt_token,
            user_id,
            request.agent_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update default agent"
            )
        
        return MessageResponse(
            message="Default agent updated successfully",
            success=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update default agent for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update default agent"
        )


@router.get("/verify-sender")
async def verify_sender(token: str = Query(...)):
    """
    Verify sender email address via token from verification email.
    
    This is a PUBLIC endpoint (no JWT required) since users click the link
    from their email before they're logged in.
    
    Args:
        token: Verification token from email link
        
    Returns:
        Redirect to the user-facing Email Ingest settings page
    """
    try:
        if not is_email_ingest_enabled():
            return sender_verification_redirect("disabled")

        success, message = email_ingest_service.verify_sender(token)
        
        if success:
            return sender_verification_redirect("success")

        logger.warning("Sender verification rejected: %s", message)
        return sender_verification_redirect("invalid")
            
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
        return sender_verification_redirect("failed")
