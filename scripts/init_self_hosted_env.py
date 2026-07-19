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
DEFAULT_EMBEDDING_DIMENSIONS = "1536"
EMAIL_PROVIDER_CHOICES = ("none", "microsoft_graph", "resend")


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
        if args.internal_cron_secret:
            updates["INTERNAL_CRON_SECRET"] = args.internal_cron_secret
        else:
            updates["INTERNAL_CRON_SECRET"] = secrets.token_urlsafe(32)
            generated_internal_cron_secret = True

    uses_resend = outbound_email_provider == "resend" or inbound_email_provider == "resend"
    if uses_resend:
        updates["RESEND_API_KEY"] = prompt_value("RESEND_API_KEY", args.resend_api_key)

    if inbound_email_provider == "resend":
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
        "--model-base-url",
        help=f"OpenAI-compatible base URL. Defaults to {DEFAULT_MODEL_BASE_URL}.",
    )
    parser.add_argument("--model-api-key", default="", help="Optional model gateway API key.")
    parser.add_argument("--llm-model", help="Chat/completions model served by the gateway.")
    parser.add_argument("--embedding-model", help="Embedding model served by the gateway.")
    parser.add_argument(
        "--embedding-dimensions",
        default=DEFAULT_EMBEDDING_DIMENSIONS,
        help="Embedding vector dimensions. Defaults to 1536.",
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
    parser.add_argument("--resend-api-key", help="Resend API key.")
    parser.add_argument("--resend-webhook-secret", help="Resend inbound webhook secret.")
    args = parser.parse_args()
    generated_local_auth_token = args.local_auth_token is None
    outbound_email_provider, inbound_email_provider = selected_email_providers(args)

    template_path = Path(args.template)
    output_path = Path(args.output)
    if not template_path.exists():
        raise SystemExit(f"{template_path} does not exist.")

    updates = {
        "ATTENLY_FRONTEND_PORT": args.frontend_port,
        "AUTH_PROVIDER": "local",
        "LOCAL_AUTH_TOKEN": args.local_auth_token or secrets.token_urlsafe(32),
        "LLM_PROVIDER": "openai_compatible",
        "EMBEDDING_PROVIDER": "openai_compatible",
        "OPENAI_COMPATIBLE_BASE_URL": prompt_value(
            "OPENAI_COMPATIBLE_BASE_URL",
            args.model_base_url,
            DEFAULT_MODEL_BASE_URL,
        ),
        "OPENAI_COMPATIBLE_API_KEY": args.model_api_key,
        "LLM_MODEL": prompt_value("LLM_MODEL", args.llm_model),
        "EMBEDDING_MODEL": prompt_value("EMBEDDING_MODEL", args.embedding_model),
        "EMBEDDING_DIMENSIONS": args.embedding_dimensions,
        "TEMPLATE_INGEST_PROVIDER": "disabled",
    }
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
    if generated_internal_cron_secret:
        print("INTERNAL_CRON_SECRET was generated and written to the file.")
    print(f"Run: docker compose --env-file {output_path} config")
    print("Then: docker compose up -d --wait")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
