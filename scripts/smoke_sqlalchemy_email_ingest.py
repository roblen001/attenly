"""Smoke test SQLAlchemy-backed email ingest settings.

This does not call Supabase, Resend, Microsoft Graph, Gemini, OpenAI-compatible
endpoints, Redis, or a persistent database. It creates a temporary SQLite file
and exercises the email ingest settings data model directly.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"


def configure_env(data_dir: Path) -> None:
    db_path = data_dir / "email-ingest.db"
    os.environ.update(
        {
            "APP_PROFILE": "local",
            "AUTH_PROVIDER": "local",
            "LOCAL_AUTH_TOKEN": "email-smoke-token",
            "LOCAL_AUTH_USER_ID": "email-smoke-user",
            "LOCAL_AUTH_EMAIL": "email-smoke@example.com",
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
            "EMAIL_INGEST_DOMAIN": "mail.example.test",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )


def assert_equal(label: str, value, expected) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


class FakeEmailService:
    def send_verification_email(self, to: str, token: str, user_alias: str) -> bool:
        return True


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="attenly-email-ingest-",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        data_dir = Path(temp_dir)
        configure_env(data_dir)
        sys.path.insert(0, str(BACKEND_ROOT))

        from app.db import Base, SessionLocal, engine
        from app.models import EmailJob, EmailPollState, VerifiedSender

        import app.models  # noqa: F401 - registers SQLAlchemy models with Base
        from app.services import email_ingest_service as email_ingest_module
        from app.services.email_ingest_service import EmailIngestService
        from app.services.email_job_store import get_email_job_store

        email_ingest_module.email_service = FakeEmailService()

        Base.metadata.create_all(bind=engine)

        service = EmailIngestService()
        user_id = "local-user"

        enabled = service.enable_email_ingest("", user_id)
        assert_equal("email enabled", enabled["enabled"], True)
        if not enabled["email_alias"].endswith("@mail.example.test"):
            raise AssertionError(f"unexpected alias: {enabled['email_alias']}")

        settings = service.get_user_settings("", user_id)
        endpoint = settings["endpoint"]
        assert endpoint is not None
        assert_equal("endpoint active", endpoint["is_active"], True)
        assert_equal("initial sender count", len(settings["verified_senders"]), 0)

        sender = service.add_verified_sender("", user_id, "Sender@Example.com")
        assert_equal("sender normalized", sender["email"], "sender@example.com")
        assert_equal("sender pending", sender["status"], "pending")

        job_id = uuid.uuid4()

        with SessionLocal() as session:
            sender_row = (
                session.query(VerifiedSender)
                .filter(VerifiedSender.id == uuid.UUID(sender["id"]))
                .one()
            )
            token = sender_row.verification_token
            endpoint_id = uuid.UUID(endpoint["id"])

            session.add(
                EmailJob(
                    id=job_id,
                    user_id=user_id,
                    ingest_endpoint_id=endpoint_id,
                    from_email="sender@example.com",
                    subject="Smoke job",
                    status="pending",
                    provider_message_id="message-1",
                    raw_metadata={"attachments": []},
                )
            )
            session.add(
                EmailPollState(
                    provider="microsoft_graph",
                    mailbox="attenly@example.com",
                    state_key="inbox",
                    delta_link="https://graph.example/delta",
                )
            )
            session.commit()

        job_store = get_email_job_store()
        pending_jobs = job_store.list_pending_jobs(10)
        if str(job_id) not in {job["id"] for job in pending_jobs}:
            raise AssertionError("pending email job not returned by SQLAlchemy job store")
        assert_equal("claim job", job_store.claim_job(str(job_id)), True)
        assert_equal("claim job twice", job_store.claim_job(str(job_id)), False)
        claimed_job = job_store.get_job(str(job_id))
        assert claimed_job is not None
        assert_equal("claimed job status", claimed_job["status"], "processing")

        success, message = service.verify_sender(token)
        assert_equal("verify success", success, True)
        assert "verified" in message.lower()

        settings = service.get_user_settings("", user_id)
        assert_equal("verified sender count", len(settings["verified_senders"]), 1)
        assert_equal("sender verified", settings["verified_senders"][0]["is_verified"], True)
        assert_equal("jobs last 24h", settings["usage_summary"]["jobs_last_24h"], 1)

        assert_equal(
            "default agent update",
            service.update_default_agent("", user_id, "agent-123"),
            True,
        )
        settings = service.get_user_settings("", user_id)
        assert_equal("default agent", settings["endpoint"]["default_agent_id"], "agent-123")
        assert_equal(
            "job store default agent",
            job_store.get_endpoint_default_agent(settings["endpoint"]["id"]),
            "agent-123",
        )

        job_store.mark_completed(str(job_id), "report-123")
        completed_job = job_store.get_job(str(job_id))
        assert completed_job is not None
        assert_equal("completed job status", completed_job["status"], "completed")
        assert_equal("completed job report", completed_job["report_id"], "report-123")

        assert_equal("remove sender", service.remove_verified_sender("", user_id, sender["id"]), True)
        assert_equal("disable email ingest", service.disable_email_ingest("", user_id), True)
        settings = service.get_user_settings("", user_id)
        assert_equal("endpoint disabled", settings["endpoint"]["is_active"], False)

        engine.dispose()

    print("SQLAlchemy email ingest smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
