"""
Email Service - Resend SDK Adapter for Attenly

Provides email sending capabilities for the Email to Attenly feature.
Uses Resend as the email service provider.
"""

import resend
import logging
from typing import Optional
from app import config

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending emails via Resend.
    
    This service acts as an adapter around the Resend SDK, making it easy
    to swap email providers in the future if needed.
    
    Note: Webhook signature verification is handled directly in the webhook
    router using the Svix library, not in this service.
    """
    
    def __init__(self):
        """Initialize Resend SDK with API key from configuration."""
        if config.RESEND_API_KEY:
            resend.api_key = config.RESEND_API_KEY
            logger.info("Email service initialized with Resend")
        else:
            logger.warning("RESEND_API_KEY not configured - email features will not work")
    
    def send_verification_email(
        self, 
        to: str, 
        token: str, 
        user_alias: str
    ) -> bool:
        """
        Send verification email to a new sender address.
        
        Args:
            to: Recipient email address (the sender being verified)
            token: Verification token to include in the link
            user_alias: User's email alias (e.g., u_abc123@in.attenly.ca)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not config.RESEND_API_KEY:
            logger.error("Cannot send verification email: RESEND_API_KEY not configured")
            return False
        
        try:
            verification_url = f"{config.API_URL}/email-ingest/verify-sender?token={token}"
            
            subject = "Verify your email for Attenly"
            
            # Plain text email body
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
            
            params = {
                "from": config.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "text": body,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"Verification email sent to {to}, email_id: {response.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {to}: {str(e)}")
            return False
    
    def send_report_ready_email(
        self,
        to: str,
        report_url: str,
        report_name: str,
        subject_text: Optional[str] = None
    ) -> bool:
        """
        Send notification email when a report is ready.
        
        Args:
            to: Recipient email address
            report_url: Direct link to view the report
            report_name: Name of the generated report
            subject_text: Optional subject from the original email
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not config.RESEND_API_KEY:
            logger.error("Cannot send report ready email: RESEND_API_KEY not configured")
            return False
        
        try:
            # Create subject line
            if subject_text:
                subject = f"Your Attenly report is ready: {subject_text}"
            else:
                subject = "Your Attenly report is ready"
            
            # Plain text email body
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
            
            params = {
                "from": config.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "text": body,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"Report ready email sent to {to}, email_id: {response.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send report ready email to {to}: {str(e)}")
            return False
    
    def send_job_failed_email(
        self,
        to: str,
        job_id: str,
        error: str
    ) -> bool:
        """
        Send notification email when a job processing fails.
        
        Args:
            to: Recipient email address
            job_id: ID of the failed job
            error: Short error description for the user
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not config.RESEND_API_KEY:
            logger.error("Cannot send job failed email: RESEND_API_KEY not configured")
            return False
        
        try:
            subject = "Attenly document processing failed"
            
            # Plain text email body
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
            
            params = {
                "from": config.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "text": body,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"Job failed email sent to {to}, email_id: {response.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send job failed email to {to}: {str(e)}")
            return False
    
    def is_configured(self) -> bool:
        """
        Check if email service is properly configured.
        
        Returns:
            True if API key and webhook secret are configured
        """
        return bool(config.RESEND_API_KEY and config.RESEND_WEBHOOK_SECRET)


# Global instance for easy import
email_service = EmailService()
