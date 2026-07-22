"""Smoke test external JWT auth without FastAPI or network calls."""

from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path

import jwt


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
SMOKE_JWT_SECRET = "external-jwt-smoke-secret-at-least-32-bytes"


def configure_env() -> None:
    os.environ.update(
        {
            "APP_PROFILE": "enterprise",
            "AUTH_PROVIDER": "external_jwt",
            "EXTERNAL_JWT_SECRET": SMOKE_JWT_SECRET,
            "EXTERNAL_JWT_ALGORITHM": "HS256",
            "EXTERNAL_JWT_ISSUER": "https://idp.example.test",
            "EXTERNAL_JWT_AUDIENCE": "attenly",
            "EXTERNAL_JWT_USER_ID_CLAIM": "sub",
            "EXTERNAL_JWT_EMAIL_CLAIM": "email",
            "EXTERNAL_JWT_NAME_CLAIM": "name",
            "DATABASE_PROVIDER": "sqlalchemy",
            "DATABASE_URL": "sqlite:///:memory:",
            "STORAGE_PROVIDER": "filesystem",
            "STORAGE_PATH": "/tmp/attenly-external-jwt-smoke",
            "LLM_PROVIDER": "openai_compatible",
            "EMBEDDING_PROVIDER": "openai_compatible",
            "OPENAI_COMPATIBLE_BASE_URL": "https://models.example.test/v1",
            "TEMPLATE_INGEST_PROVIDER": "disabled",
            "OUTBOUND_EMAIL_PROVIDER": "none",
            "INBOUND_EMAIL_PROVIDER": "none",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )


def assert_equal(label: str, value, expected) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


def make_token(**overrides) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://idp.example.test",
        "aud": "attenly",
        "sub": "user-123",
        "email": "user@example.test",
        "name": "Example User",
        "iat": now,
        "exp": now + 300,
    }
    payload.update(overrides)
    return jwt.encode(payload, SMOKE_JWT_SECRET, algorithm="HS256")


def main() -> int:
    configure_env()
    sys.path.insert(0, str(BACKEND_ROOT))

    from app.config import get_config_summary, validate_config
    from app.services.external_jwt_auth import ExternalJwtAuthError, authenticate_external_jwt

    logging.getLogger("app.services.external_jwt_auth").setLevel(logging.ERROR)

    validate_config()
    summary = get_config_summary()
    assert_equal("auth provider", summary["auth"]["provider"], "external_jwt")
    assert_equal("secret configured", summary["auth"]["external_jwt_secret_configured"], True)

    principal = authenticate_external_jwt(make_token())
    assert_equal("principal id", principal.id, "user-123")
    assert_equal("principal email", principal.email, "user@example.test")
    assert_equal("principal provider", principal.user_metadata["provider"], "external_jwt")

    try:
        authenticate_external_jwt(make_token(aud="other-app"))
    except ExternalJwtAuthError:
        pass
    else:
        raise AssertionError("wrong audience token should be rejected")

    try:
        authenticate_external_jwt(make_token(exp=int(time.time()) - 1))
    except ExternalJwtAuthError:
        pass
    else:
        raise AssertionError("expired token should be rejected")

    print("External JWT auth smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
