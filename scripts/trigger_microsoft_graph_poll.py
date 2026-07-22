"""Trigger one local Microsoft Graph polling cycle through Attenly.

In the Docker self-hosted profile, accepted jobs are processed by the
email-worker service. Legacy deployments with EMAIL_JOB_EXECUTION_MODE=inline
can still process jobs through the same route.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
from urllib import error, parse, request

from check_self_hosted_env import parse_env


def validated_api_url(value: str) -> str:
    """Require HTTPS unless the API endpoint is on the local loopback host."""
    api_url = value.strip().rstrip("/")
    parsed = parse.urlsplit(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("API URL must be an absolute http:// or https:// URL.")

    if parsed.username is not None or parsed.password is not None:
        raise SystemExit("API URL must not contain embedded credentials.")
    if parsed.query or parsed.fragment:
        raise SystemExit("API URL must not contain a query string or fragment.")

    hostname = parsed.hostname.lower().rstrip(".")
    is_loopback = hostname == "localhost" or hostname.endswith(".localhost")
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False

    if parsed.scheme != "https" and not is_loopback:
        raise SystemExit(
            "Refusing to send INTERNAL_CRON_SECRET over plain HTTP to a "
            "non-loopback host. Use HTTPS or a localhost API URL."
        )
    return api_url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", default=".env")
    parser.add_argument(
        "--api-url",
        help="Browser-reachable API base. Defaults to PUBLIC_API_URL from the env file.",
    )
    parser.add_argument(
        "--poll-only",
        action="store_true",
        help="Poll the mailbox through the poll-only route.",
    )
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        raise SystemExit(f"{path} does not exist.")
    env = parse_env(path)
    secret = env.get("INTERNAL_CRON_SECRET", "").strip()
    if not secret:
        raise SystemExit("INTERNAL_CRON_SECRET is missing from the env file.")

    api_url = validated_api_url(
        args.api_url
        or env.get("PUBLIC_API_URL")
        or "http://localhost:5173/api"
    )
    route = "/internal/poll-inbound-email" if args.poll_only else "/internal/process-email-jobs"
    url = f"{api_url}{route}"
    poll_request = request.Request(
        url,
        data=b"",
        headers={
            "Accept": "application/json",
            "X-Cron-Secret": secret,
        },
        method="POST",
    )

    try:
        with request.urlopen(poll_request, timeout=600) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"FAIL HTTP {exc.code} from {url}")
        print(body[:2000])
        return 1
    except error.URLError as exc:
        print(f"FAIL could not reach {url}: {exc.reason}")
        return 1

    print(f"HTTP {status} from {url}")
    try:
        print(json.dumps(json.loads(body), indent=2))
    except json.JSONDecodeError:
        print(body[:2000])
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
