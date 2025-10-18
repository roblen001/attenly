"""Supabase service for backend operations using user JWT tokens"""

import os
import logging
import base64
from typing import List, Dict, Optional, Any
from supabase import create_client, Client
from datetime import datetime

class SupabaseService:
    def __init__(self):
        # Use the same environment variable names as the existing app config
        from app.config import SUPABASE_URL, SUPABASE_ANON_KEY
        
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        self.supabase_url = SUPABASE_URL
        self.supabase_anon_key = SUPABASE_ANON_KEY
        logging.info("Supabase service initialized with user JWT support")

    def _create_user_client(self, user_jwt: str) -> Client:
        """Create a Supabase client with user JWT context for RLS compliance"""
        client = create_client(self.supabase_url, self.supabase_anon_key)
        # Set JWT for PostgREST calls (RLS will see auth.uid())
        client.postgrest.auth(user_jwt)  # Raw token, no "Bearer " prefix
        return client

    def save_report(self, user_jwt: str, user_id: str, agent_id: str, agent_name: str, 
                   report_name: str, report_data: dict, document_contents: dict, 
                   pdf_binaries: Optional[Dict[str, bytes]] = None) -> str:
        """Save a complete report with document content and PDF binaries to Supabase using user JWT"""
        try:
            # Create user-context client for RLS compliance
            user_client = self._create_user_client(user_jwt)
            
            # Insert main report record
            report_insert = {
                "user_id": user_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "report_name": report_name,
                "report_data": report_data,
                "generated_at": report_data.get("generated_at")
            }
            
            result = user_client.table("saved_reports").insert(report_insert).execute()
            
            if not result.data:
                raise Exception("Failed to insert report record")
            
            report_id = result.data[0]["id"]
            logging.info(f"Saved report with ID: {report_id} for user: {user_id}")
            
            # Insert document content records with optional PDF binaries
            for doc_id, doc_content in document_contents.items():
                doc_insert = {
                    "report_id": report_id,
                    "document_id": doc_id,
                    "filename": doc_content["filename"],
                    "full_text": doc_content["full_text"],
                    "pages_info": doc_content["pages"],
                    "total_pages": doc_content["total_pages"],
                    "total_characters": doc_content["total_characters"],
                    "metadata": doc_content["metadata"]
                }
                
                # Add PDF binary if available (will be None for OCR documents)
                # Base64 encode the binary data for JSON serialization
                if pdf_binaries and doc_id in pdf_binaries:
                    pdf_bytes = pdf_binaries[doc_id]
                    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                    doc_insert["pdf_binary"] = pdf_base64
                    logging.info(f"Saving PDF binary for {doc_id} ({len(pdf_bytes)} bytes, {len(pdf_base64)} chars base64)")
                else:
                    logging.info(f"No PDF binary for {doc_id} (likely OCR document)")
                
                doc_result = user_client.table("saved_report_documents").insert(doc_insert).execute()
                
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
            
            # Format response to match existing DocumentContent structure
            return {
                "document_id": doc_data["document_id"],
                "filename": doc_data["filename"],
                "full_text": doc_data["full_text"],
                "pages": doc_data["pages_info"],
                "total_pages": doc_data["total_pages"],
                "total_characters": doc_data["total_characters"],
                "metadata": doc_data["metadata"]
            }
            
        except Exception as e:
            logging.error(f"Error fetching document content: {e}")
            return None

    def get_saved_document_pdf(self, user_jwt: str, user_id: str, report_id: str, document_id: str) -> Optional[bytes]:
        """Get PDF binary for a saved report document using user JWT"""
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
            
            # Get PDF binary (RLS will ensure user can only access their documents)
            doc_result = user_client.table("saved_report_documents")\
                .select("pdf_binary")\
                .eq("report_id", report_id)\
                .eq("document_id", document_id)\
                .single()\
                .execute()
            
            if not doc_result.data:
                logging.warning(f"Document {document_id} not found for report {report_id}")
                return None
            
            pdf_base64 = doc_result.data.get("pdf_binary")
            
            if pdf_base64 is None:
                logging.info(f"No PDF binary available for document {document_id} (likely OCR document or pre-migration report)")
                return None
            
            # Decode base64 string back to bytes
            try:
                pdf_binary = base64.b64decode(pdf_base64)
                logging.info(f"Retrieved and decoded PDF binary for document {document_id} ({len(pdf_binary)} bytes)")
                return pdf_binary
            except Exception as decode_error:
                logging.error(f"Failed to decode PDF binary for document {document_id}: {decode_error}")
                return None
            
        except Exception as e:
            logging.error(f"Error fetching PDF binary: {e}")
            return None

    def update_saved_report(self, user_jwt: str, user_id: str, report_id: str, report_data: Optional[Dict[str, Any]] = None, report_name: Optional[str] = None) -> bool:
        """Update a saved report's data and/or name using user JWT"""
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

            result = user_client.table("saved_reports")\
                .update(update_fields)\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .execute()

            if result.data:
                logging.info(f"Updated saved report {report_id} for user {user_id}")
                return True
            else:
                logging.warning(f"Update affected 0 rows for report {report_id} and user {user_id}")
                return False

        except Exception as e:
            logging.error(f"Error updating saved report {report_id}: {e}")
            return False

    def delete_saved_report(self, user_jwt: str, user_id: str, report_id: str) -> bool:
        """Delete a saved report and its associated documents using user JWT"""
        try:
            user_client = self._create_user_client(user_jwt)
            
            # Verify ownership and delete (RLS will handle access control)
            result = user_client.table("saved_reports")\
                .delete()\
                .eq("id", report_id)\
                .eq("user_id", user_id)\
                .execute()
            
            if result.data:
                logging.info(f"Deleted saved report {report_id}")
                return True
            else:
                logging.warning(f"Report {report_id} not found or not owned by user {user_id}")
                return False
                
        except Exception as e:
            logging.error(f"Error deleting saved report {report_id}: {e}")
            return False

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
