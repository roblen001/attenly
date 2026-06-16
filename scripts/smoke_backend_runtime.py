"""Smoke test backend runtime routes for no-Supabase open-source profiles.

This script starts the real FastAPI application with local auth, SQLite, and
filesystem storage. It then checks /health, /ready, template capability, and
email-ingest settings routes over HTTP.

It does not call Supabase, Gemini, OpenAI-compatible model endpoints, Microsoft
Graph, Resend, or Redis. It does require backend runtime dependencies to be
installed, or it can be run inside the backend Docker image.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
AUTH_TOKEN = "smoke-local-token"


@dataclass(frozen=True)
class SmokeCase:
    name: str
    env: dict[str, str]
    expected_template_provider: str
    expected_template_enabled: bool


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def backend_env(case_env: dict[str, str], data_dir: Path) -> dict[str, str]:
    db_path = data_dir / "attenly-smoke.db"
    storage_path = data_dir / "storage"
    storage_path.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "ENV": "development",
            "PORT": "0",
            "APP_URL": "http://localhost:5173",
            "API_URL": "http://127.0.0.1",
            "CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
            "AUTH_PROVIDER": "local",
            "LOCAL_AUTH_TOKEN": AUTH_TOKEN,
            "LOCAL_AUTH_USER_ID": "smoke-user",
            "LOCAL_AUTH_EMAIL": "smoke@example.com",
            "LOCAL_AUTH_DISPLAY_NAME": "Smoke User",
            "DATABASE_PROVIDER": "sqlalchemy",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "STORAGE_PROVIDER": "filesystem",
            "STORAGE_PATH": storage_path.as_posix(),
            "OUTBOUND_EMAIL_PROVIDER": "none",
            "INBOUND_EMAIL_PROVIDER": "none",
            "PYTHONPATH": str(BACKEND_ROOT),
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )
    env.update(case_env)
    return env


def dependency_check(env: dict[str, str]) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import fastapi, sqlalchemy, slowapi, uvicorn",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return

    raise RuntimeError(
        "Backend runtime dependencies are not installed for this Python. "
        "Run `pip install -r backend/requirements.txt`, activate the backend "
        "environment, or run this script inside the backend Docker image.\n\n"
        f"STDERR:\n{result.stderr}"
    )


def start_backend(port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: Any | None = None,
    timeout: float = 5.0,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8")

    return status, json.loads(body)


def wait_for_health(process: subprocess.Popen[str], base_url: str) -> None:
    deadline = time.time() + 30
    last_error: Exception | None = None

    while time.time() < deadline:
        if process.poll() is not None:
            _, stderr = process.communicate(timeout=2)
            raise RuntimeError(f"Backend exited before /health was ready:\n{stderr}")

        try:
            status, payload = request_json(base_url, "/health", timeout=1)
            if status == 200 and payload.get("status") == "healthy":
                return
        except Exception as exc:
            last_error = exc

        time.sleep(0.25)

    raise RuntimeError(f"Timed out waiting for /health. Last error: {last_error}")


def assert_equal(label: str, value: Any, expected: Any) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


def run_case(case: SmokeCase) -> None:
    with tempfile.TemporaryDirectory(prefix=f"attenly-{case.name}-") as temp_dir:
        data_dir = Path(temp_dir)
        env = backend_env(case.env, data_dir)
        dependency_check(env)

        port = find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_backend(port, env)
        try:
            wait_for_health(process, base_url)

            ready_status, ready = request_json(base_url, "/ready")
            assert_equal(f"{case.name} /ready status", ready_status, 200)
            assert_equal(f"{case.name} ready overall", ready["status"], "healthy")
            assert_equal(
                f"{case.name} ready database",
                ready["checks"]["database"]["status"],
                "healthy",
            )
            assert_equal(
                f"{case.name} ready configuration",
                ready["checks"]["configuration"]["status"],
                "healthy",
            )

            template_status, template = request_json(
                base_url,
                "/agents/template/capabilities",
                token=AUTH_TOKEN,
            )
            assert_equal(f"{case.name} template status", template_status, 200)
            assert_equal(
                f"{case.name} template provider",
                template["provider"],
                case.expected_template_provider,
            )
            assert_equal(
                f"{case.name} template enabled",
                template["enabled"],
                case.expected_template_enabled,
            )

            email_status, email = request_json(
                base_url,
                "/email-ingest/settings",
                token=AUTH_TOKEN,
            )
            assert_equal(f"{case.name} email settings status", email_status, 200)
            assert_equal(f"{case.name} email enabled", email["enabled_by_config"], False)
            assert_equal(f"{case.name} email provider", email["provider"], "none")

            auth_status, auth_user = request_json(
                base_url,
                "/auth/api/auth/me",
                token=AUTH_TOKEN,
            )
            assert_equal(f"{case.name} auth me status", auth_status, 200)
            assert_equal(f"{case.name} auth user id", auth_user["id"], "smoke-user")

            agent_payload = {
                "name": f"{case.name} Custom Agent",
                "description": "Smoke test custom agent",
                "report_template": "<html><body><p>{{summary}}</p></body></html>",
                "report_template_css": "body { font-family: sans-serif; }",
                "questions": [
                    {
                        "id": "summary",
                        "placeholder": "summary",
                        "prompt": "Summarize the uploaded documents.",
                    }
                ],
            }
            create_status, created_agent = request_json(
                base_url,
                "/agents/create_custom_agent",
                method="POST",
                token=AUTH_TOKEN,
                payload=agent_payload,
            )
            assert_equal(f"{case.name} create custom agent status", create_status, 200)
            assert_equal(
                f"{case.name} created custom agent name",
                created_agent["name"],
                agent_payload["name"],
            )
            agent_id = created_agent["id"]

            list_status, custom_agents = request_json(
                base_url,
                "/agents/list_user_custom_agents",
                token=AUTH_TOKEN,
            )
            assert_equal(f"{case.name} list custom agents status", list_status, 200)
            if agent_id not in {agent["id"] for agent in custom_agents}:
                raise AssertionError(f"{case.name} created custom agent was not returned by list route")

            get_status, fetched_agent = request_json(
                base_url,
                f"/agents/{agent_id}",
                token=AUTH_TOKEN,
            )
            assert_equal(f"{case.name} get custom agent status", get_status, 200)
            assert_equal(f"{case.name} fetched custom agent id", fetched_agent["id"], agent_id)

            updated_name = f"{case.name} Custom Agent Updated"
            update_status, updated_agent = request_json(
                base_url,
                f"/agents/custom/{agent_id}",
                method="PUT",
                token=AUTH_TOKEN,
                payload={"name": updated_name},
            )
            assert_equal(f"{case.name} update custom agent status", update_status, 200)
            assert_equal(f"{case.name} updated custom agent name", updated_agent["name"], updated_name)

            delete_status, delete_result = request_json(
                base_url,
                f"/agents/custom/{agent_id}",
                method="DELETE",
                token=AUTH_TOKEN,
            )
            assert_equal(f"{case.name} delete custom agent status", delete_status, 200)
            assert_equal(f"{case.name} delete custom agent result", delete_result["success"], True)

            print(f"PASS {case.name}")
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)


def cases() -> list[SmokeCase]:
    return [
        SmokeCase(
            name="local_disabled_template",
            env={
                "APP_PROFILE": "local",
                "LLM_PROVIDER": "gemini",
                "EMBEDDING_PROVIDER": "gemini",
                "GEMINI_API_KEY": "fake-gemini-key",
                "TEMPLATE_INGEST_PROVIDER": "disabled",
            },
            expected_template_provider="disabled",
            expected_template_enabled=False,
        ),
        SmokeCase(
            name="enterprise_openai_template",
            env={
                "APP_PROFILE": "enterprise",
                "LLM_PROVIDER": "openai_compatible",
                "EMBEDDING_PROVIDER": "openai_compatible",
                "OPENAI_COMPATIBLE_BASE_URL": "https://models.company.internal/v1",
                "OPENAI_COMPATIBLE_API_KEY": "fake-model-token",
                "TEMPLATE_INGEST_PROVIDER": "openai_compatible",
                "TEMPLATE_INGEST_MODEL": "company-template-model",
            },
            expected_template_provider="openai_compatible",
            expected_template_enabled=True,
        ),
    ]


def main() -> int:
    try:
        for case in cases():
            run_case(case)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("All backend runtime smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
