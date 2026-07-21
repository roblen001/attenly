"""Trigger one local Microsoft Graph poll-and-process cycle through Attenly."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import error, request

from check_self_hosted_env import parse_env


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
        help="Poll the mailbox without processing accepted jobs.",
    )
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        raise SystemExit(f"{path} does not exist.")
    env = parse_env(path)
    secret = env.get("INTERNAL_CRON_SECRET", "").strip()
    if not secret:
        raise SystemExit("INTERNAL_CRON_SECRET is missing from the env file.")

    api_url = (
        args.api_url
        or env.get("PUBLIC_API_URL")
        or "http://localhost:5173/api"
    ).rstrip("/")
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
