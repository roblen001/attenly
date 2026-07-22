"""Smoke test SQLAlchemy-backed usage limits.

This does not call Supabase, Gemini, OpenAI-compatible endpoints, Resend,
Microsoft Graph, Redis, or a persistent database. It creates a temporary
SQLite file, initializes the SQLAlchemy tables, and exercises CreditService.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"


def configure_env(data_dir: Path) -> None:
    db_path = data_dir / "usage-limits.db"
    os.environ.update(
        {
            "APP_PROFILE": "local",
            "AUTH_PROVIDER": "local",
            "LOCAL_AUTH_TOKEN": "usage-smoke-token",
            "LOCAL_AUTH_USER_ID": "usage-smoke-user",
            "LOCAL_AUTH_EMAIL": "usage-smoke@example.com",
            "DATABASE_PROVIDER": "sqlalchemy",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "DATABASE_AUTO_CREATE_TABLES": "true",
            "STORAGE_PROVIDER": "filesystem",
            "STORAGE_PATH": (data_dir / "storage").as_posix(),
            "LLM_PROVIDER": "gemini",
            "EMBEDDING_PROVIDER": "gemini",
            "GEMINI_API_KEY": "fake-gemini-key",
            "TEMPLATE_INGEST_PROVIDER": "disabled",
            "OUTBOUND_EMAIL_PROVIDER": "none",
            "INBOUND_EMAIL_PROVIDER": "none",
            "DEFAULT_MONTHLY_LIMIT_CAD": "0.01",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )


def assert_equal(label: str, value, expected) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="attenly-usage-limits-") as temp_dir:
        data_dir = Path(temp_dir)
        configure_env(data_dir)
        sys.path.insert(0, str(BACKEND_ROOT))

        from app.db import Base, SessionLocal, engine
        from app.models import UserQuota

        import app.models  # noqa: F401 - registers SQLAlchemy models with Base
        from app.services.credit_service import CreditService

        Base.metadata.create_all(bind=engine)

        service = CreditService()
        user_id = "local-user"

        before = service.check_credits_sync(user_id)
        assert_equal("initial warning level", before.warning_level, "normal")
        assert_equal("initial used credits", before.credits_used, 0)

        first = service.consume_credits_sync(
            user_id=user_id,
            cost_cad=0.004,
            operation_type="llm_extraction",
            model="local-model",
            input_tokens=1000,
            output_tokens=100,
        )
        assert_equal("first charge allowed", first.allowed, True)

        second = service.consume_credits_sync(
            user_id=user_id,
            cost_cad=0.007,
            operation_type="llm_extraction",
            model="local-model",
            input_tokens=1000,
            output_tokens=100,
        )
        assert_equal("over-limit charge allowed", second.allowed, False)

        blocked = service.check_credits_sync(user_id)
        assert_equal("blocked warning level", blocked.warning_level, "blocked")

        summary = service._sqlalchemy_usage_summary(user_id, days=30)
        history = service._sqlalchemy_usage_history(user_id, days=30)
        assert_equal("usage summary rows", len(summary), 1)
        assert_equal("usage history rows", len(history), 1)
        assert_equal("usage request count", summary[0].request_count, 2)

        with SessionLocal() as session:
            quota = session.query(UserQuota).filter(UserQuota.user_id == user_id).one()
            quota.monthly_limit_cad = 0.02
            session.commit()

        unblocked = service.check_credits_sync(user_id)
        assert_equal("admin limit update warning level", unblocked.warning_level, "normal")

        engine.dispose()

    print("SQLAlchemy usage limit smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
