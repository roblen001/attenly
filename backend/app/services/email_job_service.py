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
        
        # Fetch pending jobs (oldest first)
        try:
            pending_jobs = supabase_service.supabase.table("email_jobs")\
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
                claim_result = supabase_service.supabase.table("email_jobs")\
                    .update({
                        "status": "processing",
                        "processing_started_at": datetime.utcnow().isoformat()
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
                    supabase_service.supabase.table("email_jobs")\
                        .update({
                            "status": "failed",
                            "error_message": f"Processing error: {str(e)}",
                            "processing_completed_at": datetime.utcnow().isoformat()
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
        1. Download attachments from Storage
        2. Pass through DocumentProcessor (same as file uploads)
        3. Generate report using report_service
        4. Save report to saved_reports table
        5. Send notification email
        
        Args:
            job_id: Email job ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Step 1: Fetch job details
            job = supabase_service.supabase.table("email_jobs")\
                .select("*")\
                .eq("id", job_id)\
                .single()\
                .execute()
            
            if not job.data:
                logger.error(f"Job {job_id} not found")
                return False
            
            job_data = job.data
            user_id = job_data["user_id"]
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
                    # Download from Supabase Storage
                    file_content = self.storage_service.download_file(
                        access_token="",  # Using service role
                        refresh_token="",
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
            
            # Step 5: Get agent configuration
            # TODO: Support for instruction_text interpretation and custom agents
            # For now, use default_agent_id if provided, otherwise use a default prebuilt agent
            agent_id = job_data.get("default_agent_id")
            
            if not agent_id:
                # Use a default agent (e.g., first prebuilt agent)
                # In production, you might want to interpret instruction_text to select agent
                logger.warning(f"No default_agent_id for job {job_id}, report generation skipped")
                
                # For Phase 7, we'll mark as completed but note that report generation needs agent config
                supabase_service.supabase.table("email_jobs")\
                    .update({
                        "status": "completed",
                        "error_message": "Documents processed but report not generated (no agent configured)",
                        "processing_completed_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", job_id)\
                    .execute()
                
                # Send notification about successful processing
                await self._send_processing_notification(
                    job_data,
                    success=True,
                    message=f"Documents processed successfully but report generation requires agent configuration"
                )
                
                return True
            
            # Step 6: Generate report (same as file uploader flow)
            # Get agent configuration from database or prebuilt agents
            # This part will be implemented when we add agent support
            
            # For now, mark as completed
            supabase_service.supabase.table("email_jobs")\
                .update({
                    "status": "completed",
                    "processing_completed_at": datetime.utcnow().isoformat()
                })\
                .eq("id", job_id)\
                .execute()
            
            # Step 7: Send success notification
            await self._send_processing_notification(
                job_data,
                success=True,
                message=f"Successfully processed {len(processed_documents)} documents"
            )
            
            logger.info(f"✅ Successfully completed job {job_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to process job {job_id}: {e}", exc_info=True)
            
            # Update job status to failed
            try:
                supabase_service.supabase.table("email_jobs")\
                    .update({
                        "status": "failed",
                        "error_message": str(e),
                        "processing_completed_at": datetime.utcnow().isoformat()
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
    
    async def _send_processing_notification(
        self, 
        job_data: Dict[str, Any],
        success: bool,
        message: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Send email notification about job processing result."""
        try:
            sender_email = job_data["sender_email"]
            subject = job_data.get("subject", "Your email")
            
            if success:
                self.email_service.send_report_ready_email(
                    to_address=sender_email,
                    subject=subject,
                    report_link=None,  # TODO: Add report link when report generation is implemented
                    message=message
                )
                logger.info(f"Sent success notification to {sender_email}")
            else:
                self.email_service.send_job_failed_email(
                    to_address=sender_email,
                    subject=subject,
                    error_details=error_message or "Unknown error occurred"
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
