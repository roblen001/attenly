"""Enable Microsoft Graph email without replacing existing model settings.

The command updates only Microsoft Graph/email values in an existing self-hosted
environment file. It intentionally prompts for the client secret by default so
the secret does not need to be stored in shell history.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
from pathlib import Path

from check_self_hosted_env import parse_env, validate
from init_self_hosted_env import update_env_lines


def required_value(name: str, value: str | None, *, secret: bool = False) -> str:
    if value:
        return value.strip()

    prompt = f"{name}: "
    entered = getpass.getpass(prompt) if secret else input(prompt)
    entered = entered.strip()
    if not entered:
        flag = "--" + name.lower().replace("_", "-")
        raise SystemExit(
            f"{name} is required. Pass it with {flag} or enter it when prompted."
        )
    return entered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", default=".env", help="Env file to update.")
    parser.add_argument(
        "--mode",
        choices=("both", "inbound", "outbound"),
        default="both",
        help="Enable both Graph directions or only one. Defaults to both.",
    )
    parser.add_argument("--graph-tenant-id", help="Microsoft Entra Directory (tenant) ID.")
    parser.add_argument("--graph-client-id", help="Microsoft Entra Application (client) ID.")
    parser.add_argument(
        "--graph-client-secret",
        help="Client secret value. Omit to enter it securely at the prompt.",
    )
    parser.add_argument("--graph-mailbox", help="Microsoft 365 mailbox Graph will poll/send as.")
    parser.add_argument(
        "--email-ingest-domain",
        help="Domain for generated Attenly aliases. Defaults to the mailbox domain.",
    )
    parser.add_argument("--graph-poll-batch-size", default="10")
    parser.add_argument("--graph-poll-lookback-seconds", default="300")
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Create it first with scripts/init_self_hosted_env.py."
        )

    current = parse_env(path)
    tenant_id = required_value("GRAPH_TENANT_ID", args.graph_tenant_id)
    client_id = required_value("GRAPH_CLIENT_ID", args.graph_client_id)
    client_secret = required_value(
        "GRAPH_CLIENT_SECRET",
        args.graph_client_secret,
        secret=True,
    )
    mailbox = required_value("GRAPH_MAILBOX", args.graph_mailbox).lower()
    if "@" not in mailbox:
        raise SystemExit("GRAPH_MAILBOX must be a complete email address.")

    ingest_domain = (args.email_ingest_domain or mailbox.rsplit("@", 1)[1]).lower()
    outbound_provider = "microsoft_graph" if args.mode in {"both", "outbound"} else "none"
    inbound_provider = "microsoft_graph" if args.mode in {"both", "inbound"} else "none"
    cron_secret = current.get("INTERNAL_CRON_SECRET") or secrets.token_urlsafe(32)

    updates = {
        "OUTBOUND_EMAIL_PROVIDER": outbound_provider,
        "INBOUND_EMAIL_PROVIDER": inbound_provider,
        "GRAPH_TENANT_ID": tenant_id,
        "GRAPH_CLIENT_ID": client_id,
        "GRAPH_CLIENT_SECRET": client_secret,
        "GRAPH_MAILBOX": mailbox,
        "GRAPH_POLL_BATCH_SIZE": args.graph_poll_batch_size,
        "GRAPH_POLL_LOOKBACK_SECONDS": args.graph_poll_lookback_seconds,
        "EMAIL_INGEST_DOMAIN": ingest_domain,
    }
    if inbound_provider == "microsoft_graph":
        updates["INTERNAL_CRON_SECRET"] = cron_secret
        updates["EMAIL_JOB_EXECUTION_MODE"] = "worker"
        updates["EMAIL_WORKER_POLL_INTERVAL_SECONDS"] = "30"
        updates["EMAIL_WORKER_MAX_JOBS_PER_CYCLE"] = "1"

    original_lines = path.read_text(encoding="utf-8").splitlines()
    updated_lines = update_env_lines(original_lines, updates)
    path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    errors, warnings = validate(parse_env(path))
    if errors:
        print(f"Updated {path}, but self-hosted preflight found errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Updated {path} without changing its model or authentication settings.")
    print(
        "Microsoft Graph email: "
        f"outbound={outbound_provider}, inbound={inbound_provider}."
    )
    print(f"Generated Attenly email aliases will use @{ingest_domain}.")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print(f"Next: python scripts/check_microsoft_graph_connection.py {path}")
    print("Then recreate the Compose stack so backend and email-worker load the updated env file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
