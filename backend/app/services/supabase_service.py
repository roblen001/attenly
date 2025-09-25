"""Supabase service for backend operations using user JWT tokens"""

import os
import logging
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
                   report_name: str, report_data: dict, document_contents: dict) -> str:
        """Save a complete report with document content to Supabase using user JWT"""
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
            
            # Insert document content records
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

# Global instance
supabase_service = SupabaseService()
