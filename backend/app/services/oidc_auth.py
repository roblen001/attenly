"""Generic OpenID Connect login and opaque application-session support.

The browser receives only an Attenly session cookie. Provider access and ID
tokens are exchanged and verified by the backend and are never persisted.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx
import jwt
from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.models import (
    AppSession,
    AppUser,
    OIDCLoginTransaction,
    Organization,
    OrganizationMembership,
    SecurityAuditEvent,
)
from app.services.identity_service import (
    IdentityConflictError,
    IdentityService,
    OrganizationRole,
    VerifiedIdentity,
)


class OIDCError(Exception):
    """Base class for errors safe for the router to translate."""


class OIDCConfigurationError(OIDCError):
    """The configured provider cannot be used safely."""


class OIDCAuthenticationError(OIDCError):
    """The provider response or local session is not authenticated."""


class OIDCAuthorizationError(OIDCError):
    """The identity is valid but is not allowed to use this deployment."""


@dataclass(frozen=True)
class OIDCSessionPrincipal:
    resource_owner_id: str
    app_user_id: str
    organization_id: str
    organization_role: str
    membership_status: str
    email: str
    display_name: str
    created_at: str


@dataclass(frozen=True)
class CompletedOIDCLogin:
    session_token: str
    return_to: str
    principal: OIDCSessionPrincipal


@dataclass(frozen=True)
class StartedOIDCLogin:
    authorization_url: str
    browser_binding: str


_DISCOVERY_CACHE: tuple[float, dict[str, Any]] | None = None
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_METADATA_CACHE_SECONDS = 300
_HTTP_TIMEOUT_SECONDS = 15.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def sanitize_return_to(value: Optional[str]) -> str:
    """Allow only same-origin absolute paths in post-login redirects."""
    candidate = (value or "/").strip()
    if (
        len(candidate) > 2048
        or not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
    ):
        return "/"
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return "/"
    return urlunsplit(("", "", parsed.path or "/", parsed.query, parsed.fragment))


def _validate_provider_url(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise OIDCConfigurationError(f"OIDC metadata is missing {field_name}")
    parsed = urlsplit(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if config.OIDC_ALLOW_INSECURE_HTTP and parsed.scheme == "http" and parsed.netloc:
        return value
    raise OIDCConfigurationError(f"OIDC {field_name} must use HTTPS")


async def get_provider_metadata(*, force_refresh: bool = False) -> dict[str, Any]:
    global _DISCOVERY_CACHE
    now = time.monotonic()
    if not force_refresh and _DISCOVERY_CACHE and _DISCOVERY_CACHE[0] > now:
        return _DISCOVERY_CACHE[1]

    discovery_url = _validate_provider_url(config.OIDC_DISCOVERY_URL, "discovery URL")
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                discovery_url,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            metadata = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OIDCConfigurationError("Unable to load OIDC provider metadata") from exc

    if not isinstance(metadata, dict):
        raise OIDCConfigurationError("OIDC provider metadata is invalid")

    for field in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        _validate_provider_url(metadata.get(field), field)

    expected_issuer = config.OIDC_EXPECTED_ISSUER
    if expected_issuer and not secrets.compare_digest(metadata["issuer"], expected_issuer):
        raise OIDCConfigurationError("OIDC metadata issuer does not match OIDC_EXPECTED_ISSUER")

    supported_response_types = metadata.get("response_types_supported")
    if isinstance(supported_response_types, list) and "code" not in supported_response_types:
        raise OIDCConfigurationError("OIDC provider does not advertise authorization code support")
    challenge_methods = metadata.get("code_challenge_methods_supported")
    if isinstance(challenge_methods, list) and "S256" not in challenge_methods:
        raise OIDCConfigurationError("OIDC provider does not advertise PKCE S256 support")
    client_auth_methods = metadata.get("token_endpoint_auth_methods_supported")
    if (
        isinstance(client_auth_methods, list)
        and config.OIDC_CLIENT_AUTH_METHOD not in client_auth_methods
    ):
        raise OIDCConfigurationError(
            "OIDC provider does not support the configured token endpoint client auth method"
        )

    _DISCOVERY_CACHE = (now + _METADATA_CACHE_SECONDS, metadata)
    return metadata


def _get_or_create_organization(db: Session) -> Organization:
    organization = (
        db.query(Organization)
        .filter(Organization.slug == config.OIDC_ORGANIZATION_SLUG)
        .one_or_none()
    )
    if organization:
        if organization.status != "active":
            raise OIDCAuthorizationError("This organization is blocked")
        return organization

    organization = Organization(
        slug=config.OIDC_ORGANIZATION_SLUG,
        name=config.OIDC_ORGANIZATION_NAME,
        status="active",
    )
    db.add(organization)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        organization = (
            db.query(Organization)
            .filter(Organization.slug == config.OIDC_ORGANIZATION_SLUG)
            .one()
        )
    return organization


async def begin_oidc_login(db: Session, return_to: Optional[str]) -> StartedOIDCLogin:
    metadata = await get_provider_metadata()
    db.query(OIDCLoginTransaction).filter(
        OIDCLoginTransaction.expires_at < _utcnow()
    ).delete(synchronize_session=False)
    state = secrets.token_urlsafe(32)
    browser_binding = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _base64url(hashlib.sha256(code_verifier.encode("ascii")).digest())
    organization = _get_or_create_organization(db)
    transaction = OIDCLoginTransaction(
        organization_id=organization.id,
        provider="oidc",
        state_hash=_hash_secret(state),
        browser_binding_hash=_hash_secret(browser_binding),
        nonce=nonce,
        code_verifier=code_verifier,
        redirect_uri=config.OIDC_CALLBACK_URL,
        return_to=sanitize_return_to(return_to),
        expires_at=_utcnow() + timedelta(seconds=config.OIDC_LOGIN_TTL_SECONDS),
    )
    db.add(transaction)
    db.commit()

    endpoint = urlsplit(metadata["authorization_endpoint"])
    query = dict(parse_qsl(endpoint.query, keep_blank_values=True))
    query.update(
        {
            "client_id": config.OIDC_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": config.OIDC_CALLBACK_URL,
            "scope": config.OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
    )
    return StartedOIDCLogin(
        authorization_url=urlunsplit(
            (endpoint.scheme, endpoint.netloc, endpoint.path, urlencode(query), endpoint.fragment)
        ),
        browser_binding=browser_binding,
    )


def _consume_login_transaction(
    db: Session,
    state: str,
    browser_binding: Optional[str],
) -> OIDCLoginTransaction:
    if (
        not state
        or len(state) > 512
        or not browser_binding
        or len(browser_binding) > 512
    ):
        raise OIDCAuthenticationError("The login request is invalid or expired")
    state_hash = _hash_secret(state)
    transaction = (
        db.query(OIDCLoginTransaction)
        .filter(OIDCLoginTransaction.state_hash == state_hash)
        .one_or_none()
    )
    if not transaction:
        raise OIDCAuthenticationError("The login request is invalid or expired")
    if not transaction.browser_binding_hash or not secrets.compare_digest(
        transaction.browser_binding_hash,
        _hash_secret(browser_binding),
    ):
        raise OIDCAuthenticationError("The login request is invalid or expired")
    now = _utcnow()
    if transaction.consumed_at or _ensure_aware(transaction.expires_at) <= now:
        raise OIDCAuthenticationError("The login request is invalid or expired")

    updated = (
        db.query(OIDCLoginTransaction)
        .filter(
            OIDCLoginTransaction.id == transaction.id,
            OIDCLoginTransaction.consumed_at.is_(None),
        )
        .update({OIDCLoginTransaction.consumed_at: now}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        raise OIDCAuthenticationError("The login request is invalid or expired")
    db.commit()
    return transaction


async def _exchange_code(
    metadata: Mapping[str, Any],
    transaction: OIDCLoginTransaction,
    code: str,
) -> Mapping[str, Any]:
    if not code or len(code) > 8192:
        raise OIDCAuthenticationError("The identity provider did not return a valid code")
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": config.OIDC_CLIENT_ID,
        "code": code,
        "redirect_uri": transaction.redirect_uri,
        "code_verifier": transaction.code_verifier,
    }
    auth: httpx.BasicAuth | None = None
    if config.OIDC_CLIENT_AUTH_METHOD == "client_secret_post":
        data["client_secret"] = config.OIDC_CLIENT_SECRET
    elif config.OIDC_CLIENT_AUTH_METHOD == "client_secret_basic":
        auth = httpx.BasicAuth(config.OIDC_CLIENT_ID, config.OIDC_CLIENT_SECRET)

    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                metadata["token_endpoint"],
                data=data,
                auth=auth,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_response = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OIDCAuthenticationError("The identity provider rejected the login") from exc
    if not isinstance(token_response, dict) or not isinstance(token_response.get("id_token"), str):
        raise OIDCAuthenticationError("The identity provider did not return an ID token")
    return token_response


async def _get_jwks(jwks_uri: str, *, force_refresh: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    cached = _JWKS_CACHE.get(jwks_uri)
    if not force_refresh and cached and cached[0] > now:
        return cached[1]
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.get(jwks_uri, headers={"Accept": "application/json"})
            response.raise_for_status()
            jwks = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OIDCAuthenticationError("Unable to verify the provider ID token") from exc
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise OIDCAuthenticationError("The provider signing-key response is invalid")
    _JWKS_CACHE[jwks_uri] = (now + _METADATA_CACHE_SECONDS, jwks)
    return jwks


def _select_jwk(
    jwks: Mapping[str, Any],
    kid: Optional[str],
    algorithm: str,
) -> Mapping[str, Any] | None:
    keys = [
        key
        for key in jwks.get("keys", [])
        if isinstance(key, dict)
        and key.get("use") in (None, "sig")
        and key.get("alg") in (None, algorithm)
        and (not isinstance(key.get("key_ops"), list) or "verify" in key["key_ops"])
    ]
    if kid:
        return next((key for key in keys if key.get("kid") == kid), None)
    return keys[0] if len(keys) == 1 else None


async def _validate_id_token(
    metadata: Mapping[str, Any],
    raw_id_token: str,
    expected_nonce: str,
) -> Mapping[str, Any]:
    if not isinstance(raw_id_token, str) or len(raw_id_token) > 65536:
        raise OIDCAuthenticationError("The provider ID token is malformed")
    try:
        header = jwt.get_unverified_header(raw_id_token)
    except jwt.PyJWTError as exc:
        raise OIDCAuthenticationError("The provider ID token is malformed") from exc
    algorithm = header.get("alg")
    if algorithm not in config.OIDC_ALLOWED_ID_TOKEN_ALGORITHMS:
        raise OIDCAuthenticationError("The provider used an unapproved ID-token algorithm")
    provider_algorithms = metadata.get("id_token_signing_alg_values_supported")
    if isinstance(provider_algorithms, list) and algorithm not in provider_algorithms:
        raise OIDCAuthenticationError("The ID-token algorithm is not advertised by the provider")

    jwks_uri = _validate_provider_url(metadata["jwks_uri"], "jwks_uri")
    jwks = await _get_jwks(jwks_uri)
    jwk_data = _select_jwk(jwks, header.get("kid"), algorithm)
    if jwk_data is None:
        jwks = await _get_jwks(jwks_uri, force_refresh=True)
        jwk_data = _select_jwk(jwks, header.get("kid"), algorithm)
    if jwk_data is None:
        raise OIDCAuthenticationError("The provider ID-token signing key was not found")

    try:
        signing_key = jwt.PyJWK.from_dict(dict(jwk_data), algorithm=algorithm).key
        claims = jwt.decode(
            raw_id_token,
            signing_key,
            algorithms=list(config.OIDC_ALLOWED_ID_TOKEN_ALGORITHMS),
            audience=config.OIDC_CLIENT_ID,
            issuer=metadata["issuer"],
            leeway=config.OIDC_CLOCK_SKEW_SECONDS,
            options={"require": ["iss", "sub", "aud", "exp", "iat"]},
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise OIDCAuthenticationError("The provider ID token could not be verified") from exc

    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not secrets.compare_digest(nonce, expected_nonce):
        raise OIDCAuthenticationError("The provider ID token nonce is invalid")
    audience = claims.get("aud")
    authorized_party = claims.get("azp")
    if authorized_party is not None and (
        not isinstance(authorized_party, str)
        or not secrets.compare_digest(authorized_party, config.OIDC_CLIENT_ID)
    ):
        raise OIDCAuthenticationError("The provider ID token authorized party is invalid")
    if isinstance(audience, list) and len(audience) > 1 and authorized_party is None:
        raise OIDCAuthenticationError("The provider ID token authorized party is invalid")
    return claims


def _claim_roles(claims: Mapping[str, Any]) -> set[str]:
    raw_roles = claims.get(config.OIDC_ROLES_CLAIM, [])
    if isinstance(raw_roles, str):
        return {raw_roles}
    if isinstance(raw_roles, list):
        return {role for role in raw_roles if isinstance(role, str)}
    return set()


def _application_role(claims: Mapping[str, Any]) -> str:
    roles = _claim_roles(claims)
    if config.OIDC_ADMIN_ROLE in roles:
        return "admin"
    if config.OIDC_USER_ROLE in roles:
        return "user"
    raise OIDCAuthorizationError("Your account is not assigned an Attenly application role")


def _optional_claim(claims: Mapping[str, Any], *names: str) -> Optional[str]:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _provision_identity(
    db: Session,
    claims: Mapping[str, Any],
    organization: Organization,
) -> tuple[AppUser, OrganizationMembership]:
    issuer = claims.get("iss")
    subject = claims.get("sub")
    if (
        not isinstance(issuer, str)
        or not isinstance(subject, str)
        or not issuer
        or not subject
        or len(issuer) > 2048
        or len(subject) > 512
    ):
        raise OIDCAuthenticationError("The provider identity is incomplete")

    tenant_id = _optional_claim(claims, "tid")
    object_id = _optional_claim(claims, "oid")
    if (tenant_id and len(tenant_id) > 255) or (object_id and len(object_id) > 255):
        raise OIDCAuthenticationError("The provider tenant identity is invalid")
    if config.OIDC_TENANT_ID:
        if not tenant_id or not secrets.compare_digest(
            tenant_id.casefold(), config.OIDC_TENANT_ID.casefold()
        ):
            raise OIDCAuthorizationError("This account belongs to a different tenant")
        if not object_id:
            raise OIDCAuthenticationError("The Microsoft Entra object ID is missing")
    else:
        # ``tid``/``oid`` are an Entra-specific canonical pair. Generic OIDC
        # providers may coincidentally use those claim names; unless the
        # deployment explicitly pins an Entra tenant, issuer+subject alone is
        # the durable identity key and cannot inherit another issuer's data.
        tenant_id = None
        object_id = None

    role = _application_role(claims)
    email = _optional_claim(claims, "email", "preferred_username", "upn")
    display_name = _optional_claim(claims, "name") or email or "Attenly User"
    if email and len(email) > 320:
        email = None
    display_name = display_name[:255]
    owner_digest = hashlib.sha256(f"{issuer}\0{subject}".encode("utf-8")).hexdigest()
    def provision():
        return IdentityService(db).provision_verified_identity(
            organization_slug=organization.slug,
            organization_name=organization.name,
            verified_identity=VerifiedIdentity(
                provider="oidc",
                issuer=issuer,
                subject=subject,
                email=email,
                display_name=display_name,
                tenant_id=tenant_id,
                object_id=object_id,
            ),
            role=OrganizationRole.ADMIN if role == "admin" else OrganizationRole.USER,
            # Keep the stable private owner key safe as a filesystem path
            # component on Windows as well as Linux.
            resource_owner_id=f"oidc-{owner_digest}",
            now=_utcnow(),
        )

    try:
        provisioned = provision()
    except IntegrityError:
        # Two first-time callbacks for the same person can race on the durable
        # identity keys. Once the winner commits, retry as the existing user.
        db.rollback()
        try:
            provisioned = provision()
        except (IdentityConflictError, IntegrityError, ValueError) as exc:
            raise OIDCAuthenticationError(
                "The provider identity conflicts with an existing user"
            ) from exc
    except (IdentityConflictError, ValueError) as exc:
        raise OIDCAuthenticationError("The provider identity conflicts with an existing user") from exc
    if not provisioned.can_sign_in:
        raise OIDCAuthorizationError("This Attenly account or membership is blocked")
    return provisioned.app_user, provisioned.membership


def _principal(user: AppUser, membership: OrganizationMembership) -> OIDCSessionPrincipal:
    return OIDCSessionPrincipal(
        resource_owner_id=user.resource_owner_id,
        app_user_id=str(user.id),
        organization_id=str(membership.organization_id),
        organization_role=membership.role,
        membership_status=membership.status,
        email=user.email or "",
        display_name=user.display_name or user.email or "Attenly User",
        created_at=_ensure_aware(user.created_at).isoformat(),
    )


def _audit(
    db: Session,
    *,
    event_type: str,
    outcome: str = "success",
    organization_id: Any = None,
    actor_user_id: Any = None,
    target_user_id: Any = None,
    metadata: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    db.add(
        SecurityAuditEvent(
            event_type=event_type,
            outcome=outcome,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            event_metadata=metadata or {},
            ip_address=(request.client.host[:64] if request and request.client else None),
            user_agent=(request.headers.get("user-agent", "")[:1000] if request else None),
        )
    )


def audit_oidc_login_failure(
    db: Session,
    *,
    state: Optional[str],
    browser_binding: Optional[str],
    reason: str,
    request: Optional[Request] = None,
) -> bool:
    """Audit one browser-bound provider failure without amplifying junk traffic."""

    if (
        not state
        or len(state) > 512
        or not browser_binding
        or len(browser_binding) > 512
    ):
        return False

    transaction = (
        db.query(OIDCLoginTransaction)
        .filter(OIDCLoginTransaction.state_hash == _hash_secret(state))
        .one_or_none()
    )
    now = _utcnow()
    if (
        transaction is None
        or transaction.consumed_at is not None
        or _ensure_aware(transaction.expires_at) <= now
        or not transaction.browser_binding_hash
        or not secrets.compare_digest(
            transaction.browser_binding_hash,
            _hash_secret(browser_binding),
        )
    ):
        return False

    consumed = (
        db.query(OIDCLoginTransaction)
        .filter(
            OIDCLoginTransaction.id == transaction.id,
            OIDCLoginTransaction.consumed_at.is_(None),
        )
        .update({OIDCLoginTransaction.consumed_at: now}, synchronize_session=False)
    )
    if consumed != 1:
        db.rollback()
        return False

    _audit(
        db,
        event_type="oidc.login",
        outcome="failure",
        organization_id=transaction.organization_id,
        metadata={"provider": "oidc", "reason": reason[:120]},
        request=request,
    )
    db.commit()
    return True


async def complete_oidc_login(
    db: Session,
    *,
    state: str,
    code: str,
    browser_binding: Optional[str],
    request: Optional[Request] = None,
) -> CompletedOIDCLogin:
    organization_id = None
    try:
        transaction = _consume_login_transaction(db, state, browser_binding)
        organization_id = transaction.organization_id
        return_to = transaction.return_to
        metadata = await get_provider_metadata()
        token_response = await _exchange_code(metadata, transaction, code)
        claims = await _validate_id_token(metadata, token_response["id_token"], transaction.nonce)
        organization = db.query(Organization).filter(Organization.id == organization_id).one()
        if organization.status != "active":
            raise OIDCAuthorizationError("This organization is blocked")

        user, membership = _provision_identity(db, claims, organization)
        raw_session_token = secrets.token_urlsafe(48)
        session = AppSession(
            app_user_id=user.id,
            organization_id=organization.id,
            token_hash=_hash_secret(raw_session_token),
            expires_at=_utcnow() + timedelta(hours=config.OIDC_SESSION_TTL_HOURS),
            ip_address=(request.client.host[:64] if request and request.client else None),
            user_agent=(request.headers.get("user-agent", "")[:1000] if request else None),
        )
        db.add(session)
        _audit(
            db,
            event_type="oidc.login",
            organization_id=organization.id,
            actor_user_id=user.id,
            target_user_id=user.id,
            metadata={"provider": "oidc", "role": membership.role},
            request=request,
        )
        db.commit()
        return CompletedOIDCLogin(
            session_token=raw_session_token,
            return_to=sanitize_return_to(return_to),
            principal=_principal(user, membership),
        )
    except OIDCError as exc:
        db.rollback()
        if organization_id is not None:
            try:
                _audit(
                    db,
                    event_type="oidc.login",
                    outcome="failure",
                    organization_id=organization_id,
                    metadata={
                        "provider": "oidc",
                        "reason": type(exc).__name__[:120],
                    },
                    request=request,
                )
                db.commit()
            except Exception:
                db.rollback()
        raise


def authenticate_oidc_session(db: Session, raw_session_token: Optional[str]) -> OIDCSessionPrincipal:
    if not raw_session_token or len(raw_session_token) > 1024:
        raise OIDCAuthenticationError("Authentication required")
    session = (
        db.query(AppSession)
        .filter(AppSession.token_hash == _hash_secret(raw_session_token))
        .one_or_none()
    )
    now = _utcnow()
    if not session or session.revoked_at or _ensure_aware(session.expires_at) <= now:
        raise OIDCAuthenticationError("Session expired. Please log in again")

    user = session.app_user
    organization = session.organization
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == session.organization_id,
            OrganizationMembership.app_user_id == session.app_user_id,
        )
        .one_or_none()
    )
    if (
        user.status != "active"
        or organization.status != "active"
        or not membership
        or membership.status != "active"
    ):
        session.revoked_at = now
        session.revoked_reason = "account_or_membership_blocked"
        db.commit()
        raise OIDCAuthorizationError("This Attenly account is blocked")

    if _ensure_aware(session.last_seen_at) <= now - timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return _principal(user, membership)


def revoke_oidc_session(
    db: Session,
    raw_session_token: Optional[str],
    *,
    request: Optional[Request] = None,
) -> None:
    if not raw_session_token:
        return
    session = (
        db.query(AppSession)
        .filter(AppSession.token_hash == _hash_secret(raw_session_token))
        .one_or_none()
    )
    if not session or session.revoked_at:
        return
    session.revoked_at = _utcnow()
    session.revoked_reason = "logout"
    _audit(
        db,
        event_type="oidc.logout",
        organization_id=session.organization_id,
        actor_user_id=session.app_user_id,
        target_user_id=session.app_user_id,
        request=request,
    )
    db.commit()


def _require_active_admin(
    db: Session,
    principal: OIDCSessionPrincipal,
) -> tuple[UUID, UUID]:
    if principal.organization_role != "admin":
        raise OIDCAuthorizationError("Organization administrator access is required")
    try:
        organization_id = UUID(principal.organization_id)
        actor_user_id = UUID(principal.app_user_id)
    except (TypeError, ValueError) as exc:
        raise OIDCAuthorizationError("Organization administrator access is required") from exc
    actor_membership = (
        db.query(OrganizationMembership)
        .join(AppUser, AppUser.id == OrganizationMembership.app_user_id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.app_user_id == actor_user_id,
            OrganizationMembership.role == "admin",
            OrganizationMembership.status == "active",
            AppUser.status == "active",
            Organization.status == "active",
        )
        .one_or_none()
    )
    if not actor_membership:
        raise OIDCAuthorizationError("Organization administrator access is required")
    return organization_id, actor_user_id


def list_organization_users(db: Session, principal: OIDCSessionPrincipal) -> list[dict[str, Any]]:
    organization_id, _ = _require_active_admin(db, principal)
    rows = (
        db.query(OrganizationMembership, AppUser)
        .join(AppUser, AppUser.id == OrganizationMembership.app_user_id)
        .filter(OrganizationMembership.organization_id == organization_id)
        .order_by(AppUser.display_name.asc(), AppUser.email.asc())
        .all()
    )
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": membership.role,
            "status": membership.status,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
        }
        for membership, user in rows
    ]


def set_organization_user_status(
    db: Session,
    principal: OIDCSessionPrincipal,
    target_user_id: str,
    new_status: str,
    *,
    reason: Optional[str] = None,
    request: Optional[Request] = None,
) -> dict[str, Any]:
    organization_id, actor_user_id = _require_active_admin(db, principal)
    if new_status not in {"active", "blocked"}:
        raise ValueError("Status must be active or blocked")
    try:
        target_id = UUID(target_user_id)
    except (TypeError, ValueError) as exc:
        raise LookupError("User not found") from exc
    if target_id == actor_user_id and new_status == "blocked":
        raise OIDCAuthorizationError("Administrators cannot block their own current account")

    row = (
        db.query(OrganizationMembership, AppUser)
        .join(AppUser, AppUser.id == OrganizationMembership.app_user_id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.app_user_id == target_id,
        )
        .one_or_none()
    )
    if not row:
        raise LookupError("User not found")
    membership, user = row
    now = _utcnow()
    membership.status = new_status
    user.status = new_status
    if new_status == "blocked":
        membership.blocked_at = now
        membership.blocked_by_user_id = actor_user_id
        membership.block_reason = (reason or "")[:1000] or None
        (
            db.query(AppSession)
            .filter(
                AppSession.organization_id == membership.organization_id,
                AppSession.app_user_id == membership.app_user_id,
                AppSession.revoked_at.is_(None),
            )
            .update(
                {
                    AppSession.revoked_at: now,
                    AppSession.revoked_reason: "administrator_blocked_user",
                },
                synchronize_session=False,
            )
        )
    else:
        membership.blocked_at = None
        membership.blocked_by_user_id = None
        membership.block_reason = None

    _audit(
        db,
        event_type=f"organization.user_{new_status}",
        organization_id=membership.organization_id,
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        metadata={"reason": (reason or "")[:1000]},
        request=request,
    )
    db.commit()
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": membership.role,
        "status": membership.status,
    }


def validate_browser_origin(request: Request) -> None:
    """Reject cross-site cookie-authenticated state changes."""
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise OIDCAuthorizationError("Cross-site requests are not allowed")
    origin = request.headers.get("origin")
    if not origin:
        raise OIDCAuthorizationError("The request origin is required")

    allowed = set(config.OIDC_ALLOWED_ORIGINS)
    for configured_url in (config.APP_URL, config.OIDC_CALLBACK_URL):
        if configured_url:
            parsed = urlsplit(configured_url)
            if parsed.scheme and parsed.netloc:
                allowed.add(f"{parsed.scheme}://{parsed.netloc}")
    if origin.rstrip("/") not in allowed:
        raise OIDCAuthorizationError("The request origin is not allowed")
