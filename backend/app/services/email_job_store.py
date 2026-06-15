"""Provider-specific persistence for email job processing.

The processor should not know whether email jobs live in Supabase tables or
SQLAlchemy tables. This module keeps that database-specific plumbing small and
lets the processing pipeline stay focused on documents, agents, and reports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from app import config

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _endpoint_to_dict(endpoint: Any) -> Dict[str, Any]:
    return {
        "id": str(endpoint.id),
        "user_id": endpoint.user_id,
        "local_part": endpoint.local_part,
        "domain": endpoint.domain,
        "full_address": endpoint.full_address,
        "is_active": endpoint.is_active,
        "default_agent_id": endpoint.default_agent_id,
        "created_at": _to_iso(endpoint.created_at),
        "updated_at": _to_iso(endpoint.updated_at),
    }


class SupabaseEmailJobStore:
    """Email job store backed by Supabase service-role operations."""

    def __init__(self):
        from app.services.supabase_service import supabase_service

        self.supabase_service = supabase_service

    def _client(self):
        from supabase import create_client

        return create_client(
            self.supabase_service.supabase_url,
            self.supabase_service.supabase_service_key,
        )

    def list_pending_jobs(self, max_jobs: int) -> List[Dict[str, Any]]:
        result = (
            self._client()
            .table("email_jobs")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(max_jobs)
            .execute()
        )
        return result.data or []

    def claim_job(self, job_id: str) -> bool:
        result = (
            self._client()
            .table("email_jobs")
            .update({"status": "processing", "updated_at": _now_iso()})
            .eq("id", job_id)
            .eq("status", "pending")
            .execute()
        )
        return bool(result.data)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        result = (
            self._client()
            .table("email_jobs")
            .select("*")
            .eq("id", job_id)
            .single()
            .execute()
        )
        return result.data

    def get_endpoint_default_agent(self, endpoint_id: str) -> Optional[str]:
        result = (
            self._client()
            .table("email_ingest_endpoints")
            .select("default_agent_id")
            .eq("id", endpoint_id)
            .single()
            .execute()
        )
        if not result.data:
            return None
        return result.data.get("default_agent_id")

    def get_job_by_provider_message_id(self, provider_message_id: str) -> Optional[Dict[str, Any]]:
        result = (
            self._client()
            .table("email_jobs")
            .select("*")
            .eq("provider_message_id", provider_message_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_endpoint_by_address(self, full_address: str) -> Optional[Dict[str, Any]]:
        result = (
            self._client()
            .table("email_ingest_endpoints")
            .select("*")
            .eq("full_address", full_address.lower())
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def is_verified_sender(self, user_id: str, email: str) -> bool:
        result = (
            self._client()
            .table("verified_senders")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("email", email.lower())
            .eq("status", "verified")
            .limit(1)
            .execute()
        )
        return bool(result.data)

    def create_job(self, job_data: Dict[str, Any]) -> str:
        insert_data = dict(job_data)
        if "id" not in insert_data:
            insert_data["id"] = str(uuid4())
        result = self._client().table("email_jobs").insert(insert_data).execute()
        if result.data:
            return str(result.data[0]["id"])
        return str(insert_data["id"])

    def get_poll_state(self, provider: str, mailbox: str, state_key: str) -> Optional[Dict[str, Any]]:
        result = (
            self._client()
            .table("email_poll_state")
            .select("*")
            .eq("provider", provider)
            .eq("mailbox", mailbox)
            .eq("state_key", state_key)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def save_poll_state(
        self,
        provider: str,
        mailbox: str,
        state_key: str,
        *,
        last_polled_at: datetime,
        last_message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = _now_iso()
        data = {
            "provider": provider,
            "mailbox": mailbox,
            "state_key": state_key,
            "last_message_id": last_message_id,
            "metadata": metadata or {},
            "last_polled_at": last_polled_at.isoformat(),
            "updated_at": now,
        }
        existing = self.get_poll_state(provider, mailbox, state_key)
        if existing:
            (
                self._client()
                .table("email_poll_state")
                .update(data)
                .eq("id", existing["id"])
                .execute()
            )
            return

        data["created_at"] = now
        self._client().table("email_poll_state").insert(data).execute()

    def mark_failed(self, job_id: str, error_message: str) -> None:
        (
            self._client()
            .table("email_jobs")
            .update(
                {
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            )
            .eq("id", job_id)
            .execute()
        )

    def mark_completed(self, job_id: str, report_id: str) -> None:
        (
            self._client()
            .table("email_jobs")
            .update(
                {
                    "report_id": report_id,
                    "status": "completed",
                    "completed_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            )
            .eq("id", job_id)
            .execute()
        )


class SqlAlchemyEmailJobStore:
    """Email job store backed by SQLAlchemy tables."""

    def _job_to_dict(self, job) -> Dict[str, Any]:
        return {
            "id": str(job.id),
            "user_id": job.user_id,
            "ingest_endpoint_id": str(job.ingest_endpoint_id),
            "from_email": job.from_email,
            "subject": job.subject,
            "instruction_text": job.instruction_text,
            "status": job.status,
            "report_id": job.report_id,
            "provider_message_id": job.provider_message_id,
            "raw_metadata": job.raw_metadata or {},
            "error_message": job.error_message,
            "attachment_count": job.attachment_count,
            "created_at": _to_iso(job.created_at),
            "updated_at": _to_iso(job.updated_at),
            "completed_at": _to_iso(job.completed_at),
        }

    def list_pending_jobs(self, max_jobs: int) -> List[Dict[str, Any]]:
        from app.db import SessionLocal
        from app.models import EmailJob

        with SessionLocal() as session:
            jobs = (
                session.query(EmailJob)
                .filter(EmailJob.status == "pending")
                .order_by(EmailJob.created_at.asc())
                .limit(max_jobs)
                .all()
            )
            return [self._job_to_dict(job) for job in jobs]

    def claim_job(self, job_id: str) -> bool:
        from app.db import SessionLocal
        from app.models import EmailJob

        with SessionLocal() as session:
            updated = (
                session.query(EmailJob)
                .filter(EmailJob.id == _to_uuid(job_id), EmailJob.status == "pending")
                .update(
                    {
                        "status": "processing",
                        "updated_at": datetime.now(timezone.utc),
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return updated == 1

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        from app.db import SessionLocal
        from app.models import EmailJob

        with SessionLocal() as session:
            job = session.query(EmailJob).filter(EmailJob.id == _to_uuid(job_id)).first()
            return self._job_to_dict(job) if job else None

    def get_endpoint_default_agent(self, endpoint_id: str) -> Optional[str]:
        from app.db import SessionLocal
        from app.models import EmailIngestEndpoint

        with SessionLocal() as session:
            endpoint = (
                session.query(EmailIngestEndpoint)
                .filter(EmailIngestEndpoint.id == _to_uuid(endpoint_id))
                .first()
            )
            return endpoint.default_agent_id if endpoint else None

    def get_job_by_provider_message_id(self, provider_message_id: str) -> Optional[Dict[str, Any]]:
        from app.db import SessionLocal
        from app.models import EmailJob

        with SessionLocal() as session:
            job = (
                session.query(EmailJob)
                .filter(EmailJob.provider_message_id == provider_message_id)
                .first()
            )
            return self._job_to_dict(job) if job else None

    def get_endpoint_by_address(self, full_address: str) -> Optional[Dict[str, Any]]:
        from app.db import SessionLocal
        from app.models import EmailIngestEndpoint

        with SessionLocal() as session:
            endpoint = (
                session.query(EmailIngestEndpoint)
                .filter(EmailIngestEndpoint.full_address == full_address.lower())
                .first()
            )
            return _endpoint_to_dict(endpoint) if endpoint else None

    def is_verified_sender(self, user_id: str, email: str) -> bool:
        from app.db import SessionLocal
        from app.models import VerifiedSender

        with SessionLocal() as session:
            sender = (
                session.query(VerifiedSender)
                .filter(
                    VerifiedSender.user_id == str(user_id),
                    VerifiedSender.email == email.lower(),
                    VerifiedSender.status == "verified",
                )
                .first()
            )
            return sender is not None

    def create_job(self, job_data: Dict[str, Any]) -> str:
        from app.db import SessionLocal
        from app.models import EmailJob

        insert_data = dict(job_data)
        job_id = _to_uuid(insert_data.get("id") or uuid4())
        with SessionLocal() as session:
            job = EmailJob(
                id=job_id,
                user_id=str(insert_data["user_id"]),
                ingest_endpoint_id=_to_uuid(insert_data["ingest_endpoint_id"]),
                from_email=insert_data["from_email"],
                subject=insert_data.get("subject"),
                instruction_text=insert_data.get("instruction_text"),
                status=insert_data.get("status", "pending"),
                report_id=insert_data.get("report_id"),
                provider_message_id=insert_data["provider_message_id"],
                raw_metadata=insert_data.get("raw_metadata") or {},
                error_message=insert_data.get("error_message"),
                attachment_count=insert_data.get("attachment_count", 0),
            )
            session.add(job)
            session.commit()
            return str(job.id)

    def get_poll_state(self, provider: str, mailbox: str, state_key: str) -> Optional[Dict[str, Any]]:
        from app.db import SessionLocal
        from app.models import EmailPollState

        with SessionLocal() as session:
            state = (
                session.query(EmailPollState)
                .filter(
                    EmailPollState.provider == provider,
                    EmailPollState.mailbox == mailbox,
                    EmailPollState.state_key == state_key,
                )
                .first()
            )
            if not state:
                return None
            return {
                "id": str(state.id),
                "provider": state.provider,
                "mailbox": state.mailbox,
                "state_key": state.state_key,
                "delta_link": state.delta_link,
                "last_message_id": state.last_message_id,
                "metadata": state.metadata_json or {},
                "last_polled_at": _to_iso(state.last_polled_at),
                "created_at": _to_iso(state.created_at),
                "updated_at": _to_iso(state.updated_at),
            }

    def save_poll_state(
        self,
        provider: str,
        mailbox: str,
        state_key: str,
        *,
        last_polled_at: datetime,
        last_message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        from app.db import SessionLocal
        from app.models import EmailPollState

        with SessionLocal() as session:
            state = (
                session.query(EmailPollState)
                .filter(
                    EmailPollState.provider == provider,
                    EmailPollState.mailbox == mailbox,
                    EmailPollState.state_key == state_key,
                )
                .first()
            )
            now = datetime.now(timezone.utc)
            if not state:
                state = EmailPollState(
                    provider=provider,
                    mailbox=mailbox,
                    state_key=state_key,
                    metadata_json=metadata or {},
                )
                session.add(state)

            state.last_polled_at = last_polled_at
            state.last_message_id = last_message_id
            state.metadata_json = metadata or {}
            state.updated_at = now
            session.commit()

    def mark_failed(self, job_id: str, error_message: str) -> None:
        from app.db import SessionLocal
        from app.models import EmailJob

        with SessionLocal() as session:
            job = session.query(EmailJob).filter(EmailJob.id == _to_uuid(job_id)).first()
            if not job:
                logger.warning("Email job %s not found while marking failed", job_id)
                return
            now = datetime.now(timezone.utc)
            job.status = "failed"
            job.error_message = error_message
            job.completed_at = now
            job.updated_at = now
            session.commit()

    def mark_completed(self, job_id: str, report_id: str) -> None:
        from app.db import SessionLocal
        from app.models import EmailJob

        with SessionLocal() as session:
            job = session.query(EmailJob).filter(EmailJob.id == _to_uuid(job_id)).first()
            if not job:
                logger.warning("Email job %s not found while marking completed", job_id)
                return
            now = datetime.now(timezone.utc)
            job.report_id = report_id
            job.status = "completed"
            job.completed_at = now
            job.updated_at = now
            session.commit()


def get_email_job_store():
    if config.DATABASE_PROVIDER == "sqlalchemy":
        return SqlAlchemyEmailJobStore()
    return SupabaseEmailJobStore()
