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
from typing import Dict, Optional
from datetime import datetime
from supabase import create_client, Client
from storage3 import SyncStorageClient as StorageClient


class SupabaseStorageService:
    """Service for managing PDF documents in Supabase Storage with RLS enforcement"""
    
    def __init__(self):
        """Initialize Storage service with Supabase credentials"""
        from app.config import SUPABASE_URL, SUPABASE_ANON_KEY
        
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY are required for Storage service")
        
        self.supabase_url = SUPABASE_URL
        self.supabase_anon_key = SUPABASE_ANON_KEY
        self.bucket_name = "report-documents"
        
        logging.info("Supabase Storage service initialized with RLS enforcement")
    
    def _create_user_client(self, access_token: str, refresh_token: str) -> Client:
        """
        Create a Supabase client with authenticated session for RLS compliance
        
        Properly authenticates both PostgREST and Storage operations by:
        1. Passing Authorization header through ClientOptions (for Storage)
        2. Using set_session() for auth state management (for PostgREST)
        
        Args:
            access_token: User's access token (JWT)
            refresh_token: User's refresh token
            
        Returns:
            Supabase client configured with authenticated session for both database and Storage
        """
        # DEBUG: Log token information
        logging.info(f"🔐 Creating user client:")
        logging.info(f"   - access_token present: {bool(access_token)}, length: {len(access_token) if access_token else 0}")
        logging.info(f"   - refresh_token present: {bool(refresh_token)}, length: {len(refresh_token) if refresh_token else 0}")
        
        # CRITICAL: Pass Authorization header through ClientOptions
        # This ensures storage3 client has the JWT token for RLS enforcement
        from supabase.lib.client_options import ClientOptions
        
        options = ClientOptions(
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Client-Info": "supabase-py/2.3.0"  # Preserve default header
            }
        )
        
        logging.info("🔐 Creating client with Authorization header in options...")
        client = create_client(self.supabase_url, self.supabase_anon_key, options)
        
        # Use set_session() for auth state management (PostgREST)
        try:
            logging.info("🔐 Calling auth.set_session()...")
            client.auth.set_session(access_token, refresh_token)
            logging.info("✓ set_session() completed successfully")
            
            # Verify session was set
            current_session = client.auth.get_session()
            logging.info(f"✓ Session verification: user={current_session.user.id if current_session and current_session.user else 'None'}")
            logging.info("✓ Client fully authenticated for both database and storage operations")
            
        except Exception as e:
            logging.error(f"❌ set_session() failed: {e}")
            logging.error(f"   Error type: {type(e).__name__}")
            raise
        
        return client
    
    def _create_storage_client(self, access_token: str) -> StorageClient:
        """
        Create a dedicated Storage client with explicit authentication headers
        
        This ensures the Storage API receives proper JWT authentication, so Postgres
        sees the request as 'authenticated' role and RLS policies pass.
        
        Args:
            access_token: User's access token (JWT)
            
        Returns:
            StorageClient configured with explicit Authorization and apikey headers
        """
        return StorageClient(
            f"{self.supabase_url}/storage/v1",
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": self.supabase_anon_key,
                "X-Client-Info": "storage3/py-explicit",
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
        Upload PDF to Supabase Storage with content-addressed naming using authenticated session for RLS
        
        Features:
        - Content-hash based naming for deduplication
        - Automatic path construction with user isolation
        - Skips upload if file already exists (deduplication)
        - Uses authenticated session to enforce RLS policies
        
        Args:
            access_token: User's access token (JWT)
            refresh_token: User's refresh token
            user_id: User ID for RLS path isolation
            document_id: Document identifier (for logging)
            pdf_bytes: Raw PDF binary data
            report_id: Report ID for organization
            
        Returns:
            Dictionary with storage metadata:
            {
                "storage_path": "path/to/file.pdf",
                "content_hash": "sha256_hash",
                "bucket": "report-documents",
                "stored_at": "2025-11-01T20:00:00Z"
            }
            
        Raises:
            ValueError: If upload fails or RLS policy rejects
            Exception: If Storage unavailable
        """
        try:
            # DEBUG: Log upload attempt details
            logging.info(f"📤 UPLOAD ATTEMPT - user_id: {user_id}, report_id: {report_id}, document_id: {document_id}")
            logging.info(f"📤 PDF size: {len(pdf_bytes)} bytes")
            
            # Create user-context client for RLS compliance
            user_client = self._create_user_client(access_token, refresh_token)
            
            # Calculate content hash
            content_hash = self._calculate_content_hash(pdf_bytes)
            logging.info(f"📤 Content hash: {content_hash[:16]}...")
            
            # Construct storage path
            storage_path = self._construct_storage_path(user_id, report_id, content_hash)
            logging.info(f"📤 Storage path: {storage_path}")
            
            # Create dedicated Storage client with explicit headers for RLS enforcement
            storage = self._create_storage_client(access_token)
            
            # Check if file already exists (deduplication)
            try:
                existing_file = storage.from_(self.bucket_name).list(
                    path=f"{user_id}/{report_id}"
                )
                
                # Check if our file already exists
                file_exists = any(
                    file.get("name") == f"{content_hash}.pdf" 
                    for file in existing_file
                )
                
                if file_exists:
                    logging.info(
                        f"File already exists in Storage (deduplication): {storage_path}"
                    )
                    # File exists, skip upload but return metadata
                    return {
                        "storage_path": storage_path,
                        "content_hash": content_hash,
                        "bucket": self.bucket_name,
                        "stored_at": datetime.now().isoformat(),
                        "duplicate": True
                    }
            except Exception as e:
                # If list fails, continue with upload (better to upload than fail)
                logging.warning(f"Failed to check for existing file: {e}")
            
            # Upload to Storage with dedicated storage client (RLS enforced)
            logging.info(f"📤 Attempting upload to bucket '{self.bucket_name}' at path '{storage_path}'")
            logging.info(f"📤 File options: contentType=application/pdf, size={len(pdf_bytes)}")
            
            # Safety assertions to prevent RLS failures
            assert storage_path and not storage_path.startswith("/"), "storage_path must not start with '/'"
            assert storage_path.split("/", 1)[0] == user_id, "first path segment must be the user_id"
            assert access_token and access_token.count(".") == 2, "access_token looks malformed"
            
            # DEBUG: Verify all RLS policy conditions before upload
            # Get current session to verify user ID
            current_session = user_client.auth.get_session()
            session_user_id = current_session.user.id if current_session and current_session.user else None
            
            # Prepare debug output
            debug_output = []
            debug_output.append("=" * 70)
            debug_output.append("🔍 RLS POLICY CONDITION VERIFICATION")
            debug_output.append(f"Timestamp: {datetime.now().isoformat()}")
            debug_output.append("=" * 70)
            debug_output.append(f"1️⃣  bucket_id = 'report-documents'")
            debug_output.append(f"    ✓ Our bucket: '{self.bucket_name}'")
            debug_output.append(f"    ✓ Match: {self.bucket_name == 'report-documents'}")
            debug_output.append("")
            debug_output.append(f"2️⃣  (storage.foldername(name))[1] = auth.uid()::text")
            debug_output.append(f"    ✓ Storage path: '{storage_path}'")
            debug_output.append(f"    ✓ First folder (user_id): '{user_id}'")
            debug_output.append(f"    ✓ Expected auth.uid(): '{user_id}'")
            debug_output.append(f"    ✓ Session user ID: '{session_user_id}'")
            debug_output.append(f"    ✓ Match: {user_id == session_user_id}")
            debug_output.append(f"    ⚠️  CRITICAL: If session_user_id is None, auth.uid() will be NULL -> RLS FAILS")
            debug_output.append("")
            debug_output.append(f"3️⃣  (metadata->>'mimetype') = 'application/pdf'")
            debug_output.append(f"    ✓ Content-Type: 'application/pdf'")
            debug_output.append(f"    ✓ Match: True")
            debug_output.append("")
            debug_output.append(f"4️⃣  ((metadata->>'size'))::bigint <= 104857600")
            debug_output.append(f"    ✓ File size: {len(pdf_bytes)} bytes")
            debug_output.append(f"    ✓ Size limit: 104857600 bytes (100MB)")
            debug_output.append(f"    ✓ Under limit: {len(pdf_bytes) <= 104857600}")
            debug_output.append("")
            debug_output.append("🔑 JWT Token Info:")
            debug_output.append(f"    ✓ Access token length: {len(access_token)}")
            debug_output.append(f"    ✓ Token prefix (first 20 chars): '{access_token[:20]}...'")
            debug_output.append(f"    ✓ Authorization header format: 'Bearer {access_token[:20]}...'")
            debug_output.append("=" * 70)
            debug_output.append("")
            
            # Write to both console log and file
            for line in debug_output:
                logging.info(line)
            
            # Write to debug file
            try:
                with open("rls_debug.txt", "a", encoding="utf-8") as f:
                    f.write("\n".join(debug_output))
                    f.write("\n\n")
                logging.info("✓ RLS debug info written to rls_debug.txt")
            except Exception as file_error:
                logging.warning(f"Failed to write debug file: {file_error}")
            
            response = storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=pdf_bytes,
                file_options={
                    "contentType": "application/pdf",  # camelCase required by storage3
                    "upsert": "false"  # string expected by API
                }
            )
            
            # DEBUG: Log full response details
            logging.info(f"📤 Upload response type: {type(response)}")
            logging.info(f"📤 Upload response: {response}")
            
            # Check for upload errors
            if hasattr(response, 'error') and response.error:
                logging.error(f"❌ Upload failed with error: {response.error}")
                raise ValueError(f"Storage upload failed: {response.error}")
            
            logging.info(
                f"Uploaded PDF to Storage: {storage_path} "
                f"({len(pdf_bytes)} bytes, hash: {content_hash[:8]}...)"
            )
            
            return {
                "storage_path": storage_path,
                "content_hash": content_hash,
                "bucket": self.bucket_name,
                "stored_at": datetime.now().isoformat(),
                "duplicate": False
            }
            
        except Exception as e:
            logging.error(f"❌ UPLOAD EXCEPTION for document {document_id}: {type(e).__name__}: {e}")
            logging.error(f"❌ Exception details: {repr(e)}")
            import traceback
            logging.error(f"❌ Stack trace:\n{traceback.format_exc()}")
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
        Generate temporary signed URL for secure document access using authenticated session for RLS
        
        Security:
        - Verifies user_id matches path prefix (user isolation)
        - Uses user JWT to enforce RLS policies
        - URL expires after expiry_seconds
        
        Args:
            access_token: User's access token (JWT)
            refresh_token: User's refresh token
            user_id: User ID for access verification
            storage_path: Storage path from database
            expiry_seconds: URL validity period (default 1 hour)
            
        Returns:
            Signed URL string valid for expiry_seconds
            
        Raises:
            ValueError: If user doesn't own document, path invalid, or RLS rejects
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
        Download PDF from Storage using authenticated session for RLS
        
        Args:
            access_token: User's access token (JWT)
            refresh_token: User's refresh token
            user_id: User ID for access verification
            storage_path: Storage path from database
            
        Returns:
            PDF binary data as bytes
            
        Raises:
            ValueError: If user doesn't own document, download fails, or RLS rejects
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
    
    def delete_document(self, access_token: str, refresh_token: str, user_id: str, storage_path: str) -> bool:
        """
        Delete document from Storage using authenticated session for RLS
        
        Args:
            access_token: User's access token (JWT)
            refresh_token: User's refresh token
            user_id: User ID for access verification
            storage_path: Storage path from database
            
        Returns:
            True if deletion successful, False otherwise
            
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
        Delete all documents for a report from Storage using authenticated session for RLS
        
        Args:
            access_token: User's access token (JWT)
            refresh_token: User's refresh token
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
