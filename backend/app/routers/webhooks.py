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
from svix.webhooks import Webhook, WebhookVerificationError
from supabase import create_client

from app.config import (
    EMAIL_ALLOWED_EXTENSIONS,
    EMAIL_MAX_ATTACHMENTS,
    EMAIL_MAX_ATTACHMENT_SIZE_MB,
    EMAIL_MAX_TOTAL_SIZE_MB,
    RESEND_WEBHOOK_SECRET,
    RESEND_API_KEY
)
from app.services.email_ingest_service import EmailIngestService
from app.services.supabase_storage_service import SupabaseStorageService
from app.services.supabase_service import supabase_service

logger = logging.getLogger(__name__)

router = APIRouter()

email_ingest_service = EmailIngestService()
storage_service = SupabaseStorageService()


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
        try:
            wh = Webhook(RESEND_WEBHOOK_SECRET)
            payload = wh.verify(raw_body, headers)
            logger.info("Webhook signature verified successfully")
        except WebhookVerificationError as e:
            logger.warning(f"Invalid webhook signature: {e}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid webhook signature"}
            )
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Webhook verification failed"}
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
        
        subject = email_data.get("subject", "")
        email_body = email_data.get("text", "") or email_data.get("html", "")
        attachments = email_data.get("attachments", [])
        
        logger.info(f"Processing inbound email: {provider_message_id} from {from_address} to {to_address}")
        
        # Create service role client for system-level database operations
        # Webhooks are system operations without user JWT authentication
        db_client = create_client(
            supabase_service.supabase_url,
            supabase_service.supabase_service_key
        )
        
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
        
        # Step 6: Check rate limit
        rate_limit_ok, rate_limit_msg = email_ingest_service.check_rate_limit(user_id)
        
        if not rate_limit_ok:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            
            job_data = {
                "user_id": user_id,
                "endpoint_id": endpoint_data["id"],
                "sender_email": from_address,
                "subject": subject[:255],
                "provider_message_id": provider_message_id,
                "status": "discarded",
                "error_message": f"Rate limit exceeded: {rate_limit_msg}",
                "instruction_text": None,
                "raw_metadata": {"rate_limited": True}
            }
            
            db_client.table("email_jobs").insert(job_data).execute()
            return JSONResponse(content={"status": "rate_limited"})
        
        # Step 7: Validate attachments
        valid_attachments = []
        skipped_attachments = []
        total_size_bytes = 0
        
        for attachment in attachments[:EMAIL_MAX_ATTACHMENTS]:
            filename = attachment.get("filename", "unnamed")
            size_bytes = attachment.get("size", 0)
            content_type = attachment.get("content_type", "")
            
            # Resend provides attachment ID - construct download URL
            attachment_id = attachment.get("id", "")
            if not attachment_id:
                logger.warning(f"Attachment {filename} has no ID, skipping")
                skipped_attachments.append({"filename": filename, "reason": "No attachment ID"})
                continue
            
            # Resend attachment download URL format
            download_url = f"https://api.resend.com/attachments/{attachment_id}"
            
            is_valid, error_msg = validate_attachment(filename, size_bytes)
            
            if not is_valid:
                logger.info(f"Skipping attachment: {filename} - {error_msg}")
                skipped_attachments.append({"filename": filename, "reason": error_msg})
                continue
            
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
                "endpoint_id": endpoint_data["id"],
                "sender_email": from_address,
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
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attachment in valid_attachments:
                try:
                    # Download attachment from Resend API with authorization
                    headers = {"Authorization": f"Bearer {RESEND_API_KEY}"}
                    response = await client.get(attachment["download_url"], headers=headers)
                    response.raise_for_status()
                    file_content = response.content
                    
                    # Store in Supabase Storage: email-attachments/{user_id}/{job_id}/{filename}
                    storage_path = f"{user_id}/{job_id}/{attachment['filename']}"
                    
                    upload_result = storage_service.upload_file(
                        bucket_name="email-attachments",
                        file_path=storage_path,
                        file_content=file_content,
                        content_type=attachment["content_type"]
                    )
                    
                    if upload_result["success"]:
                        stored_attachments.append({
                            "filename": attachment["filename"],
                            "storage_path": storage_path,
                            "size_bytes": attachment["size_bytes"],
                            "content_type": attachment["content_type"]
                        })
                        logger.info(f"Stored attachment: {storage_path} ({attachment['size_bytes']} bytes)")
                    else:
                        logger.error(f"Failed to store {attachment['filename']}: {upload_result.get('error')}")
                        skipped_attachments.append({
                            "filename": attachment["filename"],
                            "reason": f"Storage failed: {upload_result.get('error')}"
                        })
                
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
                "endpoint_id": endpoint_data["id"],
                "sender_email": from_address,
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
            "endpoint_id": endpoint_data["id"],
            "sender_email": from_address,
            "subject": subject[:255],
            "provider_message_id": provider_message_id,
            "status": "pending",
            "instruction_text": instruction_text[:2000] if instruction_text else None,
            "default_agent_id": endpoint_data.get("default_agent_id"),
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
