"""Preflight checks for the self-hosted Docker environment file.

This script intentionally uses only the Python standard library so users can run
it before installing backend dependencies.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List
from urllib.parse import urlsplit


PLACEHOLDER_MARKERS = (
    "replace-with",
    "paste_",
    "your_",
    "your-",
    "your ",
    "<tenant-id>",
    "<internal_cron_secret>",
)
CURRENT_GEMINI_LLM_MODEL = "gemini-3.5-flash"
CURRENT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
GEMINI_MODELS_BLOCKED_FOR_NEW_USERS = {
    "gemini-2.5-flash": (
        "Google may reject this model for new Gemini API users; use "
        f"{CURRENT_GEMINI_LLM_MODEL} for current Docker pilots"
    ),
}
GEMINI_SHUT_DOWN_MODELS = {
    "gemini-embedding-001": (
        "has been shut down; use "
        f"{CURRENT_GEMINI_EMBEDDING_MODEL}"
    ),
    "text-embedding-004": (
        "has been shut down; use "
        f"{CURRENT_GEMINI_EMBEDDING_MODEL}"
    ),
}
SAFE_OIDC_ID_TOKEN_ALGORITHMS = {
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
}
COOKIE_NAME_CHARACTERS = frozenset(
    "!#$%&'*+-.^_`|~"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
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
    email_job_execution_mode = provider(env, "EMAIL_JOB_EXECUTION_MODE", "worker")
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
    elif auth_provider == "oidc":
        for key in (
            "OIDC_DISCOVERY_URL",
            "OIDC_CLIENT_ID",
            "OIDC_CALLBACK_URL",
            "OIDC_USER_ROLE",
            "OIDC_ADMIN_ROLE",
            "OIDC_ORGANIZATION_SLUG",
            "OIDC_ORGANIZATION_NAME",
        ):
            require(errors, env, key, when="AUTH_PROVIDER=oidc")
        client_auth_method = provider(
            env,
            "OIDC_CLIENT_AUTH_METHOD",
            "client_secret_post",
        )
        if client_auth_method not in {
            "client_secret_basic",
            "client_secret_post",
            "none",
        }:
            errors.append(
                "OIDC_CLIENT_AUTH_METHOD must be client_secret_basic, "
                "client_secret_post, or none"
            )
        if client_auth_method != "none":
            require(errors, env, "OIDC_CLIENT_SECRET", when="OIDC confidential client auth")
        if "openid" not in env.get("OIDC_SCOPES", "openid profile email").split():
            errors.append("OIDC_SCOPES must include openid")
        allowed_algorithms = {
            value.strip()
            for value in env.get("OIDC_ALLOWED_ID_TOKEN_ALGORITHMS", "RS256").split(",")
            if value.strip()
        }
        if not allowed_algorithms:
            errors.append("OIDC_ALLOWED_ID_TOKEN_ALGORITHMS cannot be empty")
        unsupported_algorithms = allowed_algorithms - SAFE_OIDC_ID_TOKEN_ALGORITHMS
        if unsupported_algorithms:
            errors.append(
                "OIDC_ALLOWED_ID_TOKEN_ALGORITHMS contains unsupported values: "
                + ", ".join(sorted(unsupported_algorithms))
            )
        if not env.get("OIDC_ROLES_CLAIM", "roles").strip():
            errors.append("OIDC_ROLES_CLAIM cannot be blank")
        user_role = env.get("OIDC_USER_ROLE", "Attenly.User").strip()
        admin_role = env.get("OIDC_ADMIN_ROLE", "Attenly.Admin").strip()
        if user_role and admin_role and user_role == admin_role:
            errors.append("OIDC_USER_ROLE and OIDC_ADMIN_ROLE must be different")
        for key, default, minimum, maximum in (
            ("OIDC_SESSION_TTL_HOURS", "12", 1, 168),
            ("OIDC_LOGIN_TTL_SECONDS", "600", 60, 1800),
            ("OIDC_CLOCK_SKEW_SECONDS", "60", 0, 300),
        ):
            try:
                value = int(env.get(key, default))
                if value < minimum or value > maximum:
                    errors.append(f"{key} must be between {minimum} and {maximum}")
            except ValueError:
                errors.append(f"{key} must be an integer")
        cookie_names = {
            "OIDC_SESSION_COOKIE_NAME": env.get(
                "OIDC_SESSION_COOKIE_NAME", "__Host-attenly_session"
            ).strip(),
            "OIDC_LOGIN_COOKIE_NAME": env.get(
                "OIDC_LOGIN_COOKIE_NAME", "__Host-attenly_oidc_flow"
            ).strip(),
        }
        invalid_cookie_names = [
            key
            for key, value in cookie_names.items()
            if not value or any(character not in COOKIE_NAME_CHARACTERS for character in value)
        ]
        if invalid_cookie_names:
            errors.append(
                "OIDC cookie names are blank or invalid: "
                + ", ".join(invalid_cookie_names)
            )
        if cookie_names["OIDC_SESSION_COOKIE_NAME"] == cookie_names["OIDC_LOGIN_COOKIE_NAME"]:
            errors.append("OIDC session and login cookie names must be different")
        allow_insecure = provider(env, "OIDC_ALLOW_INSECURE_HTTP", "false") in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not allow_insecure:
            for key in ("OIDC_DISCOVERY_URL", "OIDC_CALLBACK_URL"):
                value = env.get(key, "")
                if value and not value.startswith("https://"):
                    errors.append(f"{key} must use HTTPS")
        environment = provider(env, "ENV", "development")
        cookie_secure = provider(
            env,
            "OIDC_COOKIE_SECURE",
            "true" if environment == "production" else "false",
        ) in {"1", "true", "yes", "on"}
        if not cookie_secure and any(
            value.startswith("__Host-") for value in cookie_names.values()
        ):
            errors.append(
                "__Host- OIDC cookie names require OIDC_COOKIE_SECURE=true; "
                "use non-prefixed cookie names only for local HTTP development"
            )
        if environment == "production" and not cookie_secure:
            errors.append("OIDC_COOKIE_SECURE must be true in production")
        if environment == "production" and allow_insecure:
            errors.append("OIDC_ALLOW_INSECURE_HTTP cannot be enabled in production")
        if environment == "production":
            for key, value in cookie_names.items():
                if value and not value.startswith("__Host-"):
                    errors.append(f"{key} must use the __Host- prefix in production")
        cors_origins = {
            origin.strip()
            for origin in env.get("CORS_ORIGINS", "").split(",")
        }
        if "*" in cors_origins:
            errors.append("CORS_ORIGINS cannot contain '*' with OIDC authentication")
        callback_url = env.get("OIDC_CALLBACK_URL", "").strip()
        app_url = env.get("APP_URL", "https://app.attenly.ca").strip()
        if callback_url and app_url:
            callback = urlsplit(callback_url)
            application = urlsplit(app_url)
            if (
                callback.scheme.lower(),
                callback.netloc.casefold(),
            ) != (
                application.scheme.lower(),
                application.netloc.casefold(),
            ):
                errors.append(
                    "OIDC_CALLBACK_URL and APP_URL must use the same origin for the "
                    "cookie-backed login flow"
                )
        if database_provider != "sqlalchemy":
            errors.append("OIDC authentication requires DATABASE_PROVIDER=sqlalchemy")
        if storage_provider != "filesystem":
            errors.append("OIDC authentication requires STORAGE_PROVIDER=filesystem")
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
        timeout_value = env.get("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "300")
        try:
            if int(timeout_value) < 1:
                errors.append("OPENAI_COMPATIBLE_TIMEOUT_SECONDS must be at least 1")
        except ValueError:
            errors.append("OPENAI_COMPATIBLE_TIMEOUT_SECONDS must be an integer")

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
        try:
            if int(env.get("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "300")) < 300:
                warnings.append(
                    "Smart template ingestion may need five minutes; consider "
                    "OPENAI_COMPATIBLE_TIMEOUT_SECONDS=300."
                )
        except ValueError:
            pass
    elif template_provider == "gemini":
        require(
            errors,
            env,
            "TEMPLATE_INGEST_MODEL_NAME",
            when="TEMPLATE_INGEST_PROVIDER=gemini",
        )
        warnings.append(
            "TEMPLATE_INGEST_PROVIDER=gemini requires a multimodal Gemini model; "
            "test core report generation first."
        )

    uses_gemini = (
        llm_provider == "gemini"
        or embedding_provider == "gemini"
        or template_provider == "gemini"
    )
    if uses_gemini:
        require(errors, env, "GEMINI_API_KEY", when="a Gemini provider is enabled")

    if llm_provider == "gemini":
        llm_model = env.get("LLM_MODEL", "").strip()
        warning = GEMINI_MODELS_BLOCKED_FOR_NEW_USERS.get(llm_model)
        if warning:
            warnings.append(f"LLM_MODEL={llm_model}: {warning}")

    if embedding_provider == "gemini":
        embedding_model = env.get("EMBEDDING_MODEL", "").strip()
        error = GEMINI_SHUT_DOWN_MODELS.get(embedding_model)
        if error:
            errors.append(f"EMBEDDING_MODEL={embedding_model} {error}")

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

    if inbound_email in {"microsoft_graph", "resend"}:
        if email_job_execution_mode not in {"worker", "inline"}:
            errors.append("EMAIL_JOB_EXECUTION_MODE must be 'worker' or 'inline'")
        if email_job_execution_mode == "inline":
            warnings.append(
                "EMAIL_JOB_EXECUTION_MODE=inline processes email jobs inside the "
                "web backend; Docker pilots should use worker."
            )

        poll_interval = env.get("EMAIL_WORKER_POLL_INTERVAL_SECONDS", "30")
        try:
            if int(poll_interval) < 5:
                errors.append("EMAIL_WORKER_POLL_INTERVAL_SECONDS must be at least 5")
        except ValueError:
            errors.append("EMAIL_WORKER_POLL_INTERVAL_SECONDS must be an integer")

        max_jobs = env.get("EMAIL_WORKER_MAX_JOBS_PER_CYCLE", "1")
        try:
            max_jobs_int = int(max_jobs)
            if max_jobs_int < 1 or max_jobs_int > 10:
                errors.append("EMAIL_WORKER_MAX_JOBS_PER_CYCLE must be between 1 and 10")
        except ValueError:
            errors.append("EMAIL_WORKER_MAX_JOBS_PER_CYCLE must be an integer")

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
