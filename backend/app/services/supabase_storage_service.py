"""
Supabase Storage Service for PDF Document Management

Handles all Supabase Storage operations with proper RLS security:
- Upload PDFs with content-addressed naming (SHA-256 hash)
- Generate signed URLs for temporary secure access
- Download PDFs from Storage
- Delete PDFs from Storage
- Verify file integrity with content-hash verification

All operations use user JWT tokens to enforce Row Level Security policies.
"""

import logging
import hashlib
from typing import Dict, Optional, Any
from datetime import datetime

try:
    from storage3 import SyncStorageClient as StorageClient
except ImportError:
    StorageClient = None


class SupabaseStorageService:
    """Service for managing PDF documents in Supabase Storage with RLS enforcement"""
    
    def __init__(self):
        """Initialize Storage service with Supabase credentials"""
        from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY are required for Storage service")

        if not SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required for service operations")

        self.supabase_url = SUPABASE_URL
        self.supabase_anon_key = SUPABASE_ANON_KEY
        self.supabase_service_role_key = SUPABASE_SERVICE_ROLE_KEY
        self.bucket_name = "report-documents"

        logging.info("Supabase Storage service initialized with RLS enforcement")
    
    
    def _require_storage_client_class(self):
        if StorageClient is None:
            raise RuntimeError("storage3 SDK is not installed")
        return StorageClient

    def _create_storage_client(self, access_token: str) -> Any:
        """
        Create a dedicated Storage client with explicit authentication headers
        for RLS enforcement.
        
        Args:
            access_token: User's access token (JWT)
            
        Returns:
            StorageClient configured with Authorization and apikey headers
        """
        storage_client_class = self._require_storage_client_class()
        return storage_client_class(
            f"{self.supabase_url}/storage/v1",
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": self.supabase_anon_key,
                "X-Client-Info": "storage3/py-explicit",
            },
        )

    def _create_service_role_storage_client(self) -> Any:
        storage_client_class = self._require_storage_client_class()
        return storage_client_class(
            f"{self.supabase_url}/storage/v1",
            headers={
                "Authorization": f"Bearer {self.supabase_service_role_key}",
                "apikey": self.supabase_anon_key,
                "X-Client-Info": "storage3/py-service-role",
            },
        )
    
    def _calculate_content_hash(self, pdf_bytes: bytes) -> str:
        """
        Calculate SHA-256 hash of PDF content
        
        Args:
            pdf_bytes: Raw PDF binary data
            
        Returns:
            Hexadecimal SHA-256 hash string
        """
        return hashlib.sha256(pdf_bytes).hexdigest()
    
    def _construct_storage_path(self, user_id: str, report_id: str, content_hash: str) -> str:
        """
        Construct storage path for PDF file
        
        Path structure: {user_id}/{report_id}/{content_hash}.pdf
        
        Args:
            user_id: User identifier
            report_id: Report identifier
            content_hash: SHA-256 hash of PDF content
            
        Returns:
            Storage path string
        """
        return f"{user_id}/{report_id}/{content_hash}.pdf"
    
    def upload_document(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str,
        document_id: str,
        pdf_bytes: bytes,
        report_id: str
    ) -> Dict[str, str]:
        """
        Upload PDF to Supabase Storage with content-addressed naming.

        Uses SHA-256 hash for deduplication and enforces RLS policies.

        Args:
            access_token: User's JWT access token
            refresh_token: User's refresh token (unused, kept for API compatibility)
            user_id: User ID for path isolation
            document_id: Document identifier
            pdf_bytes: Raw PDF binary data
            report_id: Report ID for organization

        Returns:
            Dictionary with storage metadata including storage_path and content_hash

        Raises:
            ValueError: If upload fails or RLS rejects
        """
        try:
            # Calculate content hash
            content_hash = self._calculate_content_hash(pdf_bytes)

            # Construct storage path
            storage_path = self._construct_storage_path(user_id, report_id, content_hash)

            # Create Storage client with JWT authentication
            storage = self._create_storage_client(access_token)

            # Check if file already exists (deduplication)
            try:
                existing_file = storage.from_(self.bucket_name).list(
                    path=f"{user_id}/{report_id}"
                )

                file_exists = any(
                    file.get("name") == f"{content_hash}.pdf"
                    for file in existing_file
                )

                if file_exists:
                    logging.info(f"File already exists in Storage: {storage_path}")
                    return {
                        "storage_path": storage_path,
                        "content_hash": content_hash,
                        "bucket": self.bucket_name,
                        "stored_at": datetime.now().isoformat(),
                        "duplicate": True
                    }
            except Exception as e:
                logging.warning(f"Failed to check for existing file: {e}")

            # Upload to Storage
            response = storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=pdf_bytes,
                file_options={
                    "contentType": "application/pdf",  # camelCase required by storage3
                    "upsert": "false"  # string expected by API
                }
            )

            if hasattr(response, 'error') and response.error:
                raise ValueError(f"Storage upload failed: {response.error}")

            logging.info(f"Uploaded PDF to Storage: {storage_path} ({len(pdf_bytes)} bytes)")

            return {
                "storage_path": storage_path,
                "content_hash": content_hash,
                "bucket": self.bucket_name,
                "stored_at": datetime.now().isoformat(),
                "duplicate": False
            }

        except Exception as e:
            logging.error(f"Failed to upload document {document_id}: {e}")
            raise

    def upload_document_for_user(
        self,
        user_id: str,
        document_id: str,
        pdf_bytes: bytes,
        report_id: str,
        content_type: str = "application/pdf"
    ) -> Dict[str, str]:
        """
        Upload document using service role key (for system operations like webhooks).

        Reuses the same core logic as upload_document() but bypasses RLS for system operations.
        Use same content-addressed naming, deduplication, and metadata structure.

        Args:
            user_id: User ID for path isolation
            document_id: Document identifier
            pdf_bytes: Raw file binary data
            report_id: Report ID for organization
            content_type: MIME type of the file

        Returns:
            Dictionary with storage metadata (same format as upload_document)
        """
        try:
            # Calculate content hash
            content_hash = self._calculate_content_hash(pdf_bytes)

            # Construct storage path (same format as user-uploaded files)
            storage_path = self._construct_storage_path(user_id, report_id, content_hash)

            # Create Storage client with service role key (bypasses RLS for system operations)
            storage = self._create_service_role_storage_client()

            # Check if file already exists (deduplication)
            try:
                existing_file = storage.from_(self.bucket_name).list(
                    path=f"{user_id}/{report_id}"
                )

                file_exists = any(
                    file.get("name") == f"{content_hash}.pdf"
                    for file in existing_file
                )

                if file_exists:
                    logging.info(f"File already exists in Storage: {storage_path} (email attachment)")
                    return {
                        "storage_path": storage_path,
                        "content_hash": content_hash,
                        "bucket": self.bucket_name,
                        "stored_at": datetime.now().isoformat(),
                        "duplicate": True
                    }
            except Exception as e:
                logging.warning(f"Failed to check for existing email attachment file: {e}")

            # Upload to Storage with service role key
            response = storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=pdf_bytes,
                file_options={
                    "contentType": content_type,  # Use provided content type
                    "upsert": "false"
                }
            )

            if hasattr(response, 'error') and response.error:
                raise ValueError(f"Storage upload failed for email attachment: {response.error}")

            logging.info(f"Uploaded email attachment to Storage: {storage_path} ({len(pdf_bytes)} bytes)")

            return {
                "storage_path": storage_path,
                "content_hash": content_hash,
                "bucket": self.bucket_name,
                "stored_at": datetime.now().isoformat(),
                "duplicate": False
            }

        except Exception as e:
            logging.error(f"Failed to upload email attachment {document_id}: {e}")
            raise
    
    def get_signed_url(
        self, 
        access_token: str,
        refresh_token: str,
        user_id: str, 
        storage_path: str, 
        expiry_seconds: int = 3600
    ) -> str:
        """
        Generate temporary signed URL for secure document access.
        
        Args:
            access_token: User's JWT access token
            refresh_token: User's refresh token (unused, kept for API compatibility)
            user_id: User ID for access verification
            storage_path: Storage path from database
            expiry_seconds: URL validity period (default 1 hour)
            
        Returns:
            Signed URL string valid for expiry_seconds
            
        Raises:
            ValueError: If user doesn't own document or RLS rejects
        """
        try:
            # Verify user owns this document (path-based security)
            if not storage_path.startswith(f"{user_id}/"):
                raise ValueError(
                    f"Access denied: User {user_id} does not own document at {storage_path}"
                )
            
            # Create dedicated Storage client with explicit headers for RLS enforcement
            storage = self._create_storage_client(access_token)
            
            # Generate signed URL with dedicated storage client (RLS enforced)
            response = storage.from_(self.bucket_name).create_signed_url(
                path=storage_path,
                expires_in=expiry_seconds
            )
            
            # Check for errors
            if hasattr(response, 'error') and response.error:
                raise ValueError(f"Failed to generate signed URL: {response.error}")
            
            # Extract signed URL
            signed_url = response.get("signedURL")
            if not signed_url:
                raise ValueError("No signed URL returned from Storage")
            
            logging.info(
                f"Generated signed URL for {storage_path} "
                f"(expires in {expiry_seconds}s)"
            )
            
            return signed_url
            
        except Exception as e:
            logging.error(f"Failed to generate signed URL for {storage_path}: {e}")
            raise
    
    def download_document(self, access_token: str, refresh_token: str, user_id: str, storage_path: str) -> bytes:
        """
        Download PDF from Storage.
        
        Args:
            access_token: User's JWT access token
            refresh_token: User's refresh token (unused, kept for API compatibility)
            user_id: User ID for access verification
            storage_path: Storage path from database
            
        Returns:
            PDF binary data as bytes
            
        Raises:
            ValueError: If user doesn't own document or download fails
        """
        try:
            # Verify user owns this document (path-based security)
            if not storage_path.startswith(f"{user_id}/"):
                raise ValueError(
                    f"Access denied: User {user_id} does not own document at {storage_path}"
                )
            
            # Create dedicated Storage client with explicit headers for RLS enforcement
            storage = self._create_storage_client(access_token)
            
            # Download from Storage with dedicated storage client (RLS enforced)
            response = storage.from_(self.bucket_name).download(
                path=storage_path
            )
            
            # Check for errors
            if hasattr(response, 'error') and response.error:
                raise ValueError(f"Storage download failed: {response.error}")
            
            logging.info(f"Downloaded PDF from Storage: {storage_path} ({len(response)} bytes)")
            
            return response
            
        except Exception as e:
            logging.error(f"Failed to download document from {storage_path}: {e}")
            raise

    def download_document_for_system(self, user_id: str, storage_path: str) -> bytes:
        """
        Download document using service role key (for system operations like cron jobs).

        Args:
            user_id: User ID for path verification
            storage_path: Storage path from database

        Returns:
            PDF binary data as bytes
        """
        try:
            # Verify path belongs to user (basic path-based security)
            if not storage_path.startswith(f"{user_id}/"):
                raise ValueError(
                    f"Access denied: Path {storage_path} does not belong to user {user_id}"
                )

            # Create Storage client with service role key for system operations
            storage = self._create_service_role_storage_client()

            # Download from Storage with service role key (bypasses RLS)
            response = storage.from_(self.bucket_name).download(
                path=storage_path
            )

            # Check for errors
            if hasattr(response, 'error') and response.error:
                raise ValueError(f"Storage download failed: {response.error}")

            logging.info(f"Downloaded document from Storage (system): {storage_path} ({len(response)} bytes)")

            return response

        except Exception as e:
            logging.error(f"Failed to download document from {storage_path}: {e}")
            raise
    
    def delete_document(self, access_token: str, refresh_token: str, user_id: str, storage_path: str) -> bool:
        """
        Delete document from Storage.
        
        Args:
            access_token: User's JWT access token
            refresh_token: User's refresh token (unused, kept for API compatibility)
            user_id: User ID for access verification
            storage_path: Storage path from database
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            # Verify user owns this document (path-based security)
            if not storage_path.startswith(f"{user_id}/"):
                raise ValueError(
                    f"Access denied: User {user_id} does not own document at {storage_path}"
                )
            
            # Create dedicated Storage client with explicit headers for RLS enforcement
            storage = self._create_storage_client(access_token)
            
            # Delete from Storage with dedicated storage client (RLS enforced)
            response = storage.from_(self.bucket_name).remove(
                paths=[storage_path]
            )
            
            # Check for errors
            if hasattr(response, 'error') and response.error:
                logging.error(f"Storage deletion failed: {response.error}")
                return False
            
            logging.info(f"Deleted PDF from Storage: {storage_path}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to delete document from {storage_path}: {e}")
            return False
    
    def cleanup_report_documents(self, access_token: str, refresh_token: str, user_id: str, report_id: str) -> int:
        """
        Delete all documents for a report from Storage.
        
        Args:
            access_token: User's JWT access token
            refresh_token: User's refresh token (unused, kept for API compatibility)
            user_id: User ID for access verification
            report_id: Report ID to clean up
            
        Returns:
            Number of files deleted
        """
        try:
            # Create dedicated Storage client with explicit headers for RLS enforcement
            storage = self._create_storage_client(access_token)
            
            # List all files in report directory with dedicated storage client (RLS enforced)
            folder_path = f"{user_id}/{report_id}"
            files = storage.from_(self.bucket_name).list(path=folder_path)
            
            if not files:
                logging.info(f"No files found to clean up for report {report_id}")
                return 0
            
            # Construct full paths for deletion
            file_paths = [f"{folder_path}/{file['name']}" for file in files]
            
            # Delete all files with dedicated storage client (RLS enforced)
            response = storage.from_(self.bucket_name).remove(paths=file_paths)
            
            # Check for errors
            if hasattr(response, 'error') and response.error:
                logging.error(f"Storage cleanup failed: {response.error}")
                return 0
            
            deleted_count = len(file_paths)
            logging.info(
                f"Cleaned up {deleted_count} documents from Storage for report {report_id}"
            )
            return deleted_count
            
        except Exception as e:
            logging.error(f"Failed to cleanup report {report_id} documents: {e}")
            return 0
    
    def verify_content_hash(self, pdf_bytes: bytes, expected_hash: str) -> bool:
        """
        Verify PDF content matches expected hash
        
        Args:
            pdf_bytes: PDF binary data to verify
            expected_hash: Expected SHA-256 hash
            
        Returns:
            True if hash matches, False otherwise
        """
        actual_hash = self._calculate_content_hash(pdf_bytes)
        matches = actual_hash == expected_hash
        
        if not matches:
            logging.warning(
                f"Content hash mismatch: expected {expected_hash[:8]}..., "
                f"got {actual_hash[:8]}..."
            )
        
        return matches


# Global service instance
_storage_service_instance: Optional[SupabaseStorageService] = None


def get_storage_service() -> SupabaseStorageService:
    """
    Get or create global Storage service instance (singleton pattern)
    
    Returns:
        SupabaseStorageService instance
    """
    global _storage_service_instance
    
    if _storage_service_instance is None:
        _storage_service_instance = SupabaseStorageService()
    
    return _storage_service_instance
