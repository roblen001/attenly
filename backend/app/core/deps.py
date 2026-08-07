"""Authentication dependencies for configured auth providers."""
from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import HTTPException, Request, status, Header
from typing import Optional
from app.client import supabase_client
from app import config
import logging
import secrets

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str
    user_metadata: dict
    created_at: str
    provider: str = ""
    app_user_id: Optional[str] = None
    organization_id: Optional[str] = None
    organization_role: Optional[str] = None
    organization_status: Optional[str] = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        logger.warning("Authentication attempt without authorization header")
        raise _unauthorized("Authentication required. Please log in.")

    if not authorization.startswith("Bearer "):
        logger.warning("Invalid authorization header format")
        raise _unauthorized("Invalid authentication format. Please log in again.")

    return authorization.split(" ", 1)[1]


def _get_local_user(token: str) -> AuthenticatedUser:
    if not config.LOCAL_AUTH_TOKEN:
        logger.error("LOCAL_AUTH_TOKEN is not configured")
        raise _unauthorized("Local authentication is not configured.")

    if not secrets.compare_digest(token, config.LOCAL_AUTH_TOKEN):
        logger.warning("Invalid local authentication token")
        raise _unauthorized("Authentication failed. Please log in again.")

    return AuthenticatedUser(
        id=config.LOCAL_AUTH_USER_ID,
        email=config.LOCAL_AUTH_EMAIL,
        user_metadata={
            "provider": "local",
            "display_name": config.LOCAL_AUTH_DISPLAY_NAME,
        },
        created_at=datetime.now(timezone.utc).isoformat(),
        provider="local",
    )


def _get_external_jwt_user(token: str) -> AuthenticatedUser:
    from app.services.external_jwt_auth import ExternalJwtAuthError, authenticate_external_jwt

    try:
        principal = authenticate_external_jwt(token)
    except ExternalJwtAuthError as exc:
        raise _unauthorized(str(exc)) from exc

    return AuthenticatedUser(
        id=principal.id,
        email=principal.email,
        user_metadata=principal.user_metadata,
        created_at=principal.created_at,
        provider="external_jwt",
    )


def _get_oidc_user(request: Request) -> AuthenticatedUser:
    from app.db import SessionLocal
    from app.services.oidc_auth import (
        OIDCAuthenticationError,
        OIDCAuthorizationError,
        authenticate_oidc_session,
        validate_browser_origin,
    )

    try:
        validate_browser_origin(request)
    except OIDCAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        with SessionLocal() as db:
            principal = authenticate_oidc_session(
                db,
                request.cookies.get(config.OIDC_SESSION_COOKIE_NAME),
            )
    except (OIDCAuthenticationError, OIDCAuthorizationError) as exc:
        raise _unauthorized(str(exc)) from exc

    return AuthenticatedUser(
        id=principal.resource_owner_id,
        email=principal.email,
        user_metadata={
            "provider": "oidc",
            "display_name": principal.display_name,
            "organization_id": principal.organization_id,
            "organization_role": principal.organization_role,
        },
        created_at=principal.created_at,
        provider="oidc",
        app_user_id=principal.app_user_id,
        organization_id=principal.organization_id,
        organization_role=principal.organization_role,
        organization_status=principal.membership_status,
    )


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Dependency to get the current authenticated user from the configured auth provider.
    
    Args:
        authorization: Authorization header containing Bearer token
        
    Returns:
        Provider user object with id, email, user_metadata, and created_at
        
    Raises:
        HTTPException: If token is missing, invalid, or user not found
    """
    if config.AUTH_PROVIDER == "oidc":
        return _get_oidc_user(request)

    token = _extract_bearer_token(authorization)

    if config.AUTH_PROVIDER == "local":
        return _get_local_user(token)

    if config.AUTH_PROVIDER == "external_jwt":
        return _get_external_jwt_user(token)

    if config.AUTH_PROVIDER != "supabase":
        logger.error("Unsupported auth provider reached runtime: %s", config.AUTH_PROVIDER)
        raise _unauthorized("Authentication provider is not available.")

    if supabase_client is None:
        logger.error("Supabase auth selected but client is not configured")
        raise _unauthorized("Authentication provider is not configured.")

    try:
        # Validate token with Supabase
        user_response = supabase_client.auth.get_user(token)
        
        if not user_response.user:
            logger.warning("Token validation failed - no user returned")
            raise _unauthorized("Session expired. Please log in again.")
        
        logger.info(f"User authenticated successfully: {user_response.user.id}")
        return user_response.user
        
    except HTTPException:
        # Re-raise HTTP exceptions (already logged above)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise _unauthorized("Authentication failed. Please log in again.")
