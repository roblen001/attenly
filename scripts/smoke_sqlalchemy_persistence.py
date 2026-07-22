"""Smoke test SQLAlchemy-backed app persistence.

This does not call Supabase, Gemini, OpenAI-compatible endpoints, Resend,
Microsoft Graph, Redis, FastAPI, or a persistent database. It creates a
temporary SQLite file and filesystem storage root, then exercises the core
custom-agent and saved-report persistence surface used by the app routes.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"


def configure_env(data_dir: Path) -> None:
    db_path = data_dir / "persistence.db"
    os.environ.update(
        {
            "APP_PROFILE": "enterprise",
            "AUTH_PROVIDER": "local",
            "LOCAL_AUTH_TOKEN": "persistence-smoke-token",
            "LOCAL_AUTH_USER_ID": "persistence-smoke-user",
            "LOCAL_AUTH_EMAIL": "persistence-smoke@example.com",
            "DATABASE_PROVIDER": "sqlalchemy",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "DATABASE_AUTO_CREATE_TABLES": "true",
            "STORAGE_PROVIDER": "filesystem",
            "STORAGE_PATH": (data_dir / "storage").as_posix(),
            "LLM_PROVIDER": "openai_compatible",
            "EMBEDDING_PROVIDER": "openai_compatible",
            "OPENAI_COMPATIBLE_BASE_URL": "https://models.example.test/v1",
            "OPENAI_COMPATIBLE_API_KEY": "fake-model-token",
            "TEMPLATE_INGEST_PROVIDER": "disabled",
            "OUTBOUND_EMAIL_PROVIDER": "none",
            "INBOUND_EMAIL_PROVIDER": "none",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )


def assert_equal(label: str, value, expected) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="attenly-persistence-") as temp_dir:
        data_dir = Path(temp_dir)
        configure_env(data_dir)
        sys.path.insert(0, str(BACKEND_ROOT))

        from app.db import Base, engine

        import app.models  # noqa: F401 - registers SQLAlchemy models with Base
        from app.services.sqlalchemy_persistence_service import SqlAlchemyPersistenceService

        Base.metadata.create_all(bind=engine)

        service = SqlAlchemyPersistenceService()
        user_id = "local-user"
        token = ""

        agent_id = service.create_custom_agent(
            user_jwt=token,
            user_id=user_id,
            created_by_name="Smoke User",
            name="Persistence Smoke Agent",
            description="Custom agent smoke test",
            report_template="<html><body><p>{{summary}}</p></body></html>",
            report_template_css="body { font-family: sans-serif; }",
            questions=[
                {
                    "placeholder": "summary",
                    "prompt": "Summarize the uploaded documents.",
                }
            ],
        )

        created_agent = service.get_agent_by_id(token, user_id, agent_id)
        assert created_agent is not None
        assert_equal("created agent name", created_agent["name"], "Persistence Smoke Agent")
        assert_equal("created agent question count", len(created_agent["agent_questions"]), 1)

        custom_agents = service.get_user_custom_agents(token, user_id)
        if agent_id not in {agent["id"] for agent in custom_agents}:
            raise AssertionError("created custom agent not returned by SQLAlchemy list")

        updated = service.update_custom_agent(
            user_jwt=token,
            user_id=user_id,
            agent_id=agent_id,
            name="Persistence Smoke Agent Updated",
        )
        assert_equal("agent update", updated, True)
        updated_agent = service.get_agent_by_id(token, user_id, agent_id)
        assert updated_agent is not None
        assert_equal(
            "updated agent name",
            updated_agent["name"],
            "Persistence Smoke Agent Updated",
        )

        generated_at = datetime.now(timezone.utc).isoformat()
        report_id = service.save_report(
            user_jwt=token,
            user_id=user_id,
            agent_id=agent_id,
            agent_name=updated_agent["name"],
            report_name="Persistence Smoke Report",
            report_data={
                "generated_at": generated_at,
                "answers": {
                    "summary": {
                        "answer": "<p>Initial answer</p>",
                        "quotes": [],
                    }
                },
            },
            document_contents={
                "doc-1": {
                    "filename": "source.pdf",
                    "metadata": {"pages": 1},
                }
            },
            pdf_binaries={"doc-1": b"%PDF-1.4\n% persistence smoke\n"},
            cached_ai_baseline={"summary": "<p>Initial answer</p>"},
        )

        reports = service.get_user_reports(token, user_id)
        if report_id not in {report["id"] for report in reports}:
            raise AssertionError("saved report not returned by SQLAlchemy list")

        saved_report = service.get_saved_report(token, user_id, report_id)
        assert saved_report is not None
        assert_equal("saved report name", saved_report["report_name"], "Persistence Smoke Report")

        documents = service.get_saved_report_documents(token, user_id, report_id)
        assert_equal("saved report document count", len(documents), 1)
        assert_equal("saved report document filename", documents[0]["filename"], "source.pdf")

        pdf_bytes = service.download_saved_document_pdf(token, user_id, report_id, "doc-1")
        assert_equal("downloaded pdf bytes", pdf_bytes, b"%PDF-1.4\n% persistence smoke\n")

        renamed = service.update_saved_report(
            user_jwt=token,
            user_id=user_id,
            report_id=report_id,
            report_name="Persistence Smoke Report Updated",
        )
        assert_equal("saved report rename", renamed, True)
        saved_report = service.get_saved_report(token, user_id, report_id)
        assert saved_report is not None
        assert_equal(
            "renamed saved report",
            saved_report["report_name"],
            "Persistence Smoke Report Updated",
        )

        assert_equal(
            "delete saved report",
            service.delete_saved_report(token, user_id, report_id),
            True,
        )
        assert_equal("deleted report lookup", service.get_saved_report(token, user_id, report_id), None)

        assert_equal(
            "delete custom agent",
            service.delete_custom_agent(token, user_id, agent_id),
            True,
        )
        assert_equal("deleted agent lookup", service.get_agent_by_id(token, user_id, agent_id), None)

        engine.dispose()

    print("SQLAlchemy persistence smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
