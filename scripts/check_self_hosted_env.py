"""Preflight checks for the self-hosted Docker environment file.

This script intentionally uses only the Python standard library so users can run
it before installing backend dependencies.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List


PLACEHOLDER_MARKERS = (
    "replace-with",
    "your_",
    "your-",
    "your ",
    "<tenant-id>",
    "<internal_cron_secret>",
)


def parse_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def is_placeholder(value: str | None) -> bool:
    if not value:
        return False
    lower = value.lower()
    return any(marker in lower for marker in PLACEHOLDER_MARKERS)


def require(
    errors: List[str],
    env: Dict[str, str],
    key: str,
    *,
    when: str,
    allow_blank: bool = False,
) -> None:
    value = env.get(key, "")
    if not value and not allow_blank:
        errors.append(f"{key} is required when {when}")
    elif is_placeholder(value):
        errors.append(f"{key} still contains an example placeholder")


def warn_if_missing(warnings: List[str], env: Dict[str, str], key: str, message: str) -> None:
    if not env.get(key):
        warnings.append(f"{key}: {message}")


def provider(env: Dict[str, str], key: str, default: str) -> str:
    return env.get(key, default).strip().lower()


def validate(env: Dict[str, str]) -> tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    auth_provider = provider(env, "AUTH_PROVIDER", "local")
    llm_provider = provider(env, "LLM_PROVIDER", "openai_compatible")
    embedding_provider = provider(env, "EMBEDDING_PROVIDER", "openai_compatible")
    template_provider = provider(env, "TEMPLATE_INGEST_PROVIDER", "disabled")
    outbound_email = provider(env, "OUTBOUND_EMAIL_PROVIDER", "none")
    inbound_email = provider(env, "INBOUND_EMAIL_PROVIDER", "none")
    database_provider = provider(env, "DATABASE_PROVIDER", "sqlalchemy")
    storage_provider = provider(env, "STORAGE_PROVIDER", "filesystem")

    if auth_provider == "local":
        require(errors, env, "LOCAL_AUTH_TOKEN", when="AUTH_PROVIDER=local")
        token = env.get("LOCAL_AUTH_TOKEN", "")
        if token and len(token) < 24:
            errors.append("LOCAL_AUTH_TOKEN should be at least 24 characters")
    elif auth_provider == "external_jwt":
        has_secret = bool(env.get("EXTERNAL_JWT_SECRET"))
        has_jwks = bool(env.get("EXTERNAL_JWT_JWKS_URL"))
        if not has_secret and not has_jwks:
            errors.append(
                "EXTERNAL_JWT_SECRET or EXTERNAL_JWT_JWKS_URL is required when "
                "AUTH_PROVIDER=external_jwt"
            )
    elif auth_provider != "supabase":
        errors.append(f"Unsupported AUTH_PROVIDER for self-hosting: {auth_provider}")

    if database_provider == "sqlalchemy":
        require(errors, env, "DATABASE_URL", when="DATABASE_PROVIDER=sqlalchemy")
    elif database_provider != "supabase":
        errors.append(f"Unsupported DATABASE_PROVIDER: {database_provider}")

    if storage_provider == "filesystem":
        require(errors, env, "STORAGE_PATH", when="STORAGE_PROVIDER=filesystem")
    elif storage_provider != "supabase":
        errors.append(f"Unsupported STORAGE_PROVIDER: {storage_provider}")

    uses_openai_compatible = (
        llm_provider == "openai_compatible"
        or embedding_provider == "openai_compatible"
        or template_provider == "openai_compatible"
    )
    if uses_openai_compatible:
        require(
            errors,
            env,
            "OPENAI_COMPATIBLE_BASE_URL",
            when="an OpenAI-compatible provider is enabled",
        )

    if llm_provider == "openai_compatible":
        require(errors, env, "LLM_MODEL", when="LLM_PROVIDER=openai_compatible")

    if embedding_provider == "openai_compatible":
        require(
            errors,
            env,
            "EMBEDDING_MODEL",
            when="EMBEDDING_PROVIDER=openai_compatible",
        )
        warn_if_missing(
            warnings,
            env,
            "EMBEDDING_DIMENSIONS",
            "defaults to 1536 for OpenAI-compatible embeddings",
        )

    if template_provider == "openai_compatible":
        require(
            errors,
            env,
            "TEMPLATE_INGEST_MODEL",
            when="TEMPLATE_INGEST_PROVIDER=openai_compatible",
        )
        warnings.append(
            "TEMPLATE_INGEST_PROVIDER=openai_compatible requires a multimodal "
            "model endpoint; test core report generation first."
        )

    uses_gemini = (
        llm_provider == "gemini"
        or embedding_provider == "gemini"
        or template_provider == "gemini"
    )
    if uses_gemini:
        require(errors, env, "GEMINI_API_KEY", when="a Gemini provider is enabled")

    if outbound_email == "microsoft_graph" or inbound_email == "microsoft_graph":
        for key in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET", "GRAPH_MAILBOX"):
            require(errors, env, key, when="Microsoft Graph email is enabled")

    if inbound_email == "microsoft_graph":
        require(
            errors,
            env,
            "INTERNAL_CRON_SECRET",
            when="INBOUND_EMAIL_PROVIDER=microsoft_graph",
        )

    if outbound_email == "resend" or inbound_email == "resend":
        require(errors, env, "RESEND_API_KEY", when="Resend email is enabled")

    if inbound_email == "resend":
        require(errors, env, "RESEND_WEBHOOK_SECRET", when="INBOUND_EMAIL_PROVIDER=resend")

    return errors, warnings


def print_items(title: str, items: Iterable[str]) -> None:
    print(title)
    for item in items:
        print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "env_file",
        nargs="?",
        default=".env",
        help="Environment file to check. Defaults to .env.",
    )
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        print(f"ERROR: {path} does not exist.")
        print(
            "Run scripts/init_self_hosted_env.py to create it, or copy "
            ".env.example to .env and edit it manually."
        )
        return 2

    env = parse_env(path)
    errors, warnings = validate(env)

    if errors:
        print_items("ERRORS", errors)
    if warnings:
        print_items("WARNINGS", warnings)

    if errors:
        print(f"Self-hosted env preflight failed for {path}.")
        return 1

    print(f"Self-hosted env preflight passed for {path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
