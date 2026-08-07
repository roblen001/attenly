"""Configure an existing self-hosted env file for local OIDC/Entra testing.

The command preserves model, email, and storage settings already present in the
file. It only changes the application/authentication values needed for OIDC.
Run without ``--prepare`` for private interactive prompts and validation.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from pathlib import Path

from check_self_hosted_env import parse_env, validate
from init_self_hosted_env import update_env_lines, write_env


PLACEHOLDER_TENANT = "PASTE_ENTRA_TENANT_ID_HERE"
PLACEHOLDER_CLIENT = "PASTE_ENTRA_CLIENT_ID_HERE"
PLACEHOLDER_SECRET = "PASTE_ENTRA_CLIENT_SECRET_VALUE_HERE"


def usable(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate or "PASTE_" in candidate or "replace-with" in candidate:
        return None
    return candidate


def required_value(label: str, supplied: str | None, current: str | None, *, secret: bool) -> str:
    existing = usable(supplied) or usable(current)
    if existing:
        return existing
    if not sys.stdin.isatty():
        raise SystemExit(f"{label} is required; pass it as a command option.")
    prompt = f"{label}: "
    value = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    if not value:
        raise SystemExit(f"{label} cannot be blank.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", default=".env.docker-test")
    parser.add_argument("--tenant-id", help="Microsoft Entra Directory (tenant) ID.")
    parser.add_argument("--client-id", help="Microsoft Entra Application (client) ID.")
    parser.add_argument("--client-secret", help="Client secret Value (prompted privately if omitted).")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Insert clearly marked placeholders instead of prompting, for manual editing.",
    )
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Create it first with scripts/init_self_hosted_env.py."
        )

    current = parse_env(path)
    if args.prepare:
        tenant_id = usable(current.get("OIDC_TENANT_ID")) or PLACEHOLDER_TENANT
        client_id = usable(current.get("OIDC_CLIENT_ID")) or PLACEHOLDER_CLIENT
        client_secret = usable(current.get("OIDC_CLIENT_SECRET")) or PLACEHOLDER_SECRET
    else:
        tenant_id = required_value(
            "Directory (tenant) ID", args.tenant_id, current.get("OIDC_TENANT_ID"), secret=False
        )
        client_id = required_value(
            "Application (client) ID", args.client_id, current.get("OIDC_CLIENT_ID"), secret=False
        )
        client_secret = required_value(
            "Client secret Value", args.client_secret, current.get("OIDC_CLIENT_SECRET"), secret=True
        )

    origin = "http://localhost:5173"
    updates = {
        "ATTENLY_ENV_FILE": str(path),
        "ENV": "development",
        "APP_PROFILE": "enterprise",
        "APP_URL": origin,
        "PUBLIC_API_URL": f"{origin}/api",
        "CORS_ORIGINS": origin,
        "APP_SECRET_KEY": usable(current.get("APP_SECRET_KEY")) or secrets.token_urlsafe(48),
        "AUTH_PROVIDER": "oidc",
        "OIDC_TENANT_ID": tenant_id,
        "OIDC_DISCOVERY_URL": (
            f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
        ),
        "OIDC_EXPECTED_ISSUER": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "OIDC_CLIENT_ID": client_id,
        "OIDC_CLIENT_SECRET": client_secret,
        "OIDC_CLIENT_AUTH_METHOD": "client_secret_post",
        "OIDC_CALLBACK_URL": f"{origin}/api/auth/oidc/callback",
        "OIDC_ALLOWED_ORIGINS": origin,
        "OIDC_SCOPES": "openid profile email",
        "OIDC_ALLOWED_ID_TOKEN_ALGORITHMS": "RS256",
        "OIDC_ROLES_CLAIM": "roles",
        "OIDC_USER_ROLE": "Attenly.User",
        "OIDC_ADMIN_ROLE": "Attenly.Admin",
        "OIDC_ORGANIZATION_SLUG": "attenly-local-test",
        "OIDC_ORGANIZATION_NAME": "Attenly Local Test",
        "OIDC_SESSION_TTL_HOURS": "12",
        "OIDC_LOGIN_TTL_SECONDS": "600",
        "OIDC_CLOCK_SKEW_SECONDS": "60",
        "OIDC_ALLOW_INSECURE_HTTP": "true",
        "OIDC_COOKIE_SECURE": "false",
        "OIDC_SESSION_COOKIE_NAME": "attenly_session",
        "OIDC_LOGIN_COOKIE_NAME": "attenly_oidc_flow",
    }

    lines = path.read_text(encoding="utf-8").splitlines()
    write_env(path, update_env_lines(lines, updates), force=True)

    if args.prepare:
        print(f"Prepared {path} for local Entra testing.")
        print("Replace the three PASTE_ENTRA_* values, then run:")
        print(f"python scripts/check_self_hosted_env.py {path}")
        return 0

    errors, warnings = validate(parse_env(path))
    if errors:
        print(f"Updated {path}, but preflight found errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(f"Configured and validated {path} for local Entra OIDC login.")
    print(f"Run: docker compose --env-file {path} -f compose.yml -f compose.build.yml up -d --build --wait")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
