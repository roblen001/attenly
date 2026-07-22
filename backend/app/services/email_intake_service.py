"""Provider-neutral inbound email intake.

Inbound providers turn their provider-specific message payloads into this
service's simple attachment dictionaries. The service validates alias ownership,
verified senders, credit limits, storage, and job creation through configured
providers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import (
    EMAIL_MAX_ATTACHMENTS,
    EMAIL_MAX_TOTAL_SIZE_MB,
)
from app.services.email_intake_utils import (
    extract_instruction_text,
    first_matching_endpoint_address,
    normalize_email_address,
    validate_attachment,
)
from app.services.email_job_store import get_email_job_store
from app.services.storage_factory import get_configured_storage_service

logger = logging.getLogger(__name__)


class EmailIntakeService:
    """Validate and enqueue inbound email jobs for any provider."""

    def __init__(
        self,
        *,
        job_store=None,
        storage_service=None,
        credit_service=None,
    ):
        self.job_store = job_store or get_email_job_store()
        self.storage_service = storage_service or get_configured_storage_service()
        if credit_service is None:
            from app.services.credit_service import credit_service as configured_credit_service

            credit_service = configured_credit_service
        self.credit_service = credit_service

    def handle_inbound_email(
        self,
        *,
        provider: str,
        provider_message_id: str,
        to_addresses: List[str],
        from_address: str,
        subject: str,
        body_text: str,
        attachments: List[Dict[str, Any]],
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from_email = normalize_email_address(from_address)
        provider_job_id = f"{provider}:{provider_message_id}"

        existing_job = self.job_store.get_job_by_provider_message_id(provider_job_id)
        if existing_job:
            return {
                "status": "duplicate",
                "job_id": existing_job["id"],
            }

        matched_address, endpoint = first_matching_endpoint_address(
            to_addresses,
            self.job_store.get_endpoint_by_address,
        )
        if not endpoint:
            logger.warning("Unknown inbound email alias candidates: %s", to_addresses)
            return {"status": "ignored", "reason": "unknown_alias"}

        user_id = endpoint.get("user_id")
        if not user_id:
            logger.error("Email endpoint %s has no user_id", matched_address)
            return {"status": "ignored", "reason": "invalid_endpoint"}

        if not endpoint.get("is_active"):
            logger.warning("Inactive email alias: %s", matched_address)
            return {"status": "ignored", "reason": "inactive_alias"}

        if not self.job_store.is_verified_sender(user_id, from_email):
            logger.warning("Unverified sender: %s for user %s", from_email, user_id)
            return {"status": "ignored", "reason": "unverified_sender"}

        credit_status = self.credit_service.check_credits_sync(user_id)
        if credit_status.warning_level == "blocked":
            job_id = self.job_store.create_job(
                {
                    "user_id": user_id,
                    "ingest_endpoint_id": endpoint["id"],
                    "from_email": from_email,
                    "subject": subject,
                    "provider_message_id": provider_job_id,
                    "status": "discarded",
                    "error_message": "Monthly credit limit reached",
                    "instruction_text": None,
                    "raw_metadata": {"credit_limited": True, **(raw_metadata or {})},
                    "attachment_count": 0,
                }
            )
            return {"status": "credit_limited", "job_id": job_id}

        valid_attachments = []
        skipped_attachments = []
        total_size_bytes = 0

        for attachment in attachments[:EMAIL_MAX_ATTACHMENTS]:
            filename = attachment.get("filename") or "unnamed"
            content = attachment.get("content") or b""
            size_bytes = int(attachment.get("size_bytes") or len(content))
            content_type = attachment.get("content_type") or "application/octet-stream"

            is_valid, error_msg = validate_attachment(filename, size_bytes)
            if not is_valid:
                skipped_attachments.append({"filename": filename, "reason": error_msg})
                continue

            if total_size_bytes + size_bytes > EMAIL_MAX_TOTAL_SIZE_MB * 1024 * 1024:
                skipped_attachments.append({"filename": filename, "reason": "Total size limit exceeded"})
                continue

            if not content:
                skipped_attachments.append({"filename": filename, "reason": "Empty attachment content"})
                continue

            valid_attachments.append(
                {
                    "filename": filename,
                    "size_bytes": size_bytes,
                    "content_type": content_type,
                    "content": content,
                }
            )
            total_size_bytes += size_bytes

        if not valid_attachments:
            job_id = self.job_store.create_job(
                {
                    "user_id": user_id,
                    "ingest_endpoint_id": endpoint["id"],
                    "from_email": from_email,
                    "subject": subject,
                    "provider_message_id": provider_job_id,
                    "status": "discarded",
                    "error_message": "No valid attachments found",
                    "instruction_text": None,
                    "raw_metadata": {
                        "skipped_attachments": skipped_attachments,
                        **(raw_metadata or {}),
                    },
                    "attachment_count": 0,
                }
            )
            return {"status": "discarded", "reason": "no_valid_attachments", "job_id": job_id}

        job_id = str(uuid4())
        stored_attachments = []
        for attachment in valid_attachments:
            upload_result = self.storage_service.upload_document_for_user(
                user_id=user_id,
                document_id=job_id,
                pdf_bytes=attachment["content"],
                report_id=job_id,
                content_type=attachment["content_type"],
            )
            stored_attachments.append(
                {
                    "filename": attachment["filename"],
                    "storage_path": upload_result["storage_path"],
                    "content_hash": upload_result["content_hash"],
                    "size_bytes": attachment["size_bytes"],
                    "content_type": attachment["content_type"],
                }
            )

        instruction_text = extract_instruction_text(body_text)
        job_id = self.job_store.create_job(
            {
                "id": job_id,
                "user_id": user_id,
                "ingest_endpoint_id": endpoint["id"],
                "from_email": from_email,
                "subject": subject,
                "provider_message_id": provider_job_id,
                "status": "pending",
                "instruction_text": instruction_text[:2000] if instruction_text else None,
                "raw_metadata": {
                    "attachments": stored_attachments,
                    "skipped_attachments": skipped_attachments or None,
                    **(raw_metadata or {}),
                },
                "attachment_count": len(stored_attachments),
            }
        )
        return {
            "status": "accepted",
            "job_id": job_id,
            "attachments_stored": len(stored_attachments),
            "attachments_skipped": len(skipped_attachments),
        }
