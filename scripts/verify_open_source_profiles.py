"""Verify documented open-source provider profiles pass backend config validation.

This script does not contact Supabase, Gemini, OpenAI-compatible endpoints,
Microsoft Graph, Resend, Redis, or a database. It only imports backend config
with representative environment variables and checks that startup validation
and the config summary agree with the documented profiles.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend"

CONFIG_ENV_KEYS = {
    "APP_PROFILE",
    "AUTH_PROVIDER",
    "DATABASE_PROVIDER",
    "STORAGE_PROVIDER",
    "LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "TEMPLATE_INGEST_PROVIDER",
    "OUTBOUND_EMAIL_PROVIDER",
    "INBOUND_EMAIL_PROVIDER",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GEMINI_API_KEY",
    "LOCAL_AUTH_TOKEN",
    "LOCAL_AUTH_USER_ID",
    "LOCAL_AUTH_EMAIL",
    "LOCAL_AUTH_DISPLAY_NAME",
    "EXTERNAL_JWT_SECRET",
    "EXTERNAL_JWT_JWKS_URL",
    "EXTERNAL_JWT_ALGORITHM",
    "EXTERNAL_JWT_ISSUER",
    "EXTERNAL_JWT_AUDIENCE",
    "EXTERNAL_JWT_USER_ID_CLAIM",
    "EXTERNAL_JWT_EMAIL_CLAIM",
    "EXTERNAL_JWT_NAME_CLAIM",
    "EXTERNAL_JWT_REQUIRE_EXP",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_API_KEY",
    "LLM_MODEL",
    "EMBEDDING_MODEL",
    "TEMPLATE_INGEST_MODEL",
    "TEMPLATE_INGEST_MODEL_NAME",
    "DATABASE_URL",
    "DATABASE_AUTO_CREATE_TABLES",
    "STORAGE_PATH",
    "RESEND_API_KEY",
    "RESEND_WEBHOOK_SECRET",
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_CLIENT_SECRET",
    "GRAPH_MAILBOX",
    "DEFAULT_MONTHLY_LIMIT_CAD",
    "DEFAULT_MODEL_INPUT_COST_PER_MILLION_CAD",
    "DEFAULT_MODEL_OUTPUT_COST_PER_MILLION_CAD",
}

SUMMARY_SCRIPT = """
import json
from app.config import get_config_summary, validate_config

