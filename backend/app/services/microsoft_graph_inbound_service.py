"""Microsoft Graph inbound email poller."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app import config
from app.services.email_intake_service import EmailIntakeService
from app.services.email_job_store import get_email_job_store
from app.services.microsoft_graph_mail import MicrosoftGraphMailClient

logger = logging.getLogger(__name__)


def _parse_graph_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Invalid Graph datetime value: %s", value)
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recipient_addresses(message: Dict[str, Any]) -> List[str]:
    recipients = []
    for key in ("toRecipients", "ccRecipients"):
        for recipient in message.get(key) or []:
            address = (
                recipient.get("emailAddress", {})
                .get("address", "")
                .strip()
                .lower()
            )
            if address:
                recipients.append(address)
    return recipients


def _sender_address(message: Dict[str, Any]) -> str:
    return (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
        .strip()
        .lower()
    )


def _message_body_text(message: Dict[str, Any]) -> str:
    body = message.get("body") or {}
    content = body.get("content")
    if content:
        return content
    return message.get("bodyPreview") or ""


class MicrosoftGraphInboundPoller:
    provider = "microsoft_graph"
    state_key = "default"

    def __init__(
        self,
        *,
        graph_client: Optional[MicrosoftGraphMailClient] = None,
        intake_service: Optional[EmailIntakeService] = None,
        job_store=None,
    ):
        self.graph_client = graph_client or MicrosoftGraphMailClient(
            tenant_id=config.GRAPH_TENANT_ID,
            client_id=config.GRAPH_CLIENT_ID,
            client_secret=config.GRAPH_CLIENT_SECRET,
            mailbox=config.GRAPH_MAILBOX,
        )
        self.job_store = job_store or get_email_job_store()
        self.intake_service = intake_service or EmailIntakeService(job_store=self.job_store)

    def _poll_since(self) -> datetime:
        state = self.job_store.get_poll_state(
            self.provider,
            config.GRAPH_MAILBOX,
            self.state_key,
        )
        if state and state.get("last_polled_at"):
            last_polled_at = _parse_graph_datetime(state["last_polled_at"])
            if last_polled_at:
                return last_polled_at - timedelta(seconds=config.GRAPH_POLL_LOOKBACK_SECONDS)

        return datetime.now(timezone.utc) - timedelta(hours=config.GRAPH_INITIAL_LOOKBACK_HOURS)

    def _save_poll_state(
        self,
        last_polled_at: datetime,
        *,
        last_message_id: Optional[str],
        summary: Dict[str, Any],
    ) -> None:
        self.job_store.save_poll_state(
            self.provider,
            config.GRAPH_MAILBOX,
            self.state_key,
            last_polled_at=last_polled_at,
            last_message_id=last_message_id,
            metadata=summary,
        )

    def _attachment_inputs(self, message_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        attachments = []
        skipped = []

        for attachment in self.graph_client.list_message_attachments(message_id):
            attachment_type = attachment.get("@odata.type", "")
            filename = attachment.get("name") or "unnamed"
            if attachment.get("isInline"):
                skipped.append({"filename": filename, "reason": "inline_attachment"})
                continue
            if attachment_type and not attachment_type.endswith("fileAttachment"):
                skipped.append({"filename": filename, "reason": "unsupported_attachment_type"})
                continue

            content_bytes = attachment.get("contentBytes")
            if not content_bytes:
                skipped.append({"filename": filename, "reason": "missing_content"})
                continue

            try:
                content = base64.b64decode(content_bytes)
            except Exception as exc:
                skipped.append({"filename": filename, "reason": f"invalid_base64: {exc}"})
                continue

            attachments.append(
                {
                    "filename": filename,
                    "content": content,
                    "size_bytes": int(attachment.get("size") or len(content)),
                    "content_type": attachment.get("contentType") or "application/octet-stream",
                }
            )

        return attachments, skipped

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        message_id = message["id"]
        provider_message_id = message.get("internetMessageId") or message_id
        provider_job_id = f"{self.provider}:{provider_message_id}"

        existing_job = self.job_store.get_job_by_provider_message_id(provider_job_id)
        if existing_job:
            return {"status": "duplicate", "job_id": existing_job["id"]}

        attachments, skipped_attachments = self._attachment_inputs(message_id)

        result = self.intake_service.handle_inbound_email(
            provider=self.provider,
            provider_message_id=provider_message_id,
            to_addresses=_recipient_addresses(message),
            from_address=_sender_address(message),
            subject=message.get("subject") or "",
            body_text=_message_body_text(message),
            attachments=attachments,
            raw_metadata={
                "graph_message_id": message_id,
                "graph_internet_message_id": message.get("internetMessageId"),
                "receivedDateTime": message.get("receivedDateTime"),
                "skipped_graph_attachments": skipped_attachments or None,
            },
        )
        return result

    def poll_messages(self, *, max_messages: Optional[int] = None) -> Dict[str, Any]:
        if not self.graph_client.is_configured():
            raise RuntimeError("Microsoft Graph inbound email is not fully configured")

        max_messages = max_messages or config.GRAPH_POLL_BATCH_SIZE
        since = self._poll_since()
        messages = self.graph_client.list_messages_since(since, top=max_messages)

        summary: Dict[str, Any] = {
            "success": True,
            "provider": self.provider,
            "mailbox": config.GRAPH_MAILBOX,
            "messages_seen": len(messages),
            "accepted": 0,
            "duplicates": 0,
            "ignored": 0,
            "discarded": 0,
            "errors": 0,
            "since": since.isoformat(),
        }

        max_received_at = None
        last_message_id = None

        for message in messages:
            message_id = message.get("id")
            received_at = _parse_graph_datetime(message.get("receivedDateTime"))
            if received_at and (not max_received_at or received_at > max_received_at):
                max_received_at = received_at
                last_message_id = message_id

            try:
                result = self.process_message(message)
                status = result.get("status")
                if status == "accepted":
                    summary["accepted"] += 1
                elif status == "duplicate":
                    summary["duplicates"] += 1
                elif status == "discarded" or status == "credit_limited":
                    summary["discarded"] += 1
                else:
                    summary["ignored"] += 1
            except Exception as exc:
                summary["errors"] += 1
                logger.error("Failed to process Graph message %s: %s", message_id, exc, exc_info=True)

        poll_time = max_received_at or datetime.now(timezone.utc)
        self._save_poll_state(
            poll_time,
            last_message_id=last_message_id,
            summary=summary,
        )
        return summary


_microsoft_graph_inbound_poller: MicrosoftGraphInboundPoller | None = None


def get_microsoft_graph_inbound_poller() -> MicrosoftGraphInboundPoller:
    global _microsoft_graph_inbound_poller
    if _microsoft_graph_inbound_poller is None:
        _microsoft_graph_inbound_poller = MicrosoftGraphInboundPoller()
    return _microsoft_graph_inbound_poller
