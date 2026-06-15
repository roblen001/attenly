"""Smoke test Microsoft Graph inbound polling without network calls."""

from __future__ import annotations

import base64
import os
import sys
import tempfile
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"


def configure_env(data_dir: Path) -> None:
    db_path = data_dir / "graph-inbound.db"
    os.environ.update(
        {
            "APP_PROFILE": "enterprise",
            "AUTH_PROVIDER": "local",
            "LOCAL_AUTH_TOKEN": "graph-smoke-token",
            "DATABASE_PROVIDER": "sqlalchemy",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "DATABASE_AUTO_CREATE_TABLES": "true",
            "STORAGE_PROVIDER": "filesystem",
            "STORAGE_PATH": (data_dir / "storage").as_posix(),
            "LLM_PROVIDER": "openai_compatible",
            "EMBEDDING_PROVIDER": "openai_compatible",
            "OPENAI_COMPATIBLE_BASE_URL": "https://models.example.test/v1",
            "TEMPLATE_INGEST_PROVIDER": "disabled",
            "OUTBOUND_EMAIL_PROVIDER": "none",
            "INBOUND_EMAIL_PROVIDER": "microsoft_graph",
            "GRAPH_TENANT_ID": "tenant",
            "GRAPH_CLIENT_ID": "client",
            "GRAPH_CLIENT_SECRET": "secret",
            "GRAPH_MAILBOX": "attenly@example.com",
            "EMAIL_INGEST_DOMAIN": "mail.example.test",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )


def assert_equal(label: str, value, expected) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {value!r}")


class FakeCreditService:
    def check_credits_sync(self, user_id: str):
        class Status:
            warning_level = "normal"

        return Status()


class FakeGraphClient:
    def __init__(self):
        self.attachment_reads = 0

    def is_configured(self) -> bool:
        return True

    def list_messages_since(self, since, *, top: int):
        return [
            {
                "id": "graph-message-1",
                "internetMessageId": "<message-1@example.com>",
                "subject": "Graph smoke",
                "receivedDateTime": "2026-06-15T12:00:00Z",
                "from": {"emailAddress": {"address": "sender@example.com"}},
                "toRecipients": [
                    {"emailAddress": {"address": "u_graphsmoke@mail.example.test"}}
                ],
                "ccRecipients": [],
                "body": {"content": "Please process this attachment."},
                "hasAttachments": True,
            }
        ]

    def list_message_attachments(self, message_id: str):
        self.attachment_reads += 1
        return [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "attachment-1",
                "name": "smoke.pdf",
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(b"fake-pdf-content").decode("ascii"),
                "size": len(b"fake-pdf-content"),
                "isInline": False,
            }
        ]


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="attenly-graph-inbound-",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        data_dir = Path(temp_dir)
        configure_env(data_dir)
        sys.path.insert(0, str(BACKEND_ROOT))

        from app.db import Base, SessionLocal, engine
        from app.models import EmailIngestEndpoint, EmailJob, VerifiedSender
        from app.services.email_intake_service import EmailIntakeService
        from app.services.email_job_store import get_email_job_store
        from app.services.filesystem_storage_service import get_filesystem_storage_service
        from app.services.microsoft_graph_inbound_service import MicrosoftGraphInboundPoller

        import app.models  # noqa: F401 - registers SQLAlchemy models with Base

        Base.metadata.create_all(bind=engine)

        endpoint_id = uuid.uuid4()
        with SessionLocal() as session:
            session.add(
                EmailIngestEndpoint(
                    id=endpoint_id,
                    user_id="graph-user",
                    local_part="u_graphsmoke",
                    domain="mail.example.test",
                    full_address="u_graphsmoke@mail.example.test",
                    is_active=True,
                    default_agent_id="due-diligence",
                )
            )
            session.add(
                VerifiedSender(
                    user_id="graph-user",
                    email="sender@example.com",
                    status="verified",
                )
            )
            session.commit()

        job_store = get_email_job_store()
        graph_client = FakeGraphClient()
        intake_service = EmailIntakeService(
            job_store=job_store,
            storage_service=get_filesystem_storage_service(),
            credit_service=FakeCreditService(),
        )
        poller = MicrosoftGraphInboundPoller(
            graph_client=graph_client,
            intake_service=intake_service,
            job_store=job_store,
        )

        summary = poller.poll_messages(max_messages=10)
        assert_equal("messages seen", summary["messages_seen"], 1)
        assert_equal("accepted", summary["accepted"], 1)
        assert_equal("errors", summary["errors"], 0)

        provider_message_id = "microsoft_graph:<message-1@example.com>"
        job = job_store.get_job_by_provider_message_id(provider_message_id)
        assert job is not None
        assert_equal("job status", job["status"], "pending")
        assert_equal("job user", job["user_id"], "graph-user")

        with SessionLocal() as session:
            job_row = (
                session.query(EmailJob)
                .filter(EmailJob.provider_message_id == provider_message_id)
                .one()
            )
            attachments = job_row.raw_metadata["attachments"]
            assert_equal("stored attachment count", len(attachments), 1)
            storage_path = attachments[0]["storage_path"]
            stored_file = data_dir / "storage" / storage_path
            if not stored_file.exists():
                raise AssertionError(f"stored attachment missing: {stored_file}")

        state = job_store.get_poll_state("microsoft_graph", "attenly@example.com", "default")
        assert state is not None
        assert_equal("poll state last message", state["last_message_id"], "graph-message-1")

        duplicate_summary = poller.poll_messages(max_messages=10)
        assert_equal("duplicate messages seen", duplicate_summary["messages_seen"], 1)
        assert_equal("duplicate count", duplicate_summary["duplicates"], 1)
        assert_equal("duplicate attachment reads", graph_client.attachment_reads, 1)

        engine.dispose()

    print("Microsoft Graph inbound smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