validate_config()
print(json.dumps(get_config_summary(), sort_keys=True))
"""


@dataclass(frozen=True)
class ProfileCase:
    name: str
    env: dict[str, str]
    expected: dict[str, Any]


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in CONFIG_ENV_KEYS:
        env.pop(key, None)

    pythonpath_parts = [str(BACKEND_PATH)]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def run_case(case: ProfileCase) -> dict[str, Any]:
    env = base_env()
    env.update(case.env)

    result = subprocess.run(
        [sys.executable, "-c", SUMMARY_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{case.name} failed validation\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{case.name} returned non-JSON output:\n{result.stdout}"
        ) from exc


def assert_path(summary: dict[str, Any], path: str, expected: Any) -> None:
    value: Any = summary
    for part in path.split("."):
        value = value[part]
    if value != expected:
        raise AssertionError(f"{path}: expected {expected!r}, got {value!r}")


def verify_case(case: ProfileCase) -> None:
    summary = run_case(case)
    for path, expected in case.expected.items():
        assert_path(summary, path, expected)
    print(f"PASS {case.name}")


def verify_example_placeholders_are_rejected() -> None:
    env = base_env()
    env.update(
        {
            "APP_PROFILE": "local",
            "AUTH_PROVIDER": "local",
            "LOCAL_AUTH_TOKEN": "replace-with-a-long-random-token",
            "DATABASE_PROVIDER": "sqlalchemy",
            "DATABASE_URL": "sqlite:////data/attenly.db",
            "STORAGE_PROVIDER": "filesystem",
            "STORAGE_PATH": "/data/storage",
            "LLM_PROVIDER": "openai_compatible",
            "LLM_MODEL": "replace-with-chat-model",
            "EMBEDDING_PROVIDER": "openai_compatible",
            "EMBEDDING_MODEL": "replace-with-embedding-model",
            "OPENAI_COMPATIBLE_BASE_URL": "http://host.docker.internal:11434/v1",
            "TEMPLATE_INGEST_PROVIDER": "disabled",
            "OUTBOUND_EMAIL_PROVIDER": "none",
            "INBOUND_EMAIL_PROVIDER": "none",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", SUMMARY_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode == 0 or "example placeholder" not in output:
        raise AssertionError(
            "Unchanged self-hosted example placeholders must fail validation\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    print("PASS unchanged_self_hosted_placeholders_rejected")


def cases() -> list[ProfileCase]:
    return [
        ProfileCase(
            name="default_supabase_gemini_no_email",
            env={
                "APP_PROFILE": "default",
                "AUTH_PROVIDER": "supabase",
                "DATABASE_PROVIDER": "supabase",
                "STORAGE_PROVIDER": "supabase",
                "LLM_PROVIDER": "gemini",
                "EMBEDDING_PROVIDER": "gemini",
                "TEMPLATE_INGEST_PROVIDER": "gemini",
                "OUTBOUND_EMAIL_PROVIDER": "none",
                "INBOUND_EMAIL_PROVIDER": "none",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "fake-service-key",
                "SUPABASE_ANON_KEY": "fake-anon-key",
                "SUPABASE_SERVICE_ROLE_KEY": "fake-service-role-key",
                "GEMINI_API_KEY": "fake-gemini-key",
            },
            expected={
                "profile.app_profile": "default",
                "profile.providers.auth": "supabase",
                "profile.providers.database": "supabase",
                "profile.providers.storage": "supabase",
                "profile.providers.llm": "gemini",
                "profile.providers.embedding": "gemini",
                "profile.providers.template_ingest": "gemini",
                "email.inbound_runtime_enabled": False,
            },
        ),
        ProfileCase(
            name="local_sqlite_filesystem_gemini",
            env={
                "APP_PROFILE": "local",
                "AUTH_PROVIDER": "local",
                "LOCAL_AUTH_TOKEN": "fake-local-token",
                "DATABASE_PROVIDER": "sqlalchemy",
                "DATABASE_URL": "sqlite:////data/attenly.db",
                "STORAGE_PROVIDER": "filesystem",
                "STORAGE_PATH": "/data/storage",
                "LLM_PROVIDER": "gemini",
                "EMBEDDING_PROVIDER": "gemini",
                "GEMINI_API_KEY": "fake-gemini-key",
                "TEMPLATE_INGEST_PROVIDER": "disabled",
                "OUTBOUND_EMAIL_PROVIDER": "none",
                "INBOUND_EMAIL_PROVIDER": "none",
            },
            expected={
                "profile.app_profile": "local",
                "profile.providers.auth": "local",
                "profile.providers.database": "sqlalchemy",
                "profile.providers.storage": "filesystem",
                "profile.providers.template_ingest": "disabled",
                "auth.local_auth_token_configured": True,
                "database.url_configured": True,
                "storage.provider": "filesystem",
            },
        ),
        ProfileCase(
            name="enterprise_openai_compatible_no_email",
            env={
                "APP_PROFILE": "enterprise",
                "AUTH_PROVIDER": "local",
                "LOCAL_AUTH_TOKEN": "fake-local-token",
                "DATABASE_PROVIDER": "sqlalchemy",
                "DATABASE_URL": "sqlite:////data/attenly.db",
                "STORAGE_PROVIDER": "filesystem",
                "STORAGE_PATH": "/data/storage",
                "LLM_PROVIDER": "openai_compatible",
                "LLM_MODEL": "company-document-model",
                "EMBEDDING_PROVIDER": "openai_compatible",
                "EMBEDDING_MODEL": "company-embedding-model",
                "OPENAI_COMPATIBLE_BASE_URL": "https://models.company.internal/v1",
                "OPENAI_COMPATIBLE_API_KEY": "fake-model-token",
                "TEMPLATE_INGEST_PROVIDER": "openai_compatible",
                "TEMPLATE_INGEST_MODEL": "company-template-model",
                "OUTBOUND_EMAIL_PROVIDER": "none",
                "INBOUND_EMAIL_PROVIDER": "none",
            },
            expected={
                "profile.app_profile": "enterprise",
                "profile.providers.llm": "openai_compatible",
                "profile.providers.embedding": "openai_compatible",
                "profile.providers.template_ingest": "openai_compatible",
                "llm.openai_compatible_base_url_configured": True,
                "template_ingest.model_name": "company-template-model",
                "template_ingest.requires_multimodal_model": True,
                "email.outbound_provider": "none",
            },
        ),
        ProfileCase(
            name="enterprise_openai_graph_outbound",
            env={
                "APP_PROFILE": "enterprise",
                "AUTH_PROVIDER": "local",
                "LOCAL_AUTH_TOKEN": "fake-local-token",
                "DATABASE_PROVIDER": "sqlalchemy",
                "DATABASE_URL": "sqlite:////data/attenly.db",
                "STORAGE_PROVIDER": "filesystem",
                "LLM_PROVIDER": "openai_compatible",
                "EMBEDDING_PROVIDER": "openai_compatible",
                "OPENAI_COMPATIBLE_BASE_URL": "https://models.company.internal/v1",
                "TEMPLATE_INGEST_PROVIDER": "disabled",
                "OUTBOUND_EMAIL_PROVIDER": "microsoft_graph",
                "INBOUND_EMAIL_PROVIDER": "none",
                "GRAPH_TENANT_ID": "fake-tenant",
                "GRAPH_CLIENT_ID": "fake-client",
                "GRAPH_CLIENT_SECRET": "fake-secret",
                "GRAPH_MAILBOX": "attenly@example.com",
            },
            expected={
                "profile.app_profile": "enterprise",
                "profile.providers.outbound_email": "microsoft_graph",
                "profile.providers.inbound_email": "none",
                "email.graph_tenant_configured": True,
                "email.graph_client_configured": True,
                "email.graph_mailbox_configured": True,
            },
        ),
        ProfileCase(
            name="enterprise_openai_external_jwt",
            env={
                "APP_PROFILE": "enterprise",
                "AUTH_PROVIDER": "external_jwt",
                "EXTERNAL_JWT_SECRET": "fake-external-jwt-secret",
                "EXTERNAL_JWT_ALGORITHM": "HS256",
                "EXTERNAL_JWT_ISSUER": "https://idp.company.internal",
                "EXTERNAL_JWT_AUDIENCE": "attenly",
                "DATABASE_PROVIDER": "sqlalchemy",
                "DATABASE_URL": "sqlite:////data/attenly.db",
                "STORAGE_PROVIDER": "filesystem",
                "LLM_PROVIDER": "openai_compatible",
                "EMBEDDING_PROVIDER": "openai_compatible",
                "OPENAI_COMPATIBLE_BASE_URL": "https://models.company.internal/v1",
                "TEMPLATE_INGEST_PROVIDER": "disabled",
                "OUTBOUND_EMAIL_PROVIDER": "none",
                "INBOUND_EMAIL_PROVIDER": "none",
            },
            expected={
                "profile.app_profile": "enterprise",
                "profile.providers.auth": "external_jwt",
                "auth.external_jwt_secret_configured": True,
                "auth.external_jwt_algorithm": "HS256",
                "auth.external_jwt_issuer_configured": True,
                "auth.external_jwt_audience_configured": True,
            },
        ),
        ProfileCase(
            name="enterprise_openai_graph_inbound",
            env={
                "APP_PROFILE": "enterprise",
                "AUTH_PROVIDER": "local",
                "LOCAL_AUTH_TOKEN": "fake-local-token",
                "DATABASE_PROVIDER": "sqlalchemy",
                "DATABASE_URL": "sqlite:////data/attenly.db",
                "STORAGE_PROVIDER": "filesystem",
                "LLM_PROVIDER": "openai_compatible",
                "EMBEDDING_PROVIDER": "openai_compatible",
                "OPENAI_COMPATIBLE_BASE_URL": "https://models.company.internal/v1",
                "TEMPLATE_INGEST_PROVIDER": "disabled",
                "OUTBOUND_EMAIL_PROVIDER": "none",
                "INBOUND_EMAIL_PROVIDER": "microsoft_graph",
                "GRAPH_TENANT_ID": "fake-tenant",
                "GRAPH_CLIENT_ID": "fake-client",
                "GRAPH_CLIENT_SECRET": "fake-secret",
                "GRAPH_MAILBOX": "attenly@example.com",
            },
            expected={
                "profile.app_profile": "enterprise",
                "profile.providers.inbound_email": "microsoft_graph",
                "email.inbound_runtime_enabled": True,
                "email.graph_tenant_configured": True,
                "email.graph_client_configured": True,
                "email.graph_mailbox_configured": True,
            },
        ),
    ]


def main() -> int:
    for case in cases():
        verify_case(case)

    verify_example_placeholders_are_rejected()

    print("All documented open-source profile checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
