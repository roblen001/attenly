"""Test live Microsoft Graph credentials, mailbox access, and permissions.

This uses only the Python standard library. By default it performs read-only
checks. Pass --send-test-to to send one real test email through the configured
mailbox and validate Mail.Send.
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from check_self_hosted_env import parse_env


TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_URL = "https://graph.microsoft.com/v1.0"


class GraphCheckError(RuntimeError):
    pass


def required(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise GraphCheckError(f"{key} is missing from the env file.")
    return value


def error_details(exc: error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:500] or exc.reason

    graph_error = payload.get("error", payload)
    if isinstance(graph_error, dict):
        code = graph_error.get("code") or graph_error.get("error")
        message = graph_error.get("message") or graph_error.get("error_description")
        return ": ".join(str(item) for item in (code, message) if item)[:500]
    return str(graph_error)[:500]


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    form: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    graph_request = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(graph_request, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raise GraphCheckError(f"HTTP {exc.code} from {url}: {error_details(exc)}") from None
    except error.URLError as exc:
        raise GraphCheckError(f"Could not reach {url}: {exc.reason}") from None

    if status not in expected_statuses:
        raise GraphCheckError(f"Unexpected HTTP {status} from {url}.")
    return status, json.loads(body) if body else {}


def token_roles(access_token: str) -> set[str]:
    try:
        payload_part = access_token.split(".")[1]
        padded = payload_part + "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return set(payload.get("roles") or [])
    except (IndexError, ValueError, json.JSONDecodeError):
        return set()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", default=".env")
    parser.add_argument(
        "--send-test-to",
        help="Send one real test message to this address after read checks pass.",
    )
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        raise SystemExit(f"{path} does not exist.")
    env = parse_env(path)

    try:
        tenant_id = required(env, "GRAPH_TENANT_ID")
        client_id = required(env, "GRAPH_CLIENT_ID")
        client_secret = required(env, "GRAPH_CLIENT_SECRET")
        mailbox = required(env, "GRAPH_MAILBOX")

        _, token_payload = request_json(
            TOKEN_URL.format(tenant_id=parse.quote(tenant_id, safe="")),
            method="POST",
            form={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        access_token = token_payload.get("access_token")
        if not access_token:
            raise GraphCheckError("Microsoft token response did not include access_token.")
        print("PASS token: Entra accepted the tenant, client ID, and client secret.")

        roles = token_roles(access_token)
        if roles:
            print("Token application roles: " + ", ".join(sorted(roles)))
        else:
            print("WARN token roles could not be read; the live API check remains authoritative.")

        mailbox_path = parse.quote(mailbox, safe="")
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace(
            "+00:00", "Z"
        )
        query = parse.urlencode(
            {
                "$select": (
                    "id,internetMessageId,subject,from,toRecipients,ccRecipients,"
                    "receivedDateTime,bodyPreview,body,hasAttachments"
                ),
                "$filter": f"receivedDateTime ge {since} and hasAttachments eq true",
                "$orderby": "receivedDateTime asc",
                "$top": "1",
            }
        )
        _, message_payload = request_json(
            f"{GRAPH_URL}/users/{mailbox_path}/messages?{query}",
            token=access_token,
        )
        messages = message_payload.get("value") or []
        message_count = len(messages)
        print(
            "PASS Mail.Read: Graph accepted Attenly's inbound mailbox query "
            f"({message_count} attachment-bearing message found in the last 24 hours)."
        )
        if messages:
            message_id = parse.quote(messages[0]["id"], safe="")
            _, attachment_payload = request_json(
                f"{GRAPH_URL}/users/{mailbox_path}/messages/{message_id}/attachments",
                token=access_token,
            )
            attachment_count = len(attachment_payload.get("value") or [])
            print(
                "PASS attachments: Graph returned "
                f"{attachment_count} attachment record(s) for the probe message."
            )

        if args.send_test_to:
            request_json(
                f"{GRAPH_URL}/users/{mailbox_path}/sendMail",
                method="POST",
                token=access_token,
                payload={
                    "message": {
                        "subject": "Attenly Microsoft Graph connection test",
                        "body": {
                            "contentType": "Text",
                            "content": "Attenly successfully sent this message through Microsoft Graph.",
                        },
                        "toRecipients": [
                            {"emailAddress": {"address": args.send_test_to}}
                        ],
                    },
                    "saveToSentItems": False,
                },
                expected_statuses=(202,),
            )
            print(f"PASS Mail.Send: Graph accepted a test email to {args.send_test_to}.")
        elif env.get("OUTBOUND_EMAIL_PROVIDER", "").lower() == "microsoft_graph":
            if "Mail.Send" in roles:
                print("PASS Mail.Send role: present in the application token.")
            else:
                print(
                    "WARN outbound Graph is enabled but Mail.Send was not found in the token. "
                    "Use --send-test-to to verify it with a real request."
                )

    except GraphCheckError as exc:
        print(f"FAIL {exc}")
        return 1

    print("Microsoft Graph connection preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
