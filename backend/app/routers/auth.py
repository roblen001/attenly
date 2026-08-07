"""Authentication, OIDC browser login, and organization-user administration."""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import config
from app.client import supabase_client
from app.core.deps import get_current_user
from app.db import get_db
from app.limits.slowapi import get_rate_limit, limiter
from app.services.oidc_auth import (
    OIDCAuthenticationError,
    OIDCAuthorizationError,
    OIDCConfigurationError,
    audit_oidc_login_failure,
    begin_oidc_login,
    complete_oidc_login,
    list_organization_users,
    revoke_oidc_session,
    set_organization_user_status,
    validate_browser_origin,
)


logger = logging.getLogger(__name__)

# Keep the existing /auth/api/auth/* contract for token-provider compatibility.
router = APIRouter(prefix="/api/auth", tags=["auth"])
# The reverse proxy exposes /api/auth/oidc/* and strips the first /api segment.
oidc_router = APIRouter(prefix="/auth/oidc", tags=["auth"])


class OrganizationUserStatusUpdate(BaseModel):
    status: Literal["active", "blocked"]
    reason: Optional[str] = Field(default=None, max_length=1000)


def _require_oidc() -> None:
    if config.AUTH_PROVIDER != "oidc":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _oidc_error_redirect(error_code: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?auth_error={error_code}", status_code=303)
    response.delete_cookie(
        key=config.OIDC_LOGIN_COOKIE_NAME,
        path="/",
        secure=config.OIDC_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _as_oidc_principal(current_user):
    if getattr(current_user, "provider", None) != "oidc":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization user administration is available with OIDC authentication",
        )

    # The dependency already verified this database-backed session. Recreate the
    # lightweight service principal without exposing provider token claims.
    from app.services.oidc_auth import OIDCSessionPrincipal

    return OIDCSessionPrincipal(
        resource_owner_id=current_user.id,
        app_user_id=current_user.app_user_id,
        organization_id=current_user.organization_id,
        organization_role=current_user.organization_role,
        membership_status=current_user.organization_status,
        email=current_user.email,
        display_name=current_user.user_metadata.get("display_name") or current_user.email,
        created_at=current_user.created_at,
    )


@router.get("/me")
async def get_current_user_info(current_user=Depends(get_current_user)):
    """Return the authenticated application principal."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "user_metadata": current_user.user_metadata,
        "created_at": current_user.created_at,
        "provider": getattr(current_user, "provider", config.AUTH_PROVIDER),
        "app_user_id": getattr(current_user, "app_user_id", None),
        "organization_id": getattr(current_user, "organization_id", None),
        "organization_role": getattr(current_user, "organization_role", None),
        "organization_status": getattr(current_user, "organization_status", None),
    }


@router.get("/users")
async def get_users(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if config.AUTH_PROVIDER == "oidc":
        try:
            return list_organization_users(db, _as_oidc_principal(current_user))
        except OIDCAuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    # Preserve the old Supabase-backed response only for authenticated callers.
    if config.AUTH_PROVIDER != "supabase" or supabase_client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    response = supabase_client.table("users").select("*").execute()
    return response.data


@router.patch("/users/{user_id}")
async def update_user_status(
    user_id: str,
    update: OrganizationUserStatusUpdate,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_oidc()
    try:
        return set_organization_user_status(
            db,
            _as_oidc_principal(current_user),
            user_id,
            update.status,
            reason=update.reason,
            request=request,
        )
    except OIDCAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@oidc_router.get("/login")
@limiter.limit(get_rate_limit("oidc_login"))
async def oidc_login(
    request: Request,
    return_to: Optional[str] = Query(default="/"),
    db: Session = Depends(get_db),
):
    _require_oidc()
    try:
        started = await begin_oidc_login(db, return_to)
    except OIDCConfigurationError as exc:
        logger.error("OIDC login configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Single sign-on is temporarily unavailable",
        ) from exc
    except OIDCAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    response = RedirectResponse(started.authorization_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=config.OIDC_LOGIN_COOKIE_NAME,
        value=started.browser_binding,
        max_age=config.OIDC_LOGIN_TTL_SECONDS,
        httponly=True,
        secure=config.OIDC_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@oidc_router.get("/callback")
@limiter.limit(get_rate_limit("oidc_callback"))
async def oidc_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state_value: Optional[str] = Query(default=None, alias="state"),
    provider_error: Optional[str] = Query(default=None, alias="error"),
    db: Session = Depends(get_db),
):
    _require_oidc()
    if provider_error or not code or not state_value:
        try:
            audit_oidc_login_failure(
                db,
                state=state_value,
                browser_binding=request.cookies.get(config.OIDC_LOGIN_COOKIE_NAME),
                reason="provider_error" if provider_error else "missing_callback_parameters",
                request=request,
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to persist an OIDC callback failure audit event")
        return _oidc_error_redirect("oidc_login_failed")

    try:
        completed = await complete_oidc_login(
            db,
            state=state_value,
            code=code,
            browser_binding=request.cookies.get(config.OIDC_LOGIN_COOKIE_NAME),
            request=request,
        )
    except OIDCConfigurationError as exc:
        logger.error("OIDC callback configuration error: %s", exc)
        return _oidc_error_redirect("oidc_unavailable")
    except (OIDCAuthenticationError, OIDCAuthorizationError) as exc:
        logger.warning("OIDC login rejected: %s", exc)
        return _oidc_error_redirect("oidc_login_failed")

    response = RedirectResponse(completed.return_to, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=config.OIDC_SESSION_COOKIE_NAME,
        value=completed.session_token,
        max_age=config.OIDC_SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=config.OIDC_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        key=config.OIDC_LOGIN_COOKIE_NAME,
        path="/",
        secure=config.OIDC_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@oidc_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def oidc_logout(
    request: Request,
    db: Session = Depends(get_db),
):
    _require_oidc()
    try:
        validate_browser_origin(request)
        revoke_oidc_session(
            db,
            request.cookies.get(config.OIDC_SESSION_COOKIE_NAME),
            request=request,
        )
    except OIDCAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=config.OIDC_SESSION_COOKIE_NAME,
        path="/",
        secure=config.OIDC_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
