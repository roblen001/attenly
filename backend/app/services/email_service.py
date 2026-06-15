"""
Outbound email provider facade.

The app can run with email disabled, with the original Resend provider, or
with Microsoft Graph for enterprise deployments. Callers use EmailService and
do not need to know which provider is active.
"""

import logging
from typing import Optional, Protocol

from app import config
from app.services.microsoft_graph_mail import MicrosoftGraphMailClient

logger = logging.getLogger(__name__)


class OutboundEmailProvider(Protocol):
    name: str

    def is_configured(self) -> bool:
        ...

    def send_email(self, to: str, subject: str, body: str) -> bool:
        ...


class NoopEmailProvider:
    name = "none"

    def is_configured(self) -> bool:
        return False

    def send_email(self, to: str, subject: str, body: str) -> bool:
        logger.info("Outbound email disabled; skipped email to %s with subject %r", to, subject)
        return False


class ResendEmailProvider:
    name = "resend"

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        self._resend = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        if self._resend is None:
            import resend

            resend.api_key = self.api_key
            self._resend = resend
        return self._resend

    def send_email(self, to: str, subject: str, body: str) -> bool:
        if not self.is_configured():
            logger.error("Cannot send Resend email: RESEND_API_KEY not configured")
            return False

        try:
            response = self._client().Emails.send(
                {
                    "from": config.EMAIL_FROM_ADDRESS,
                    "to": [to],
                    "subject": subject,
                    "text": body,
                }
            )
            logger.info("Resend email sent to %s, email_id: %s", to, response.get("id"))
            return True
        except Exception as exc:
            logger.error("Failed to send Resend email to %s: %s", to, exc)
            return False


class MicrosoftGraphEmailProvider:
    name = "microsoft_graph"

    def __init__(
        self,
        tenant_id: Optional[str],
        client_id: Optional[str],
        client_secret: Optional[str],
        mailbox: Optional[str],
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.mailbox = mailbox
        self.client = MicrosoftGraphMailClient(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            mailbox=mailbox,
        )

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def send_email(self, to: str, subject: str, body: str) -> bool:
        if not self.is_configured():
            logger.error("Cannot send Microsoft Graph email: Graph settings are incomplete")
            return False

        try:
            self.client.send_mail(to, subject, body)
            logger.info("Microsoft Graph email sent to %s", to)
            return True
        except Exception as exc:
            logger.error("Microsoft Graph email failed for %s: %s", to, exc)
            return False


def _build_outbound_provider() -> OutboundEmailProvider:
    provider = config.OUTBOUND_EMAIL_PROVIDER

    if provider == "resend":
        logger.info("Email service initialized with Resend")
        return ResendEmailProvider(config.RESEND_API_KEY)

    if provider == "microsoft_graph":
        logger.info("Email service initialized with Microsoft Graph")
        return MicrosoftGraphEmailProvider(
            tenant_id=config.GRAPH_TENANT_ID,
            client_id=config.GRAPH_CLIENT_ID,
            client_secret=config.GRAPH_CLIENT_SECRET,
            mailbox=config.GRAPH_MAILBOX,
        )

    logger.info("Email service initialized with outbound email disabled")
    return NoopEmailProvider()


class EmailService:
    """
    Provider-neutral outbound email service.

    Webhook signature verification is handled by the inbound webhook router.
    This service only sends application emails.
    """

    def __init__(self, provider: Optional[OutboundEmailProvider] = None):
        self.provider = provider or _build_outbound_provider()

    def send_verification_email(
        self,
        to: str,
        token: str,
        user_alias: str,
    ) -> bool:
        verification_url = f"{config.API_URL}/email-ingest/verify-sender?token={token}"
        subject = "Verify your email for Attenly"
        body = f"""Hello,

You've been added as a verified sender for Attenly email submissions.

Your documents can now be sent to: {user_alias}

To complete verification, please click the link below:
{verification_url}

This link will expire in {config.EMAIL_VERIFICATION_EXPIRY_HOURS} hours.

If you didn't request this verification, you can safely ignore this email.

---
Attenly - AI-Powered Document Processing
{config.APP_URL}
"""
        return self.provider.send_email(to, subject, body)

    def send_report_ready_email(
        self,
        to: str,
        report_url: str,
        report_name: str,
        subject_text: Optional[str] = None,
    ) -> bool:
        if subject_text:
            subject = f"Your Attenly report is ready: {subject_text}"
        else:
            subject = "Your Attenly report is ready"

        body = f"""Hello,

Your document processing is complete!

Report: {report_name}

View your report here:
{report_url}

The report includes:
- Extracted data from your documents
- Source references with page numbers
- Downloadable PDF format

---
Attenly - AI-Powered Document Processing
{config.APP_URL}
"""
        return self.provider.send_email(to, subject, body)

    def send_job_failed_email(
        self,
        to: str,
        job_id: str,
        error: str,
    ) -> bool:
        subject = "Attenly document processing failed"
        body = f"""Hello,

Unfortunately, we were unable to process your document submission.

Job ID: {job_id}
Error: {error}

Common causes:
- Unsupported file format
- File size too large
- Document contains only images (OCR required)
- Processing timeout

Please try:
1. Check that your attachments are in supported formats (PDF, DOCX, TXT, PNG, JPG, GIF)
2. Ensure file sizes are within limits (max {config.EMAIL_MAX_ATTACHMENT_SIZE_MB}MB per file)
3. For image-based PDFs, ensure they contain clear, readable text
4. Contact support if the issue persists

You can view your email settings and try again at:
{config.APP_URL}/settings/email-ingest

---
Attenly - AI-Powered Document Processing
{config.APP_URL}
"""
        return self.provider.send_email(to, subject, body)

    def is_configured(self) -> bool:
        return self.provider.is_configured()


email_service = EmailService()
