"""Create a self-hosted Docker .env file from .env.example.

The script generates LOCAL_AUTH_TOKEN and asks for the model values that Attenly
cannot safely guess.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from check_self_hosted_env import parse_env, validate


DEFAULT_MODEL_BASE_URL = "http://host.docker.internal:11434/v1"
DEFAULT_MODEL_TIMEOUT_SECONDS = "300"
DEFAULT_EMBEDDING_DIMENSIONS = "1536"
DEFAULT_GEMINI_LLM_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_GEMINI_TEMPLATE_INGEST_MODEL = "gemini-3.5-flash"
DEFAULT_EMAIL_WORKER_POLL_INTERVAL_SECONDS = "30"
DEFAULT_EMAIL_WORKER_MAX_JOBS_PER_CYCLE = "1"
EMAIL_PROVIDER_CHOICES = ("none", "microsoft_graph", "resend")
MODEL_PROVIDER_CHOICES = ("openai_compatible", "gemini")
TEMPLATE_INGEST_PROVIDER_CHOICES = ("disabled", "basic", "gemini", "openai_compatible")


def prompt_value(name: str, current: str | None, default: str | None = None) -> str:
    if current:
        return current

    if sys.stdin.isatty():
        suffix = f" [{default}]" if default else ""
        value = input(f"{name}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default

    if default is not None:
        return default

    flag = "--" + name.lower().replace("_", "-")
    raise SystemExit(f"{name} is required. Pass it with {flag}.")


def update_env_lines(lines: Iterable[str], updates: Dict[str, str]) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        output.append(line.rstrip("\n"))

    missing = [key for key in updates if key not in seen]
    if missing:
        output.append("")
        output.append("# Added by scripts/init_self_hosted_env.py")
        for key in missing:
            output.append(f"{key}={updates[key]}")

    return output


def write_env(path: Path, lines: List[str], *, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists. Use --force to overwrite it.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def selected_email_providers(args: argparse.Namespace) -> tuple[str, str]:
    default_provider = args.email_provider or "none"
    outbound = args.outbound_email_provider or default_provider
    inbound = args.inbound_email_provider or default_provider
    return outbound, inbound


def selected_model_providers(args: argparse.Namespace) -> tuple[str, str]:
    default_provider = args.provider or "openai_compatible"
    llm_provider = args.llm_provider or default_provider
    embedding_provider = args.embedding_provider or default_provider
    return llm_provider, embedding_provider


def apply_model_updates(
    updates: Dict[str, str],
    args: argparse.Namespace,
    llm_provider: str,
    embedding_provider: str,
    template_ingest_provider: str,
) -> None:
    updates["LLM_PROVIDER"] = llm_provider
    updates["EMBEDDING_PROVIDER"] = embedding_provider
    updates["TEMPLATE_INGEST_PROVIDER"] = template_ingest_provider

    uses_openai_compatible = (
        llm_provider == "openai_compatible"
        or embedding_provider == "openai_compatible"
        or template_ingest_provider == "openai_compatible"
    )
    if uses_openai_compatible:
        updates["OPENAI_COMPATIBLE_BASE_URL"] = prompt_value(
            "OPENAI_COMPATIBLE_BASE_URL",
            args.model_base_url,
            DEFAULT_MODEL_BASE_URL,
        )
        updates["OPENAI_COMPATIBLE_API_KEY"] = args.model_api_key
        updates["OPENAI_COMPATIBLE_TIMEOUT_SECONDS"] = args.model_timeout_seconds
    else:
        updates["OPENAI_COMPATIBLE_BASE_URL"] = ""
        updates["OPENAI_COMPATIBLE_API_KEY"] = ""
        updates["OPENAI_COMPATIBLE_TIMEOUT_SECONDS"] = args.model_timeout_seconds

    if llm_provider == "openai_compatible":
        updates["LLM_MODEL"] = prompt_value("LLM_MODEL", args.llm_model)
    elif llm_provider == "gemini":
        updates["LLM_MODEL"] = args.llm_model or DEFAULT_GEMINI_LLM_MODEL
    else:
        updates["LLM_MODEL"] = args.llm_model or ""

    if embedding_provider == "openai_compatible":
        updates["EMBEDDING_MODEL"] = prompt_value("EMBEDDING_MODEL", args.embedding_model)
        updates["EMBEDDING_DIMENSIONS"] = args.embedding_dimensions or DEFAULT_EMBEDDING_DIMENSIONS
    elif embedding_provider == "gemini":
        updates["EMBEDDING_MODEL"] = args.embedding_model or DEFAULT_GEMINI_EMBEDDING_MODEL
        updates["EMBEDDING_DIMENSIONS"] = args.embedding_dimensions or "768"
    else:
        updates["EMBEDDING_MODEL"] = args.embedding_model or ""
        updates["EMBEDDING_DIMENSIONS"] = args.embedding_dimensions or "768"

    uses_gemini = (
        llm_provider == "gemini"
        or embedding_provider == "gemini"
        or template_ingest_provider == "gemini"
    )
    if uses_gemini:
        updates["GEMINI_API_KEY"] = prompt_value("GEMINI_API_KEY", args.gemini_api_key)
    else:
        updates["GEMINI_API_KEY"] = args.gemini_api_key or ""

    if template_ingest_provider == "gemini":
        updates["TEMPLATE_INGEST_MODEL_NAME"] = (
            args.template_ingest_model or DEFAULT_GEMINI_TEMPLATE_INGEST_MODEL
        )
    elif template_ingest_provider == "openai_compatible":
        updates["TEMPLATE_INGEST_MODEL"] = prompt_value(
            "TEMPLATE_INGEST_MODEL",
            args.template_ingest_model,
        )
        updates["TEMPLATE_INGEST_MODEL_NAME"] = ""
    else:
        updates["TEMPLATE_INGEST_MODEL"] = ""
        updates["TEMPLATE_INGEST_MODEL_NAME"] = ""


def apply_email_updates(
    updates: Dict[str, str],
    args: argparse.Namespace,
    outbound_email_provider: str,
    inbound_email_provider: str,
) -> bool:
    generated_internal_cron_secret = False
    updates["OUTBOUND_EMAIL_PROVIDER"] = outbound_email_provider
    updates["INBOUND_EMAIL_PROVIDER"] = inbound_email_provider

    uses_graph = (
        outbound_email_provider == "microsoft_graph"
        or inbound_email_provider == "microsoft_graph"
    )
    if uses_graph:
        updates["GRAPH_TENANT_ID"] = prompt_value("GRAPH_TENANT_ID", args.graph_tenant_id)
        updates["GRAPH_CLIENT_ID"] = prompt_value("GRAPH_CLIENT_ID", args.graph_client_id)
        updates["GRAPH_CLIENT_SECRET"] = prompt_value(
            "GRAPH_CLIENT_SECRET",
            args.graph_client_secret,
        )
        updates["GRAPH_MAILBOX"] = prompt_value("GRAPH_MAILBOX", args.graph_mailbox)
        updates["GRAPH_POLL_BATCH_SIZE"] = args.graph_poll_batch_size
        updates["GRAPH_POLL_LOOKBACK_SECONDS"] = args.graph_poll_lookback_seconds

    if inbound_email_provider == "microsoft_graph":
        updates["EMAIL_JOB_EXECUTION_MODE"] = args.email_job_execution_mode
        updates["EMAIL_WORKER_POLL_INTERVAL_SECONDS"] = args.email_worker_poll_interval_seconds
        updates["EMAIL_WORKER_MAX_JOBS_PER_CYCLE"] = args.email_worker_max_jobs_per_cycle
        if args.internal_cron_secret:
            updates["INTERNAL_CRON_SECRET"] = args.internal_cron_secret
        else:
            updates["INTERNAL_CRON_SECRET"] = secrets.token_urlsafe(32)
            generated_internal_cron_secret = True

    uses_resend = outbound_email_provider == "resend" or inbound_email_provider == "resend"
    if uses_resend:
        updates["RESEND_API_KEY"] = prompt_value("RESEND_API_KEY", args.resend_api_key)

    if inbound_email_provider == "resend":
        updates["EMAIL_JOB_EXECUTION_MODE"] = args.email_job_execution_mode
        updates["EMAIL_WORKER_POLL_INTERVAL_SECONDS"] = args.email_worker_poll_interval_seconds
        updates["EMAIL_WORKER_MAX_JOBS_PER_CYCLE"] = args.email_worker_max_jobs_per_cycle
        updates["RESEND_WEBHOOK_SECRET"] = prompt_value(
            "RESEND_WEBHOOK_SECRET",
            args.resend_webhook_secret,
        )

    return generated_internal_cron_secret


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=".env.example", help="Template env file.")
    parser.add_argument("--output", default=".env", help="Output env file.")
    parser.add_argument("--force", action="store_true", help="Overwrite output file.")
    parser.add_argument("--local-auth-token", help="Use this token instead of generating one.")
    parser.add_argument(
        "--provider",
        choices=MODEL_PROVIDER_CHOICES,
        help=(
            "Set both LLM and embedding providers. Defaults to openai_compatible. "
            "Use gemini for Gemini-backed local pilots."
        ),
    )
    parser.add_argument(
        "--llm-provider",
        choices=MODEL_PROVIDER_CHOICES,
        help="Set only the LLM provider.",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=MODEL_PROVIDER_CHOICES,
        help="Set only the embedding provider.",
    )
    parser.add_argument("--gemini-api-key", help="Gemini API key.")
    parser.add_argument(
        "--model-base-url",
        help=f"OpenAI-compatible base URL. Defaults to {DEFAULT_MODEL_BASE_URL}.",
    )
    parser.add_argument("--model-api-key", default="", help="Optional model gateway API key.")
    parser.add_argument(
        "--model-timeout-seconds",
        default=DEFAULT_MODEL_TIMEOUT_SECONDS,
        help=(
            "Maximum time for one OpenAI-compatible model request. Defaults to "
            f"{DEFAULT_MODEL_TIMEOUT_SECONDS} seconds."
        ),
    )
    parser.add_argument("--llm-model", help="Chat/completions model served by the gateway.")
    parser.add_argument("--embedding-model", help="Embedding model served by the gateway.")
    parser.add_argument(
        "--embedding-dimensions",
        help=(
            "Embedding vector dimensions. Defaults to 1536 for OpenAI-compatible "
            "providers and 768 for Gemini."
        ),
    )
    parser.add_argument(
        "--template-ingest-provider",
        default="disabled",
        choices=TEMPLATE_INGEST_PROVIDER_CHOICES,
        help="Template upload interpretation provider. Defaults to disabled.",
    )
    parser.add_argument(
        "--template-ingest-model",
        help=(
            "Model used when smart template ingestion is enabled. Defaults to "
            f"{DEFAULT_GEMINI_TEMPLATE_INGEST_MODEL} for Gemini."
        ),
    )
    parser.add_argument("--frontend-port", default="5173", help="Frontend host port.")
    parser.add_argument(
        "--email-provider",
        choices=EMAIL_PROVIDER_CHOICES,
        help="Set both inbound and outbound email providers. Defaults to none.",
    )
    parser.add_argument(
        "--outbound-email-provider",
        choices=EMAIL_PROVIDER_CHOICES,
        help="Set only the outbound email provider.",
    )
    parser.add_argument(
        "--inbound-email-provider",
        choices=EMAIL_PROVIDER_CHOICES,
        help="Set only the inbound email provider.",
    )
    parser.add_argument("--graph-tenant-id", help="Microsoft Entra tenant ID.")
    parser.add_argument("--graph-client-id", help="Microsoft Graph app client ID.")
    parser.add_argument("--graph-client-secret", help="Microsoft Graph app client secret.")
    parser.add_argument("--graph-mailbox", help="Mailbox used by Microsoft Graph email.")
    parser.add_argument("--graph-poll-batch-size", default="10", help="Graph poll batch size.")
    parser.add_argument(
        "--graph-poll-lookback-seconds",
        default="300",
        help="Graph polling overlap window in seconds.",
    )
    parser.add_argument(
        "--internal-cron-secret",
        help="Secret for internal email polling routes. Generated for Graph inbound if omitted.",
    )
    parser.add_argument(
        "--email-job-execution-mode",
        default="worker",
        choices=("worker", "inline"),
        help=(
            "How queued email jobs run. The Docker self-hosted default is worker; "
            "inline is only for legacy single-process deployments."
        ),
    )
    parser.add_argument(
        "--email-worker-poll-interval-seconds",
        default=DEFAULT_EMAIL_WORKER_POLL_INTERVAL_SECONDS,
        help="How often the Compose email-worker polls/processes jobs. Defaults to 30.",
    )
    parser.add_argument(
        "--email-worker-max-jobs-per-cycle",
        default=DEFAULT_EMAIL_WORKER_MAX_JOBS_PER_CYCLE,
        help="Maximum queued email jobs processed per worker loop. Defaults to 1.",
    )
    parser.add_argument("--resend-api-key", help="Resend API key.")
    parser.add_argument("--resend-webhook-secret", help="Resend inbound webhook secret.")
    args = parser.parse_args()
    generated_local_auth_token = args.local_auth_token is None
    outbound_email_provider, inbound_email_provider = selected_email_providers(args)
    llm_provider, embedding_provider = selected_model_providers(args)

    template_path = Path(args.template)
    output_path = Path(args.output)
    if not template_path.exists():
        raise SystemExit(f"{template_path} does not exist.")

    updates = {
        "ATTENLY_FRONTEND_PORT": args.frontend_port,
        "AUTH_PROVIDER": "local",
        "LOCAL_AUTH_TOKEN": args.local_auth_token or secrets.token_urlsafe(32),
    }
    apply_model_updates(
        updates,
        args,
        llm_provider,
        embedding_provider,
        args.template_ingest_provider,
    )
    generated_internal_cron_secret = apply_email_updates(
        updates,
        args,
        outbound_email_provider,
        inbound_email_provider,
    )

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    new_lines = update_env_lines(template_lines, updates)
    write_env(output_path, new_lines, force=args.force)

    errors, warnings = validate(parse_env(output_path))
    if errors:
        print(f"Created {output_path}, but preflight found errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    print(f"Created {output_path}.")
    if generated_local_auth_token:
        print("LOCAL_AUTH_TOKEN was generated and written to the file.")
    else:
        print("LOCAL_AUTH_TOKEN was written to the file.")
    print(
        "Email providers: "
        f"outbound={outbound_email_provider}, inbound={inbound_email_provider}."
    )
    print(
        "Model providers: "
        f"llm={llm_provider}, embedding={embedding_provider}, "
        f"template_ingest={args.template_ingest_provider}."
    )
    if generated_internal_cron_secret:
        print("INTERNAL_CRON_SECRET was generated and written to the file.")
    print(f"Run: docker compose --env-file {output_path} config")
    print("Then: docker compose up -d --wait")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
