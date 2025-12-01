"""Supabase service for backend operations using user JWT tokens"""

import os
import logging
import base64
from typing import List, Dict, Optional, Any
from supabase import create_client, Client
from datetime import datetime
from app.services.diff_service import DiffService

class SupabaseService:
    def __init__(self):
        # Use the same environment variable names as the existing app config
        from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
        
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        self.supabase_url = SUPABASE_URL
        self.supabase_anon_key = SUPABASE_ANON_KEY
        self.supabase_service_key = SUPABASE_SERVICE_ROLE_KEY
        self.diff_service = DiffService()
        logging.info("Supabase service initialized with user JWT support and audit trail")

    def _create_user_client(self, user_jwt: str) -> Client:
        """Create a Supabase client with user JWT context for RLS compliance"""
        client = create_client(self.supabase_url, self.supabase_anon_key)
        # Set JWT for PostgREST calls (RLS will see auth.uid())
        client.postgrest.auth(user_jwt)  # Raw token, no "Bearer " prefix
        return client

    def save_report(self, user_jwt: str, user_id: str, agent_id: str, agent_name: str, 
                   report_name: str, report_data: dict, document_contents: dict, 
                   pdf_binaries: Optional[Dict[str, bytes]] = None,
                   refresh_token: str = "", existing_report_id: Optional[str] = None,
                   cached_ai_baseline: Optional[Dict[str, str]] = None) -> str:
        """
        Save a complete report with document content, PDF binaries, and audit trail.
        Uses user JWT for RLS-compliant access (web endpoints).
        
        This method now handles audit trail functionality:
        1. On first save: Uses cached AI baseline from report generation (or extracts from report_data as fallback)
        2. On update: Computes diff between baseline and current content
        3. Replaces old changes with fresh diff on each save
        
        Args:
            existing_report_id: If provided, updates existing report instead of creating new one
            cached_ai_baseline: Pre-captured AI baseline from report generation (for new saves)
        """
        try:
            # Create user-context client for RLS compliance
            user_client = self._create_user_client(user_jwt)
            
            # Use shared internal helper
            return self._save_report_internal(
                client=user_client,
                user_id=user_id,
                agent_id=agent_id,
                agent_name=agent_name,
                report_name=report_name,
                report_data=report_data,
                document_contents=document_contents,
                pdf_binaries=pdf_binaries,
                access_token=user_jwt,
                refresh_token=refresh_token,
                existing_report_id=existing_report_id,
                cached_ai_baseline=cached_ai_baseline
            )
        except Exception as e:
            logging.error(f"Error saving report to Supabase: {e}")
            raise

    def save_report_for_system(self, user_id: str, agent_id: str, agent_name: str,
                               report_name: str, report_data: dict, document_contents: dict,
                               pdf_binaries: Optional[Dict[str, bytes]] = None,
                               cached_ai_baseline: Optional[Dict[str, str]] = None) -> str:
        """
        Save a report using service role key (for background jobs like email processor).
        Bypasses RLS but manually enforces user_id ownership.
        
        Args:
            user_id: User ID for ownership
            agent_id: Agent ID
            agent_name: Agent display name
            report_name: Report name
            report_data: Report content
            document_contents: Document metadata
            pdf_binaries: PDF file bytes
            cached_ai_baseline: AI baseline for audit trail
            
        Returns:
            report_id: UUID of saved report
        """
        try:
            if not self.supabase_service_key:
                raise ValueError("Service role key not configured - cannot save reports from background jobs")
            
            # Create service role client (bypasses RLS)
            service_client = create_client(self.supabase_url, self.supabase_service_key)
            
            logging.info(f"Saving report for user {user_id} via service role (background job)")
            
            # Use shared internal helper
            return self._save_report_internal(
                client=service_client,
                user_id=user_id,
                agent_id=agent_id,
                agent_name=agent_name,
                report_name=report_name,
                report_data=report_data,
                document_contents=document_contents,
                pdf_binaries=pdf_binaries,
                access_token=self.supabase_service_key,  # Use service key for Storage
                refresh_token="",  # No refresh token in background jobs
                existing_report_id=None,  # Always create new reports from background jobs
                cached_ai_baseline=cached_ai_baseline
            )
        except Exception as e:
            logging.error(f"Error saving report via service role: {e}")
            raise

    def _save_report_internal(self, client: Client, user_id: str, agent_id: str, agent_name: str,
                              report_name: str, report_data: dict, document_contents: dict,
                              pdf_binaries: Optional[Dict[str, bytes]] = None,
                              access_token: str = "", refresh_token: str = "",
                              existing_report_id: Optional[str] = None,
                              cached_ai_baseline: Optional[Dict[str, str]] = None) -> str:
        """
        Internal helper for saving reports. Used by both user-context and system-context saves.
        
        Args:
            client: Supabase client (user-context or service role)
            user_id: User ID for ownership
            agent_id: Agent ID
            agent_name: Agent display name
            report_name: Report name
            report_data: Report content
            document_contents: Document metadata
            pdf_binaries: PDF file bytes
            access_token: JWT token or service key for Storage operations
            refresh_token: Refresh token for Storage (user-context only)
            existing_report_id: If provided, updates existing report
            cached_ai_baseline: AI baseline for audit trail
            
        Returns:
            report_id: UUID of saved report
        """
        try:
            is_update = existing_report_id is not None
            
            # For updates, fetch existing baseline
            existing_baseline = None
            if is_update:
                try:
                    existing_report = client.table("saved_reports")\
                        .select("ai_baseline_answers")\
                        .eq("id", existing_report_id)\
                        .eq("user_id", user_id)\
                        .single()\
                        .execute()
                    
                    if existing_report.data:
                        existing_baseline = existing_report.data.get("ai_baseline_answers")
                        logging.info(f"Found existing baseline for report {existing_report_id}")
                except Exception as e:
                    logging.warning(f"Could not fetch existing baseline: {e}")
            
            # Determine AI baseline to use
            ai_baseline_answers = None
            if is_update:
                # For updates, use existing baseline
                ai_baseline_answers = existing_baseline
                if ai_baseline_answers:
                    logging.info(f"Using existing baseline for report update")
            else:
                # For first save, prefer cached baseline (captured at generation time)
                if cached_ai_baseline:
                    ai_baseline_answers = cached_ai_baseline
                    logging.info(f"Using cached AI baseline from generation ({len(cached_ai_baseline)} answers)")
                else:
                    # Fallback: extract from report_data (shouldn't happen in normal flow)
                    ai_baseline_answers = self._extract_baseline_answers(report_data)
                    logging.warning(f"No cached baseline provided, extracting from report_data (may include user edits)")
            
            # Prepare report insert/update data
            report_data_dict = {
                "user_id": user_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "report_name": report_name,
                "report_data": report_data,
                "generated_at": report_data.get("generated_at")
            }
            
            # Add baseline for new saves (not updates)
            if not is_update and ai_baseline_answers:
                report_data_dict["ai_baseline_answers"] = ai_baseline_answers
            
            # Insert or update report record
            if is_update:
                result = client.table("saved_reports")\
                    .update(report_data_dict)\
                    .eq("id", existing_report_id)\
                    .eq("user_id", user_id)\
                    .execute()
                report_id = existing_report_id
                logging.info(f"Updated report with ID: {report_id} for user: {user_id}")
            else:
                result = client.table("saved_reports").insert(report_data_dict).execute()
                if not result.data:
                    raise Exception("Failed to insert report record")
                report_id = result.data[0]["id"]
                logging.info(f"Saved new report with ID: {report_id} for user: {user_id}")
            
            # Compute and store audit changes if we have baseline
            if ai_baseline_answers:
                try:
                    self._compute_and_store_changes(
                        client,
                        user_id, 
                        report_id,
                        ai_baseline_answers,
                        report_data
                    )
                except Exception as audit_error:
                    # Log but don't fail the save operation
                    logging.error(f"Failed to compute audit changes: {audit_error}")
            
            # Import Storage service for PDF uploads
            from app.services.supabase_storage_service import get_storage_service
            storage_service = get_storage_service()
            
            # Insert document content records with Storage uploads for PDFs
            for doc_id, doc_content in document_contents.items():
                doc_insert = {
                    "report_id": report_id,
                    "document_id": doc_id,
                    "filename": doc_content["filename"],
                    "metadata": doc_content["metadata"]
                }
                
                # Upload PDF to Storage if available (will be None for OCR documents)
                if pdf_binaries and doc_id in pdf_binaries:
                    pdf_bytes = pdf_binaries[doc_id]
                    
                    try:
                        # Upload to Supabase Storage with authenticated session
                        storage_metadata = storage_service.upload_document(
                            access_token=access_token,
                            refresh_token=refresh_token,
                            user_id=user_id,
                            document_id=doc_id,
                            pdf_bytes=pdf_bytes,
                            report_id=report_id
                        )
                        
                        # Store Storage metadata in database
                        doc_insert["storage_path"] = storage_metadata["storage_path"]
                        doc_insert["content_hash"] = storage_metadata["content_hash"]
                        doc_insert["storage_bucket"] = storage_metadata["bucket"]
                        doc_insert["stored_at"] = storage_metadata["stored_at"]
                        
                        logging.info(
                            f"Uploaded {doc_id} to Storage: {storage_metadata['storage_path']} "
                            f"({len(pdf_bytes)} bytes, duplicate: {storage_metadata.get('duplicate', False)})"
                        )
                    except Exception as e:
                        # Log error but don't fail the entire save operation
                        logging.error(f"Storage upload failed for {doc_id}: {e}")
                        # Document will be saved without PDF (storage_path will be NULL)
                else:
                    logging.info(f"No PDF binary for {doc_id} (likely OCR document)")
                
                doc_result = client.table("saved_report_documents").insert(doc_insert).execute()
                
                if not doc_result.data:
                    logging.warning(f"Failed to insert document content for {doc_id}")
                else:
                    logging.info(f"Saved document content for {doc_id}")
            
            return report_id
            
        except Exception as e:
            logging.error(f"Error saving report to Supabase: {e}")
            raise

    def get_user_reports(self, user_jwt: str, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Get list of user's saved reports using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            result = user_client.table("saved_reports")\
                .select("id, report_name, agent_name, agent_id, saved_at, generated_at")\
                .eq("user_id", user_id)\
                .order("saved_at", desc=True)\
                .limit(limit)\
                .offset(offset)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            logging.error(f"Error fetching user reports: {e}")
            raise

    def get_saved_report(self, user_jwt: str, user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific saved report with full data using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            result = user_client.table("saved_reports")\
                .select("*")\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .single()\
                .execute()
            
            return result.data
            
        except Exception as e:
            logging.error(f"Error fetching saved report {report_id}: {e}")
            return None

    def get_saved_document_content(self, user_jwt: str, user_id: str, report_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document content for a saved report using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # First verify the report belongs to the user (RLS will handle this automatically)
            report_result = user_client.table("saved_reports")\
                .select("id")\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .single()\
                .execute()
            
            if not report_result.data:
                logging.warning(f"Report {report_id} not found for user {user_id}")
                return None
            
            # Get document content (RLS will ensure user can only access their documents)
            doc_result = user_client.table("saved_report_documents")\
                .select("*")\
                .eq("report_id", report_id)\
                .eq("document_id", document_id)\
                .single()\
                .execute()
            
            if not doc_result.data:
                logging.warning(f"Document {document_id} not found for report {report_id}")
                return None
            
            doc_data = doc_result.data
            
            return {
                "document_id": doc_data["document_id"],
                "filename": doc_data["filename"],
                "metadata": doc_data["metadata"]
            }
            
        except Exception as e:
            logging.error(f"Error fetching document content: {e}")
            return None

    def get_saved_document_pdf(self, user_jwt: str, user_id: str, report_id: str, document_id: str) -> Optional[bytes]:
        """Get PDF binary for a saved report document from Supabase Storage using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # First verify the report belongs to the user (RLS will handle this automatically)
            report_result = user_client.table("saved_reports")\
                .select("id")\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .single()\
                .execute()
            
            if not report_result.data:
                logging.warning(f"Report {report_id} not found for user {user_id}")
                return None
            
            # Get Storage metadata (RLS will ensure user can only access their documents)
            doc_result = user_client.table("saved_report_documents")\
                .select("storage_path, content_hash")\
                .eq("report_id", report_id)\
                .eq("document_id", document_id)\
                .single()\
                .execute()
            
            if not doc_result.data:
                logging.warning(f"Document {document_id} not found for report {report_id}")
                return None
            
            storage_path = doc_result.data.get("storage_path")
            
            if not storage_path:
                logging.info(f"No Storage path available for document {document_id} (likely OCR document)")
                return None
            
            # Download from Supabase Storage with user JWT (RLS enforced)
            try:
                from app.services.supabase_storage_service import get_storage_service
                storage_service = get_storage_service()
                
                pdf_binary = storage_service.download_document(user_jwt, user_id, storage_path)
                
                # Verify content hash if available
                content_hash = doc_result.data.get("content_hash")
                if content_hash:
                    if not storage_service.verify_content_hash(pdf_binary, content_hash):
                        logging.error(f"Content hash mismatch for document {document_id}")
                        raise ValueError("Content verification failed")
                
                logging.info(f"Retrieved PDF from Storage: {storage_path} ({len(pdf_binary)} bytes)")
                return pdf_binary
                
            except Exception as download_error:
                logging.error(f"Failed to download PDF from Storage for document {document_id}: {download_error}")
                return None
            
        except Exception as e:
            logging.error(f"Error fetching PDF from Storage: {e}")
            return None

    def update_saved_report(self, user_jwt: str, user_id: str, report_id: str, report_data: Optional[Dict[str, Any]] = None, report_name: Optional[str] = None) -> bool:
        """
        Update a saved report's data and/or name using user JWT.
        
        When report_data is updated, this method also computes and stores
        audit trail changes by comparing the new data with the AI baseline.
        """
        try:
            user_client = self._create_user_client(user_jwt)
            update_fields: Dict[str, Any] = {}
            if report_data is not None:
                update_fields["report_data"] = report_data
            if report_name is not None:
                update_fields["report_name"] = report_name

            if not update_fields:
                logging.info("No fields provided to update for saved report")
                return False

            # If updating report_data, fetch existing baseline for audit trail computation
            ai_baseline_answers = None
            if report_data is not None:
                try:
                    existing_report = user_client.table("saved_reports")\
                        .select("ai_baseline_answers")\
                        .eq("id", report_id)\
                        .eq("user_id", user_id)\
                        .single()\
                        .execute()
                    
                    if existing_report.data:
                        ai_baseline_answers = existing_report.data.get("ai_baseline_answers")
                        logging.info(f"Fetched AI baseline for audit trail computation on report {report_id}")
                except Exception as e:
                    logging.warning(f"Could not fetch baseline for audit trail: {e}")

            # Update the report
            result = user_client.table("saved_reports")\
                .update(update_fields)\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .execute()

            if result.data:
                logging.info(f"Updated saved report {report_id} for user {user_id}")
                
                # Compute and store audit trail changes if we have baseline and report_data
                if report_data is not None and ai_baseline_answers:
                    try:
                        self._compute_and_store_changes(
                            user_client,
                            user_id,
                            report_id,
                            ai_baseline_answers,
                            report_data
                        )
                        logging.info(f"Successfully computed audit trail changes for report {report_id}")
                    except Exception as audit_error:
                        # Log but don't fail the update operation
                        logging.error(f"Failed to compute audit changes during update: {audit_error}")
                
                return True
            else:
                logging.warning(f"Update affected 0 rows for report {report_id} and user {user_id}")
                return False

        except Exception as e:
            logging.error(f"Error updating saved report {report_id}: {e}")
            return False

    def delete_saved_report(self, user_jwt: str, user_id: str, report_id: str, refresh_token: str = "") -> bool:
        """Delete a saved report, its associated documents, and PDFs from Storage using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # First, clean up PDFs from Storage before deleting database records
            from app.services.supabase_storage_service import get_storage_service
            storage_service = get_storage_service()
            
            try:
                deleted_count = storage_service.cleanup_report_documents(
                    access_token=user_jwt,
                    refresh_token=refresh_token,
                    user_id=user_id,
                    report_id=report_id
                )
                logging.info(f"Cleaned up {deleted_count} PDFs from Storage for report {report_id}")
            except Exception as storage_error:
                # Log storage cleanup error but continue with database deletion
                # This ensures orphaned DB records don't remain if storage fails
                logging.error(f"Failed to cleanup Storage for report {report_id}: {storage_error}")
            
            # Delete database records (cascade will delete saved_report_documents)
            result = user_client.table("saved_reports")\
                .delete()\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .execute()
            
            if result.data:
                logging.info(f"Deleted saved report {report_id} from database")
                return True
            else:
                logging.warning(f"Report {report_id} not found or not owned by user {user_id}")
                return False
                
        except Exception as e:
            logging.error(f"Error deleting saved report {report_id}: {e}")
            return False

    # Audit Trail Operations

    def _extract_baseline_answers(self, report_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract plain text answers from ReportData structure for baseline storage.
        
        Args:
            report_data: The full report data dictionary
            
        Returns:
            Dictionary mapping placeholder to answer text: {"placeholder": "answer_text"}
        """
        baseline = {}
        
        try:
            answers = report_data.get("answers", {})
            for placeholder, answer_data in answers.items():
                # Extract answer text (may be HTML)
                answer_text = answer_data.get("answer", "")
                baseline[placeholder] = answer_text
            
            logging.info(f"Extracted baseline for {len(baseline)} answers")
            return baseline
            
        except Exception as e:
            logging.error(f"Error extracting baseline answers: {e}")
            return {}

    def _compute_and_store_changes(
        self,
        user_client: Client,
        user_id: str,
        report_id: str,
        baseline_answers: Dict[str, str],
        current_report_data: Dict[str, Any]
    ) -> None:
        """
        Compute differences and store in report_changes table.
        
        This method:
        1. Deletes all existing changes for the report
        2. Computes fresh diff: baseline → current for each answer
        3. Inserts new changes into report_changes table
        
        Args:
            user_client: Supabase client with user context
            user_id: User ID for change attribution
            report_id: Report ID
            baseline_answers: Original AI-generated answers
            current_report_data: Current report data with potentially edited answers
        """
        try:
            # Extract current answers from report data
            current_answers = {}
            answers = current_report_data.get("answers", {})
            for placeholder, answer_data in answers.items():
                current_answers[placeholder] = answer_data.get("answer", "")
            
            # Delete existing changes for this report (we're replacing, not accumulating)
            user_client.table("report_changes")\
                .delete()\
                .eq("report_id", report_id)\
                .execute()
            
            logging.info(f"Deleted existing changes for report {report_id}")
            
            # Get user display name for attribution
            user_name = self.get_user_display_name("", user_id)
            
            # Compute diffs for each answer
            all_changes = []
            for placeholder, baseline_text in baseline_answers.items():
                # Get current text (default to baseline if answer was removed)
                current_text = current_answers.get(placeholder, baseline_text)
                
                # Skip if no change
                if not self.diff_service.has_changes(baseline_text, current_text):
                    continue
                
                # Compute diff for this answer
                changes = self.diff_service.compute_answer_diff(
                    baseline_text,
                    current_text,
                    placeholder
                )
                
                # Add user metadata to each change
                for change in changes:
                    change["report_id"] = report_id
                    change["user_id"] = user_id
                    change["user_name"] = user_name
                    # created_at will be auto-set by database
                
                all_changes.extend(changes)
            
            # Insert all changes in bulk if any exist
            if all_changes:
                user_client.table("report_changes").insert(all_changes).execute()
                logging.info(
                    f"Stored {len(all_changes)} changes across "
                    f"{len(set(c['answer_placeholder'] for c in all_changes))} answers"
                )
            else:
                logging.info(f"No changes detected for report {report_id}")
                
        except Exception as e:
            logging.error(f"Error computing/storing changes: {e}", exc_info=True)
            raise

    def get_user_display_name(self, user_jwt: str, user_id: str) -> str:
        """
        Get user display name for change attribution.
        Falls back to user ID if name not available.
        
        Args:
            user_jwt: User JWT token
            user_id: User ID
            
        Returns:
            User display name or user ID
        """
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Try to get user email from auth.users (may not have direct access)
            # For now, just use user_id as fallback
            # In production, you might query a users table or use Supabase Auth API
            return user_id
            
        except Exception as e:
            logging.warning(f"Could not get display name for user {user_id}: {e}")
            return user_id

    def get_report_with_audit_changes(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get report with all current changes for audit trail view.
        
        Args:
            user_jwt: User JWT token
            user_id: User ID
            report_id: Report ID
            
        Returns:
            Dictionary with structure:
            {
                "report_id": str,
                "report_name": str,
                "agent_name": str,
                "report_data": dict (with answer_plain added to each answer),
                "changes": {placeholder: [AuditChange, ...]},
                "has_changes": bool
            }
        """
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Get the saved report
            report_result = user_client.table("saved_reports")\
                .select("*")\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .single()\
                .execute()
            
            if not report_result.data:
                logging.warning(f"Report {report_id} not found for user {user_id}")
                return None
            
            report = report_result.data
            report_data = report["report_data"]
            
            # Add plain text version to each answer for frontend offset alignment
            if "answers" in report_data:
                for placeholder, answer_data in report_data["answers"].items():
                    answer_html = answer_data.get("answer", "")
                    # Use same HTML stripping logic as diff computation
                    answer_plain = self.diff_service.html_to_plain_text(answer_html)
                    answer_data["answer_plain"] = answer_plain
                    
                    logging.debug(
                        f"Added answer_plain for {placeholder}: "
                        f"HTML len={len(answer_html)}, plain len={len(answer_plain)}"
                    )
            
            # Get all changes for this report
            changes_result = user_client.table("report_changes")\
                .select("*")\
                .eq("report_id", report_id)\
                .order("answer_placeholder")\
                .order("start_offset")\
                .execute()
            
            # Group changes by answer placeholder
            changes_by_placeholder: Dict[str, List[Dict[str, Any]]] = {}
            for change in changes_result.data or []:
                placeholder = change["answer_placeholder"]
                if placeholder not in changes_by_placeholder:
                    changes_by_placeholder[placeholder] = []
                
                changes_by_placeholder[placeholder].append({
                    "id": change["id"],
                    "change_type": change["change_type"],
                    "text_content": change["text_content"],
                    "start_offset": change["start_offset"],
                    "end_offset": change["end_offset"],
                    "user_name": change.get("user_name", user_id),
                    "created_at": change["created_at"],
                    "answer_placeholder": placeholder
                })
            
            has_changes = len(changes_result.data or []) > 0
            
            result = {
                "report_id": report["id"],
                "report_name": report["report_name"],
                "agent_name": report["agent_name"],
                "report_data": report_data,
                "changes": changes_by_placeholder,
                "has_changes": has_changes
            }
            
            logging.info(
                f"Fetched audit data for report {report_id}: "
                f"{len(changes_by_placeholder)} placeholders with changes"
            )
            
            return result
            
        except Exception as e:
            logging.error(f"Error fetching report with audit changes: {e}")
            return None

    # Custom Agent CRUD Operations
    
    def create_custom_agent(self, user_jwt: str, user_id: str, created_by_name: str, 
                           name: str, description: str, report_template: str, 
                           questions: List[Dict[str, str]]) -> str:
        """Create a new custom agent with questions using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Insert agent record
            agent_insert = {
                "name": name,
                "description": description,
                "report_template": report_template,
                "user_id": user_id,
                "is_custom": True,
                "created_by_name": created_by_name
            }
            
            result = user_client.table("agents").insert(agent_insert).execute()
            
            if not result.data:
                raise Exception("Failed to insert agent record")
            
            agent_id = result.data[0]["id"]
            logging.info(f"Created custom agent with ID: {agent_id} for user: {user_id}")
            
            # Insert questions
            if questions:
                question_inserts = []
                for question in questions:
                    question_inserts.append({
                        "agent_id": agent_id,
                        "placeholder": question["placeholder"],
                        "prompt": question["prompt"]
                    })
                
                questions_result = user_client.table("agent_questions").insert(question_inserts).execute()
                
                if not questions_result.data:
                    logging.warning(f"Failed to insert questions for agent {agent_id}")
                else:
                    logging.info(f"Created {len(questions_result.data)} questions for agent {agent_id}")
            
            return str(agent_id)
            
        except Exception as e:
            logging.error(f"Error creating custom agent: {e}")
            raise

    def get_user_custom_agents(self, user_jwt: str, user_id: str) -> List[Dict[str, Any]]:
        """Get user's custom agents with questions using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Get agents with their questions
            result = user_client.table("agents")\
                .select("*, agent_questions(*)")\
                .eq("user_id", user_id)\
                .eq("is_custom", True)\
                .order("created_at", desc=True)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            logging.error(f"Error fetching user custom agents: {e}")
            raise

    def get_agent_by_id(self, user_jwt: str, user_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific agent by ID with questions using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            result = user_client.table("agents")\
                .select("*, agent_questions(*)")\
                .eq("id", agent_id)\
                .single()\
                .execute()
            
            return result.data
            
        except Exception as e:
            logging.error(f"Error fetching agent {agent_id}: {e}")
            return None

    def get_agent_by_id_system(self, agent_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific custom agent by ID using service role key (bypasses RLS).
        
        This method is used by background jobs (email processor) that don't have
        user JWT context. It uses the service role key to access custom agents
        while still verifying user ownership.
        
        Args:
            agent_id: Agent UUID
            user_id: User ID for ownership verification
            
        Returns:
            Agent data dictionary with questions, or None if not found
        """
        try:
            if not self.supabase_service_key:
                logging.error("Service role key not configured - cannot access custom agents in background jobs")
                return None
            
            # Create service role client (bypasses RLS)
            service_client = create_client(self.supabase_url, self.supabase_service_key)
            
            # Query agent with user_id filter (ensures user owns the agent)
            result = service_client.table("agents")\
                .select("*, agent_questions(*)")\
                .eq("id", agent_id)\
                .eq("user_id", user_id)\
                .eq("is_custom", True)\
                .single()\
                .execute()
            
            if result.data:
                logging.info(f"Loaded custom agent {agent_id} for user {user_id} via service role")
            
            return result.data
            
        except Exception as e:
            logging.warning(f"Error fetching agent {agent_id} via service role: {e}")
            return None

    def update_custom_agent(self, user_jwt: str, user_id: str, agent_id: str,
                           name: Optional[str] = None, description: Optional[str] = None,
                           report_template: Optional[str] = None, 
                           questions: Optional[List[Dict[str, str]]] = None) -> bool:
        """Update a custom agent and optionally its questions using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Update agent fields
            update_fields = {"updated_at": datetime.now().isoformat()}
            if name is not None:
                update_fields["name"] = name
            if description is not None:
                update_fields["description"] = description
            if report_template is not None:
                update_fields["report_template"] = report_template
            
            result = user_client.table("agents")\
                .update(update_fields)\
                .eq("id", agent_id)\
                .eq("user_id", user_id)\
                .eq("is_custom", True)\
                .execute()
            
            if not result.data:
                logging.warning(f"Agent {agent_id} not found or not owned by user {user_id}")
                return False
            
            # Update questions if provided
            if questions is not None:
                # Delete existing questions
                user_client.table("agent_questions")\
                    .delete()\
                    .eq("agent_id", agent_id)\
                    .execute()
                
                # Insert new questions
                if questions:
                    question_inserts = []
                    for question in questions:
                        question_inserts.append({
                            "agent_id": agent_id,
                            "placeholder": question["placeholder"],
                            "prompt": question["prompt"]
                        })
                    
                    user_client.table("agent_questions").insert(question_inserts).execute()
            
            logging.info(f"Updated custom agent {agent_id} for user {user_id}")
            return True
            
        except Exception as e:
            logging.error(f"Error updating custom agent {agent_id}: {e}")
            return False

    def delete_custom_agent(self, user_jwt: str, user_id: str, agent_id: str) -> bool:
        """Delete a custom agent and its questions using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Delete agent (questions will be deleted by cascade)
            result = user_client.table("agents")\
                .delete()\
                .eq("id", agent_id)\
                .eq("user_id", user_id)\
                .eq("is_custom", True)\
                .execute()
            
            if result.data:
                logging.info(f"Deleted custom agent {agent_id}")
                return True
            else:
                logging.warning(f"Agent {agent_id} not found or not owned by user {user_id}")
                return False
                
        except Exception as e:
            logging.error(f"Error deleting custom agent {agent_id}: {e}")
            return False

# Global instance
supabase_service = SupabaseService()
