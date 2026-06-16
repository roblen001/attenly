"""External JWT authentication for enterprise deployments.

This provider lets Attenly trust bearer tokens issued by an existing identity
provider, API gateway, or internal SSO proxy. It supports either a shared HMAC
secret for simple gateway deployments or a JWKS URL for asymmetric IdP tokens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

from app import config

logger = logging.getLogger(__name__)


class ExternalJwtAuthError(Exception):
    """Raised when an externally-issued JWT cannot be trusted."""


@dataclass(frozen=True)
class ExternalJwtPrincipal:
    id: str
    email: str
    user_metadata: dict[str, Any]
    created_at: str


_jwks_client: PyJWKClient | None = None


def _audience() -> str | list[str] | None:
    if not config.EXTERNAL_JWT_AUDIENCE:
        return None

    values = [
        value.strip()
        for value in config.EXTERNAL_JWT_AUDIENCE.split(",")
        if value.strip()
    ]
    if not values:
        return None
    return values[0] if len(values) == 1 else values


def _signing_key(token: str) -> Any:
    if config.EXTERNAL_JWT_SECRET:
        return config.EXTERNAL_JWT_SECRET

    if config.EXTERNAL_JWT_JWKS_URL:
        global _jwks_client
        if _jwks_client is None:
            _jwks_client = PyJWKClient(config.EXTERNAL_JWT_JWKS_URL)
        return _jwks_client.get_signing_key_from_jwt(token).key

    raise ExternalJwtAuthError("External JWT authentication is not configured")


def _claim(claims: dict[str, Any], name: str) -> Any:
    value: Any = claims
    for part in name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _created_at(claims: dict[str, Any]) -> str:
    issued_at = claims.get("iat")
    if isinstance(issued_at, (int, float)):
        return datetime.fromtimestamp(issued_at, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def authenticate_external_jwt(token: str) -> ExternalJwtPrincipal:
    """Validate an externally-issued JWT and map configured claims to a user."""

    options = {
        "verify_aud": bool(config.EXTERNAL_JWT_AUDIENCE),
        "require": ["exp"] if config.EXTERNAL_JWT_REQUIRE_EXP else [],
    }

    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=[config.EXTERNAL_JWT_ALGORITHM],
            audience=_audience(),
            issuer=config.EXTERNAL_JWT_ISSUER or None,
            options=options,
        )
    except (InvalidTokenError, PyJWKClientError) as exc:
        logger.warning("External JWT validation failed: %s", exc)
        raise ExternalJwtAuthError("Authentication failed. Please log in again.") from exc

    user_id = _claim(claims, config.EXTERNAL_JWT_USER_ID_CLAIM)
    if not user_id:
        raise ExternalJwtAuthError(
            f"External JWT is missing required user id claim '{config.EXTERNAL_JWT_USER_ID_CLAIM}'"
        )

    email = _claim(claims, config.EXTERNAL_JWT_EMAIL_CLAIM) or f"{user_id}@external.local"
    display_name = _claim(claims, config.EXTERNAL_JWT_NAME_CLAIM) or email

    return ExternalJwtPrincipal(
        id=str(user_id),
        email=str(email),
        user_metadata={
            "provider": "external_jwt",
            "display_name": str(display_name),
            "issuer": claims.get("iss"),
        },
        created_at=_created_at(claims),
    )
