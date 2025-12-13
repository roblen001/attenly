"""
Email Job Processing Service

Processes email jobs by downloading attachments from Supabase Storage
and passing them through the SAME DocumentProcessor pipeline as file uploads.
This ensures complete compatibility with report viewing, quote viewing, etc.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from app.services.supabase_service import supabase_service
from app.services.supabase_storage_service import SupabaseStorageService
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store_manager
from app.services.report_service import report_service
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

storage_service = SupabaseStorageService()
document_processor = DocumentProcessor()
email_service = EmailService()


class EmailJobService:
    """
    Service for processing email jobs using the same pipeline as file uploads.
    
    This ensures that email-generated reports work identically to manually uploaded files:
    - Quote viewing
    - Document viewing
    - PDF downloads
    - All existing report features
    """
    
    def __init__(self):
        self.storage_service = storage_service
        self.document_processor = document_processor
        self.email_service = email_service

    def _get_service_role_client(self):
        """Get a Supabase client with service role key for system operations."""
        from supabase import create_client
        return create_client(
            supabase_service.supabase_url,
            supabase_service.supabase_service_key
        )
    
    async def process_pending_jobs(self, max_jobs: int = 10) -> Dict[str, Any]:
        """
        Process up to max_jobs pending email jobs.
        Uses atomic updates to prevent concurrent processing.
        
        Args:
            max_jobs: Maximum number of jobs to process in this batch
            
        Returns:
            Processing summary with counts and errors
        """
        logger.info(f"Starting batch processing of up to {max_jobs} pending email jobs")
        
        # Create service role client for system-level database operations
        # Background jobs are system operations without user JWT authentication
        from supabase import create_client
        db_client = create_client(
            supabase_service.supabase_url,
            supabase_service.supabase_service_key
        )

        # Fetch pending jobs (oldest first)
        try:
            pending_jobs = db_client.table("email_jobs")\
                .select("*")\
                .eq("status", "pending")\
                .order("created_at")\
                .limit(max_jobs)\
                .execute()
        except Exception as e:
            logger.error(f"Failed to fetch pending jobs: {e}")
            return {
                "success": False,
                "error": f"Failed to fetch pending jobs: {str(e)}",
                "jobs_processed": 0,
                "jobs_successful": 0,
                "jobs_failed": 0
            }
        
        if not pending_jobs.data:
            logger.info("No pending jobs to process")
            return {
                "success": True,
                "jobs_processed": 0,
                "jobs_successful": 0,
                "jobs_failed": 0
            }
        
        logger.info(f"Found {len(pending_jobs.data)} pending jobs to process")
        
        # Process each job
        jobs_successful = 0
        jobs_failed = 0
        
        for job in pending_jobs.data:
            try:
                # Atomically claim the job by updating to 'processing'
                claim_result = db_client.table("email_jobs")\
                    .update({
                        "status": "processing",
                        "updated_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job["id"])\
                    .eq("status", "pending")\
                    .execute()

                # If update succeeded, we claimed the job
                if claim_result.data:
                    logger.info(f"Processing job {job['id']} for user {job['user_id']}")

                    success = await self.process_single_job(job["id"])

                    if success:
                        jobs_successful += 1
                    else:
                        jobs_failed += 1
                else:
                    logger.info(f"Job {job['id']} already claimed by another process")

            except Exception as e:
                logger.error(f"Error processing job {job['id']}: {e}", exc_info=True)
                jobs_failed += 1

                # Mark job as failed
                try:
                    db_client.table("email_jobs")\
                        .update({
                            "status": "failed",
                            "error_message": f"Processing error: {str(e)}",
                            "completed_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", job["id"])\
                        .execute()
                except Exception as update_error:
                    logger.error(f"Failed to update job {job['id']} status: {update_error}")
        
        summary = {
            "success": True,
            "jobs_processed": len(pending_jobs.data),
            "jobs_successful": jobs_successful,
            "jobs_failed": jobs_failed
        }
        
        logger.info(f"Batch processing complete: {jobs_successful} successful, {jobs_failed} failed")
        
        return summary
    
    async def process_single_job(self, job_id: str) -> bool:
        """
        Process a single email job through the complete pipeline.

        Pipeline matches file upload flow:
        1. Check idempotency (skip if report already generated)
        2. Download attachments from Storage
        3. Pass through DocumentProcessor (same as file uploads)
        4. Load agent configuration
        5. Generate report using report_service
        6. Save report to saved_reports table
        7. Update email_jobs.report_id
        8. Send notification email with report URL

        Args:
            job_id: Email job ID

        Returns:
            True if successful, False otherwise
        """
        # Get service role client for database operations
        db_client = self._get_service_role_client()

        try:
            # Step 1: Fetch job details
            job = db_client.table("email_jobs")\
                .select("*")\
                .eq("id", job_id)\
                .single()\
                .execute()
            
            if not job.data:
                logger.error(f"Job {job_id} not found")
                return False
            
            job_data = job.data
            user_id = job_data["user_id"]
            
            # Step 2: IDEMPOTENCY CHECK - Skip if report already generated
            if job_data.get("report_id"):
                logger.info(f"Job {job_id} already has report_id {job_data['report_id']}, skipping processing")
                
                # Verify job is in terminal state
                if job_data.get("status") == "processing":
                    logger.warning(f"Job {job_id} has report_id but status is 'processing', fixing to 'completed'")
                    db_client.table("email_jobs")\
                        .update({
                            "status": "completed",
                            "updated_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", job_id)\
                        .execute()
                
                return True
            
            attachments = job_data["raw_metadata"].get("attachments", [])
            
            if not attachments:
                raise ValueError("No attachments found in job metadata")
            
            logger.info(f"Processing {len(attachments)} attachments for job {job_id}")
            
            # Step 2: Get vector store for this user (same as file uploads)
            vector_store = vector_store_manager.get_store(user_id)
            
            # Step 3: Download and process each attachment through DocumentProcessor
            processed_documents = []
            processing_errors = []
            
            for attachment in attachments:
                try:
                    # Download from Supabase Storage using service role
                    file_content = self.storage_service.download_document_for_system(
                        user_id=user_id,
                        storage_path=attachment["storage_path"]
                    )
                    
                    if not file_content:
                        raise ValueError(f"Failed to download {attachment['filename']}")
                    
                    # Generate file ID (same as file uploader)
                    file_id = str(uuid.uuid4())
                    
                    # Process through DocumentProcessor (SAME pipeline as file uploads)
                    processing_result = await self.document_processor.process_document(
                        file_id=file_id,
                        content=file_content,
                        filename=attachment["filename"],
                        vector_store=vector_store
                    )
                    
                    if processing_result["success"]:
                        processed_documents.append({
                            "file_id": file_id,
                            "filename": attachment["filename"],
                            "processing_result": processing_result
                        })
                        logger.info(f"Successfully processed {attachment['filename']}")
                    else:
                        error_msg = processing_result.get("error", "Unknown error")
                        processing_errors.append(f"{attachment['filename']}: {error_msg}")
                        logger.error(f"Failed to process {attachment['filename']}: {error_msg}")
                
                except Exception as e:
                    error_msg = str(e)
                    processing_errors.append(f"{attachment['filename']}: {error_msg}")
                    logger.error(f"Error processing attachment {attachment['filename']}: {e}")
            
            # Step 4: Check if we have any successfully processed documents
            if not processed_documents:
                raise ValueError(f"No documents were successfully processed. Errors: {'; '.join(processing_errors)}")
            
            # Step 5: Load agent configuration from email_ingest_endpoints (source of truth)
            # Look up the endpoint to get the current default_agent_id
            endpoint_result = db_client.table("email_ingest_endpoints")\
                .select("default_agent_id")\
                .eq("id", job_data["ingest_endpoint_id"])\
                .single()\
                .execute()
            
            if not endpoint_result.data:
                error_msg = "Email endpoint not found. Please check your email ingest settings."
                logger.error(f"Job {job_id}: {error_msg}")
                
                db_client.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": error_msg,
                        "completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                await self.email_service.send_job_failed_email(
                    to=job_data["from_email"],
                    job_id=job_id,
                    error=error_msg
                )
                
                return False
            
            agent_id = endpoint_result.data.get("default_agent_id")
            
            if not agent_id:
                error_msg = "No default agent configured. Please configure a default agent in Settings → Email Ingest."
                logger.error(f"Job {job_id}: {error_msg}")
                
                db_client.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": error_msg,
                        "completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                await self.email_service.send_job_failed_email(
                    to=job_data["from_email"],
                    job_id=job_id,
                    error=error_msg
                )
                
                return False
            
            # Load agent using agent_loader (handles both prebuilt and custom agents)
            from app.services.agent_loader import load_agent_by_id
            
            try:
                agent = load_agent_by_id(agent_id, user_id)
                logger.info(f"Loaded agent '{agent.name}' ({agent_id}) for job {job_id}")
            except ValueError as e:
                error_msg = f"Configured agent '{agent_id}' not found or deleted. Please update your agent configuration."
                logger.error(f"Job {job_id}: {error_msg} - {str(e)}")
                
                db_client.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": error_msg,
                        "completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                await self.email_service.send_job_failed_email(
                    to=job_data["from_email"],
                    job_id=job_id,
                    error=error_msg
                )
                
                return False
            
            # Step 6: Generate report (same as file upload flow)
            document_ids = [doc["file_id"] for doc in processed_documents]
            
            # Collect bounding box data if available (for OCR documents)
            bbox_data = {}
            for doc in processed_documents:
                doc_id = doc["file_id"]
                processing_result = doc["processing_result"]
                
                if "document_data" in processing_result:
                    extracted_data = processing_result["document_data"]
                    if "bounding_boxes" in extracted_data:
                        bbox_data[doc_id] = extracted_data["bounding_boxes"]
                        logger.info(f"Collected bbox data for document {doc_id}")
            
            if bbox_data:
                logger.info(f"Collected bbox data for {len(bbox_data)} OCR documents")
            
            try:
                report_result = await report_service.generate_report(
                    agent=agent,
                    vector_store=vector_store,
                    document_ids=document_ids,
                    bbox_data=bbox_data if bbox_data else None,
                    user_id=user_id
                )
                
                if not report_result["success"]:
                    raise ValueError(f"Report generation failed: {report_result.get('error', 'Unknown error')}")
                
                logger.info(f"Successfully generated report for job {job_id}")
                
            except Exception as e:
                error_msg = f"Report generation failed: {str(e)}"
                logger.error(f"Job {job_id}: {error_msg}")
                
                db_client.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": error_msg,
                        "completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                await self.email_service.send_job_failed_email(
                    to=job_data["from_email"],
                    job_id=job_id,
                    error=error_msg
                )
                
                return False
            
            # Step 7: Extract AI baseline for audit trail
            ai_baseline_answers = supabase_service._extract_baseline_answers(report_result["report_data"])
            logger.info(f"Extracted AI baseline with {len(ai_baseline_answers)} answers")
            
            # Step 8: Save report using service role (system-level save)
            report_name = self._generate_report_name(job_data, agent)
            
            # Build document contents (minimal, no full_text extraction needed for saved reports)
            document_contents = {}
            pdf_binaries = {}
            
            for doc in processed_documents:
                doc_id = doc["file_id"]
                filename = doc["filename"]
                processing_result = doc["processing_result"]
                
                document_contents[doc_id] = {
                    "filename": filename,
                    "metadata": processing_result.get("processing_stats", {})
                }
                
                # Store original PDF content if available
                # For email attachments, we need to re-download from Storage
                try:
                    # Find the attachment in job metadata
                    matching_attachment = next(
                        (att for att in attachments if att["filename"] == filename),
                        None
                    )
                    
                    if matching_attachment:
                        pdf_content = self.storage_service.download_document_for_system(
                            user_id=user_id,
                            storage_path=matching_attachment["storage_path"]
                        )
                        
                        if pdf_content:
                            pdf_binaries[doc_id] = pdf_content
                            logger.info(f"Collected PDF binary for {doc_id} ({len(pdf_content)} bytes)")
                
                except Exception as e:
                    logger.warning(f"Failed to collect PDF binary for {doc_id}: {e}")
            
            try:
                report_id = supabase_service.save_report_for_system(
                    user_id=user_id,
                    agent_id=agent_id,
                    agent_name=agent.name,
                    report_name=report_name,
                    report_data=report_result["report_data"],
                    document_contents=document_contents,
                    pdf_binaries=pdf_binaries if pdf_binaries else None,
                    cached_ai_baseline=ai_baseline_answers
                )
                
                logger.info(f"Successfully saved report {report_id} for job {job_id}")
                
            except Exception as e:
                error_msg = f"Failed to save report: {str(e)}"
                logger.error(f"Job {job_id}: {error_msg}")
                
                db_client.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": error_msg,
                        "completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                await self.email_service.send_job_failed_email(
                    to=job_data["from_email"],
                    job_id=job_id,
                    error=error_msg
                )
                
                return False
            
            # Step 9: Update email_jobs.report_id
            db_client.table("email_jobs")\
                .update({
                    "report_id": report_id,
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat()
                })\
                .eq("id", job_id)\
                .execute()
            
            logger.info(f"Updated job {job_id} with report_id {report_id}")
            
            # Step 10: Send notification with report URL
            from app.utils.urls import build_report_url
            report_url = build_report_url(report_id)
            
            try:
                await self.email_service.send_report_ready_email(
                    to=job_data["from_email"],
                    report_url=report_url,
                    report_name=report_name,
                    subject_text=job_data.get("subject", "your email")
                )
                logger.info(f"Sent report ready notification to {job_data['from_email']}")
            except Exception as email_error:
                # Log but don't fail the job - report was saved successfully
                logger.error(f"Failed to send notification email (report still saved): {email_error}")
            
            logger.info(f"✅ Successfully completed job {job_id} with report {report_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to process job {job_id}: {e}", exc_info=True)
            
            # Update job status to failed
            try:
                db_client.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": str(e),
                        "completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                # Send failure notification
                await self._send_processing_notification(
                    job_data,
                    success=False,
                    error_message=str(e)
                )
            
            except Exception as update_error:
                logger.error(f"Failed to update job status: {update_error}")
            
            return False
    
    def _generate_report_name(self, job_data: Dict[str, Any], agent) -> str:
        """
        Generate a descriptive report name from email job data.
        
        Format: "{Agent Name} - {subject}" or "{Agent Name} - {date}" if no subject
        
        Args:
            job_data: Email job metadata
            agent: Agent object used for report generation
            
        Returns:
            Generated report name
        """
        agent_name = agent.name
        
        # Try to use email subject as report name
        subject = job_data.get("subject", "").strip()
        
        if subject:
            # Truncate if too long
            max_length = 100
            if len(subject) > max_length:
                subject = subject[:max_length] + "..."
            return f"{agent_name} - {subject}"
        
        # Fallback: Use date
        created_at = job_data.get("created_at", datetime.utcnow().isoformat())
        try:
            date_obj = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_str = date_obj.strftime("%Y-%m-%d %H:%M")
        except:
            date_str = "Unknown Date"
        
        return f"{agent_name} - {date_str}"
    
    async def _send_processing_notification(
        self, 
        job_data: Dict[str, Any],
        success: bool,
        message: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Send email notification about job processing result."""
        try:
            sender_email = job_data["from_email"]
            subject = job_data.get("subject", "Your email")
            
            if success:
                self.email_service.send_report_ready_email(
                    to=sender_email,
                    report_url="",  # TODO: Add actual URL when report generation is implemented
                    report_name=message,
                    subject_text=subject
                )
                logger.info(f"Sent success notification to {sender_email}")
            else:
                self.email_service.send_job_failed_email(
                    to=sender_email,
                    job_id=job_data["id"],
                    error=error_message or "Unknown error occurred"
                )
                logger.info(f"Sent failure notification to {sender_email}")
        
        except Exception as e:
            logger.error(f"Failed to send notification email: {e}")
            # Don't fail the job if notification fails


# Global instance
_email_job_service = None

def get_email_job_service() -> EmailJobService:
    """Get or create the global email job service instance."""
    global _email_job_service
    if _email_job_service is None:
        _email_job_service = EmailJobService()
    return _email_job_service
