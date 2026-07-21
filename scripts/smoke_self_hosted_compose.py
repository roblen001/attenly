"""Smoke test the published-image self-hosted Docker Compose path.

This script intentionally uses only the Python standard library. It creates a
temporary env file with local auth, starts the published-image Compose stack,
checks frontend/backend/email-worker health, verifies Docker volume persistence
across container recreation, and then removes the disposable stack and volume.

It does not call the configured model endpoint, Microsoft Graph, Resend, or any
external API. Use it to prove that the Docker packaging boots correctly before
testing a real report-generation flow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_BASE_URL = "http://host.docker.internal:9/v1"
DEFAULT_FRONTEND_PORT = "5174"


def run(
    args: Iterable[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(result.args)
            + f"\n\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def compose_args(env_path: Path, project_name: str, *command: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "-p",
        project_name,
        *command,
    ]


def compose_env(env_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["ATTENLY_ENV_FILE"] = str(env_path)
    return env


def generate_env(args: argparse.Namespace, env_path: Path) -> None:
    run(
        [
            sys.executable,
            "scripts/init_self_hosted_env.py",
            "--output",
            str(env_path),
            "--frontend-port",
            args.frontend_port,
            "--llm-model",
            args.llm_model,
            "--embedding-model",
            args.embedding_model,
            "--model-base-url",
            args.model_base_url,
        ]
    )
    run([sys.executable, "scripts/check_self_hosted_env.py", str(env_path)])


def request_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def request_json(url: str) -> dict[str, object]:
    return json.loads(request_text(url))


def assert_equal(label: str, value: object, expected: object) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


def check_http(frontend_port: str) -> None:
    frontend_base_url = f"http://localhost:{frontend_port}/"
    frontend_health = request_text(
        urllib.parse.urljoin(frontend_base_url, "health")
    ).strip()
    assert_equal("frontend /health", frontend_health, "ok")

    ready = request_json(urllib.parse.urljoin(frontend_base_url, "api/ready"))
    assert_equal("backend /api/ready status", ready["status"], "healthy")
    checks = ready["checks"]  # type: ignore[index]
    assert_equal("database check", checks["database"]["status"], "healthy")  # type: ignore[index]
    assert_equal("storage check", checks["storage"]["status"], "healthy")  # type: ignore[index]
    assert_equal(
        "configuration check",
        checks["configuration"]["status"],  # type: ignore[index]
        "healthy",
    )

    index_html = request_text(frontend_base_url)
    script_paths = re.findall(r'<script[^>]+src="([^"]+\.js)"', index_html)
    if not script_paths:
        raise AssertionError("frontend index did not reference a JavaScript bundle")

    worker_path = None
    for script_path in script_paths:
        script_text = request_text(urllib.parse.urljoin(frontend_base_url, script_path))
        worker_match = re.search(
            r"assets/pdf\.worker\.min-[A-Za-z0-9_-]+\.mjs",
            script_text,
        )
        if worker_match:
            worker_path = worker_match.group(0)
            break

    if not worker_path:
        raise AssertionError("frontend bundle did not reference the PDF.js worker")

    worker_url = urllib.parse.urljoin(frontend_base_url, worker_path)
    with urllib.request.urlopen(worker_url, timeout=10) as response:
        worker_content_type = response.headers.get_content_type()
    assert_equal(
        "PDF.js worker Content-Type",
        worker_content_type,
        "application/javascript",
    )


def check_persistence(env_path: Path, project_name: str, command_env: dict[str, str]) -> None:
    run(
        compose_args(
            env_path,
            project_name,
            "exec",
            "-T",
            "backend",
            "sh",
            "-c",
            (
                "mkdir -p /data/storage && "
                "echo ok > /data/storage/persistence-smoke.txt && "
                "test -f /data/attenly.db && "
                "test -f /data/storage/persistence-smoke.txt"
            ),
        ),
        env=command_env,
    )

    run(compose_args(env_path, project_name, "down"), env=command_env)
    run(compose_args(env_path, project_name, "up", "-d", "--wait"), env=command_env)

    result = run(
        compose_args(
            env_path,
            project_name,
            "exec",
            "-T",
            "backend",
            "sh",
            "-c",
            (
                "test -f /data/attenly.db && "
                "test -f /data/storage/persistence-smoke.txt && "
                "cat /data/storage/persistence-smoke.txt"
            ),
        ),
        env=command_env,
    )
    assert_equal("persistence marker", result.stdout.strip(), "ok")


def print_failure_context(env_path: Path, project_name: str, command_env: dict[str, str]) -> None:
    for command in (("ps",), ("logs", "--no-color", "--tail", "200")):
        result = run(
            compose_args(env_path, project_name, *command),
            env=command_env,
            check=False,
        )
        print(f"\n$ docker compose {' '.join(command)}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default="attenly-smoke")
    parser.add_argument(
        "--frontend-port",
        default=DEFAULT_FRONTEND_PORT,
        help="Host port for the disposable frontend. Defaults to 5174.",
    )
    parser.add_argument("--llm-model", default="smoke-chat-model")
    parser.add_argument("--embedding-model", default="smoke-embedding-model")
    parser.add_argument(
        "--model-base-url",
        default=DEFAULT_MODEL_BASE_URL,
        help=(
            "OpenAI-compatible base URL. The smoke test does not call this "
            "endpoint, so the default intentionally points at a closed port."
        ),
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix=".attenly-compose-smoke-", dir=REPO_ROOT) as temp_dir:
        env_path = Path(temp_dir) / "smoke.env"
        command_env = compose_env(env_path)
        try:
            print(f"Generating temporary env file at {env_path}")
            generate_env(args, env_path)

            print("Rendering Compose config")
            run(compose_args(env_path, args.project_name, "config"), env=command_env)

            print("Starting published-image Compose stack")
            run(compose_args(env_path, args.project_name, "up", "-d", "--wait"), env=command_env)

            print("Checking frontend, backend, and email-worker health")
            check_http(args.frontend_port)

            print("Verifying Docker volume persistence across container recreation")
            check_persistence(env_path, args.project_name, command_env)
            check_http(args.frontend_port)

            print("Self-hosted Compose smoke test passed.")
            return 0
        except Exception as exc:
            print(f"Self-hosted Compose smoke test failed: {exc}", file=sys.stderr)
            print_failure_context(env_path, args.project_name, command_env)
            return 1
        finally:
            print("Cleaning up disposable Compose stack and volume")
            run(
                compose_args(env_path, args.project_name, "down", "-v"),
                env=command_env,
                check=False,
            )


if __name__ == "__main__":
    raise SystemExit(main())
