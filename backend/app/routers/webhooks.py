"""
Webhooks Router

Public webhook endpoints for external service integrations (Resend, etc.)
These endpoints do not require JWT authentication but use other security mechanisms.

IMPORTANT: This webhook ONLY validates and stores raw attachment bytes.
Document processing happens later in the cron job using the SAME
DocumentProcessor pipeline as file uploads to ensure complete compatibility.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.config import (
    EMAIL_ALLOWED_EXTENSIONS,
    EMAIL_MAX_ATTACHMENTS,
    EMAIL_MAX_ATTACHMENT_SIZE_MB,
    EMAIL_MAX_TOTAL_SIZE_MB,
    INBOUND_EMAIL_PROVIDER,
    RESEND_WEBHOOK_SECRET,
    RESEND_API_KEY
)
from app.services.email_ingest_service import EmailIngestService
from app.services.supabase_storage_service import SupabaseStorageService
from app.services.supabase_service import supabase_service
from app.services.credit_service import credit_service

logger = logging.getLogger(__name__)

router = APIRouter()

email_ingest_service = EmailIngestService()


def get_storage_service() -> SupabaseStorageService:
    return SupabaseStorageService()


def create_service_role_client():
    from supabase import create_client

    return create_client(
        supabase_service.supabase_url,
        supabase_service.supabase_service_key
    )


def verify_resend_webhook(raw_body: bytes, headers: dict):
    from svix.webhooks import Webhook, WebhookVerificationError

    try:
        wh = Webhook(RESEND_WEBHOOK_SECRET)
        payload = wh.verify(raw_body, headers)
        logger.info("Webhook signature verified successfully")
        return payload, None
    except WebhookVerificationError as exc:
        logger.warning(f"Invalid webhook signature: {exc}")
        return None, "Invalid webhook signature"
    except Exception as exc:
        logger.error(f"Error verifying webhook signature: {exc}")
        return None, "Webhook verification failed"


def extract_instruction_text(email_body: str) -> str:
    """
    Extract instruction text from forwarded email body.
    Attempts to find the original message content before email headers.
    """
    forwarded_markers = [
        "---------- Forwarded message ---------",
        "Begin forwarded message:",
        "-------- Original Message --------",
        "From:",
    ]
    
    body_lower = email_body.lower()
    earliest_pos = len(email_body)
    
    for marker in forwarded_markers:
        pos = body_lower.find(marker.lower())
        if pos != -1 and pos < earliest_pos:
            earliest_pos = pos
    
    if earliest_pos < len(email_body):
        instruction_text = email_body[:earliest_pos].strip()
    else:
        instruction_text = email_body.strip()
    
    if not instruction_text or len(instruction_text) < 10:
        instruction_text = email_body.strip()
    
    return instruction_text


def validate_attachment(filename: str, size_bytes: int) -> tuple[bool, Optional[str]]:
    """
    Validate attachment against centralized configuration.
    Uses same rules as file uploader for consistency.
    """
    file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
    if file_ext not in EMAIL_ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type: {file_ext}"
    
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > EMAIL_MAX_ATTACHMENT_SIZE_MB:
        return False, f"File too large: {size_mb:.1f}MB (max {EMAIL_MAX_ATTACHMENT_SIZE_MB}MB)"
    
    return True, None


@router.post("/webhooks/email-inbound")
async def handle_inbound_email(request: Request):
    """
    Handle inbound email webhook from Resend.
    
    This endpoint validates emails and stores raw attachments in Supabase Storage.
    Document processing happens later via cron using the same pipeline as file uploads.
    
    Response codes:
        - 401: Invalid signature (Resend retries)
        - 200: Valid request (may or may not create job)
    """
    try:
        if INBOUND_EMAIL_PROVIDER != "resend":
            logger.info("Inbound Resend webhook called while inbound email provider is disabled")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Inbound email webhook is not enabled"}
            )

        # Step 1: Verify webhook signature using Svix
        if not RESEND_WEBHOOK_SECRET:
            logger.error("RESEND_WEBHOOK_SECRET not configured")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Webhook secret not configured"}
            )
        
        # Read raw body and headers
        raw_body = await request.body()
        headers = {
            "svix-id": request.headers.get("svix-id", ""),
            "svix-timestamp": request.headers.get("svix-timestamp", ""),
            "svix-signature": request.headers.get("svix-signature", "")
        }
        
        # Verify that all required headers are present
        if not all(headers.values()):
            logger.warning("Webhook received with missing Svix headers")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing Svix webhook headers"}
            )
        
        # Verify signature using Svix
        payload, verification_error = verify_resend_webhook(raw_body, headers)
        if verification_error:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": verification_error}
            )
        
        # Step 2: Parse and process payload (already verified and parsed by Svix)
        
        event_type = payload.get("type")
        email_data = payload.get("data", {})
        
        if event_type != "email.received":
            logger.info(f"Ignoring webhook event type: {event_type}")
            return JSONResponse(content={"status": "ignored", "reason": "event_type"})
        
        provider_message_id = email_data.get("message_id")
        
        to_list = email_data.get("to", [])
        to_address = to_list[0] if to_list else ""
        from_address = email_data.get("from", "")
        email_id = email_data.get("email_id", "")

        subject = email_data.get("subject", "")
        email_body = email_data.get("text", "") or email_data.get("html", "")
        attachments = email_data.get("attachments", [])
        
        logger.info(f"Processing inbound email: {provider_message_id} from {from_address} to {to_address}")
        
        # Create service role client for system-level database operations
        # Webhooks are system operations without user JWT authentication
        db_client = create_service_role_client()
        
        # Step 3: Idempotency check
        existing_job = db_client.table("email_jobs")\
            .select("id, status")\
            .eq("provider_message_id", provider_message_id)\
            .limit(1)\
            .execute()
        
        if existing_job.data:
            logger.info(f"Duplicate webhook ignored: {provider_message_id}")
            return JSONResponse(content={"status": "duplicate", "job_id": existing_job.data[0]['id']})
        
        # Step 4: Validate email alias
        endpoint = db_client.table("email_ingest_endpoints")\
            .select("*")\
            .eq("full_address", to_address)\
            .limit(1)\
            .execute()
        
        if not endpoint.data:
            logger.warning(f"Unknown email alias: {to_address}")
            return JSONResponse(content={"status": "ignored", "reason": "unknown_alias"})
        
        endpoint_data = endpoint.data[0]
        user_id = endpoint_data["user_id"]

        # Validate user_id before using it
        if not user_id:
            logger.error(f"Email endpoint {to_address} has no user_id")
            return JSONResponse(content={"status": "ignored", "reason": "invalid_endpoint"})

        if not endpoint_data["is_active"]:
            logger.warning(f"Inactive email alias: {to_address}")
            return JSONResponse(content={"status": "ignored", "reason": "inactive_alias"})
        
        # Step 5: Verify sender
        sender_check = db_client.table("verified_senders")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("email", from_address)\
            .eq("status", "verified")\
            .limit(1)\
            .execute()
        
        if not sender_check.data:
            logger.warning(f"Unverified sender: {from_address} for user {user_id}")
            return JSONResponse(content={"status": "ignored", "reason": "unverified_sender"})
        
        # Step 6: Check credit limits (replaces old rate limiting)
        credit_status = credit_service.check_credits_sync(user_id)

        if credit_status.warning_level == 'blocked':
            logger.warning(f"Credit limit exceeded for user {user_id}")

            job_data = {
                "user_id": user_id,
                "ingest_endpoint_id": endpoint_data["id"],
                "from_email": from_address,
                "subject": subject[:255],
                "provider_message_id": provider_message_id,
                "status": "discarded",
                "error_message": "Monthly credit limit reached",
                "instruction_text": None,
                "raw_metadata": {"credit_limited": True}
            }

            db_client.table("email_jobs").insert(job_data).execute()
            return JSONResponse(content={"status": "credit_limited"})
        
        # Step 7: Fetch detailed attachment list from Resend Receiving Attachments API
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                list_url = f"https://api.resend.com/emails/receiving/{email_id}/attachments"
                headers = {"Authorization": f"Bearer {RESEND_API_KEY}"}
                list_resp = await client.get(list_url, headers=headers)
                list_resp.raise_for_status()
                attachment_list_data = list_resp.json()
                detailed_attachments = attachment_list_data.get("data", [])
                logger.info(f"Fetched {len(detailed_attachments)} detailed attachments from Resend API")
            except Exception as e:
                logger.error(f"Failed to fetch attachment list from Resend API: {e}")
                # Fallback to webhook metadata if API call fails
                detailed_attachments = []

        # Step 8: Validate attachments (use detailed list if available, fallback to webhook metadata)
        valid_attachments = []
        skipped_attachments = []
        total_size_bytes = 0

        for attachment in attachments[:EMAIL_MAX_ATTACHMENTS]:
            filename = attachment.get("filename", "unnamed")
            size_bytes = attachment.get("size", 0)
            attachment_id = attachment.get("id", "")

            is_valid, error_msg = validate_attachment(filename, size_bytes)

            if not is_valid:
                logger.info(f"Skipping attachment: {filename} - {error_msg}")
                skipped_attachments.append({"filename": filename, "reason": error_msg})
                continue

            # Check if we have detailed attachment info from API
            detailed_info = None
            if detailed_attachments:
                detailed_info = next((a for a in detailed_attachments if a.get("id") == attachment_id), None)

            # Use API-provided download URL if available, otherwise construct basic URL
            if detailed_info and "download_url" in detailed_info:
                download_url = detailed_info["download_url"]
                content_type = detailed_info.get("content_type", attachment.get("content_type", ""))
                logger.info(f"Using detailed download URL for {filename}")
            else:
                # Fallback - this might still fail but we'll try
                download_url = f"https://api.resend.com/attachments/{attachment_id}"
                content_type = attachment.get("content_type", "")
                logger.warning(f"Falling back to basic download URL for {filename} - may fail with 405")

            if total_size_bytes + size_bytes > EMAIL_MAX_TOTAL_SIZE_MB * 1024 * 1024:
                logger.warning(f"Total size limit exceeded, skipping: {filename}")
                skipped_attachments.append({"filename": filename, "reason": "Total size limit exceeded"})
                continue

            valid_attachments.append({
                "filename": filename,
                "size_bytes": size_bytes,
                "content_type": content_type,
                "download_url": download_url
            })
            total_size_bytes += size_bytes
        
        # Step 8: Require at least one valid attachment
        if not valid_attachments:
            logger.warning(f"No valid attachments in email from {from_address}")
            
            job_data = {
                "user_id": user_id,
                "ingest_endpoint_id": endpoint_data["id"],
                "from_email": from_address,
                "subject": subject[:255],
                "provider_message_id": provider_message_id,
                "status": "discarded",
                "error_message": "No valid attachments found",
                "instruction_text": None,
                "raw_metadata": {"skipped_attachments": skipped_attachments}
            }
            
            db_client.table("email_jobs").insert(job_data).execute()
            return JSONResponse(content={"status": "discarded", "reason": "no_valid_attachments"})
        
        # Step 9: Download and store attachments (raw bytes only, no processing)
        import uuid
        job_id = str(uuid.uuid4())
        stored_attachments = []
        storage_service = get_storage_service()
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attachment in valid_attachments:
                try:
                    # Download attachment from Resend's pre-signed download URL (no auth needed)
                    response = await client.get(attachment["download_url"])
                    response.raise_for_status()
                    file_content = response.content
                    
                    # Upload to same Storage bucket as UI uploads (report-documents)
                    # Use job_id as document_id and report_id for consistent path structure
                    upload_result = storage_service.upload_document_for_user(
                        user_id=user_id,
                        document_id=str(job_id),
                        pdf_bytes=file_content,
                        report_id=str(job_id),
                        content_type=attachment["content_type"]
                    )

                    # Use the actual returned storage path and metadata
                    stored_attachments.append({
                        "filename": attachment["filename"],
                        "storage_path": upload_result["storage_path"],
                        "content_hash": upload_result["content_hash"],
                        "size_bytes": attachment["size_bytes"],
                        "content_type": attachment["content_type"]
                    })
                    logger.info(f"Stored attachment: {upload_result['storage_path']} ({attachment['size_bytes']} bytes, duplicate: {upload_result.get('duplicate', False)})")
                
                except Exception as e:
                    logger.error(f"Error processing attachment {attachment['filename']}: {e}")
                    skipped_attachments.append({
                        "filename": attachment["filename"],
                        "reason": f"Download/upload error: {str(e)}"
                    })
        
        if not stored_attachments:
            logger.error(f"Failed to store any attachments for email from {from_address}")
            
            job_data = {
                "user_id": user_id,
                "ingest_endpoint_id": endpoint_data["id"],
                "from_email": from_address,
                "subject": subject[:255],
                "provider_message_id": provider_message_id,
                "status": "discarded",
                "error_message": "Failed to store attachments",
                "instruction_text": None,
                "raw_metadata": {"skipped_attachments": skipped_attachments}
            }
            
            db_client.table("email_jobs").insert(job_data).execute()
            return JSONResponse(content={"status": "discarded", "reason": "storage_failed"})
        
        # Step 10: Extract instructions and create pending job
        instruction_text = extract_instruction_text(email_body)
        
        job_data = {
            "id": job_id,
            "user_id": user_id,
            "ingest_endpoint_id": endpoint_data["id"],
            "from_email": from_address,
            "subject": subject[:255],
            "provider_message_id": provider_message_id,
            "status": "pending",
            "instruction_text": instruction_text[:2000] if instruction_text else None,
            "raw_metadata": {
                "attachments": stored_attachments,
                "skipped_attachments": skipped_attachments if skipped_attachments else None
            }
        }
        
        db_client.table("email_jobs").insert(job_data).execute()
        
        logger.info(f"✅ Created job {job_id} for user {user_id} with {len(stored_attachments)} attachments")
        
        return JSONResponse(content={
            "status": "accepted",
            "job_id": job_id,
            "attachments_stored": len(stored_attachments),
            "attachments_skipped": len(skipped_attachments)
        })
    
    except Exception as e:
        logger.error(f"Unexpected error in webhook handler: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error"}
        )
