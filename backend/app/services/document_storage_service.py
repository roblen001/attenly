"""
Secure Document Storage Service

Provides secure disk-based storage for processed document data to minimize memory usage.
Works with all document types (PDFs, OCR, DOCX, etc.)

Authentication is handled by the router layer using existing Supabase auth.
This service only handles storage operations with user_id provided by authenticated endpoints.

Features:
- User-isolated storage directories
- Cryptographically secure tokens (UUID4)
- Path traversal prevention
- Automatic TTL-based cleanup
- Context managers for guaranteed cleanup
"""

import os
import json
import uuid
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DocumentStorageService:
    """Secure storage service for processed document data"""
    
    def __init__(self, base_dir: str, ttl_hours: int = 2):
        """
        Initialize document storage service
        
        Args:
            base_dir: Base directory for document storage
            ttl_hours: Time-to-live for stored files in hours (default: 2)
        """
        self.base_dir = Path(base_dir)
        self.ttl_hours = ttl_hours
        
        # Create base directory with secure permissions
        try:
            self.base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            logger.info(f"Document storage initialized at {self.base_dir}")
        except Exception as e:
            logger.error(f"Failed to create document storage directory: {e}")
            raise
    
    def _get_user_dir(self, user_id: str) -> Path:
        """
        Get user-specific directory with isolation
        
        Args:
            user_id: User ID (from authenticated endpoint)
            
        Returns:
            Path to user-specific directory
        """
        user_id_value = str(user_id)
        if not user_id_value or Path(user_id_value).name != user_id_value or user_id_value in {".", ".."}:
            raise ValueError("Invalid user identifier")

        user_dir = self.base_dir / user_id_value
        user_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return user_dir

    @staticmethod
    def _validate_token(token: str) -> str:
        """Accept only tokens created by ``_generate_secure_token``."""
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ValueError("Invalid document token")
        return token
    
    def _generate_secure_token(self) -> str:
        """
        Generate cryptographically secure token for storage
        
        Returns:
            Secure UUID4 token as string
        """
        return uuid.uuid4().hex
    
    def _validate_path(self, filepath: Path, user_dir: Path) -> bool:
        """
        Validate file path to prevent traversal attacks
        
        Args:
            filepath: Path to validate
            user_dir: Expected parent directory
            
        Returns:
            True if path is valid and within user directory
        """
        try:
            resolved = filepath.resolve()
            user_dir_resolved = user_dir.resolve()
            return resolved.parent == user_dir_resolved
        except Exception:
            return False
    
    def store(self, data: Dict[str, Any], user_id: str, document_id: str, processor_type: str = "unknown") -> str:
        """
        Store document data securely
        
        Args:
            data: Document data to store
            user_id: User ID (from authenticated endpoint)
            document_id: Document ID for reference
            processor_type: Type of processor used (e.g., "pdf", "ocr", "docx")
            
        Returns:
            Secure token for retrieval
        """
        try:
            user_dir = self._get_user_dir(user_id)
            token = self._generate_secure_token()
            filepath = user_dir / f"{token}.json"
            
            # Prepare secure data with metadata
            secure_data = {
                "created_at": datetime.utcnow().isoformat(),
                "user_id": str(user_id),
                "document_id": str(document_id),
                "processor_type": processor_type,
                "token": token,
                "data": data
            }
            
            # Write with atomic operation and secure permissions
            temp_filepath = filepath.with_suffix('.tmp')
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(secure_data, f, ensure_ascii=False)
            
            # Set secure permissions before moving to final location
            os.chmod(temp_filepath, 0o600)
            
            # Atomic move to final location
            temp_filepath.rename(filepath)
            
            logger.info(
                "Stored %s document data for document %s",
                processor_type,
                document_id,
            )
            return token
            
        except Exception as e:
            logger.error(f"Failed to store document data: {e}")
            raise ValueError(f"Failed to store document data: {str(e)}")
    
    def load(self, token: str, user_id: str) -> Dict[str, Any]:
        """
        Load document data with ownership verification
        
        Args:
            token: Storage token
            user_id: User ID (from authenticated endpoint)
            
        Returns:
            Stored document data
        """
        try:
            token = self._validate_token(token)
            user_dir = self._get_user_dir(user_id)
            filepath = user_dir / f"{token}.json"
            
            # Security checks
            if not filepath.exists():
                raise ValueError("Document data not found")
            
            if not self._validate_path(filepath, user_dir):
                raise ValueError("Invalid path - potential traversal attempt detected")
            
            # Load data
            with open(filepath, 'r', encoding='utf-8') as f:
                secure_data = json.load(f)
            
            # Verify ownership
            if secure_data.get("user_id") != str(user_id):
                raise ValueError("Unauthorized access attempt")
            
            # Check TTL (warn but still return data)
            created_at = datetime.fromisoformat(secure_data.get("created_at"))
            age_hours = (datetime.utcnow() - created_at).total_seconds() / 3600
            
            if age_hours > self.ttl_hours:
                logger.warning(f"Document data expired (age: {age_hours:.1f}h > TTL: {self.ttl_hours}h) but returning anyway")
            
            return secure_data["data"]
            
        except Exception as e:
            logger.error("Failed to load document data: %s", e)
            raise ValueError(f"Failed to load document data: {str(e)}")
    
    def delete(self, token: str, user_id: str) -> bool:
        """
        Delete document data
        
        Args:
            token: Storage token
            user_id: User ID (from authenticated endpoint)
            
        Returns:
            True if deleted successfully
        """
        try:
            token = self._validate_token(token)
            user_dir = self._get_user_dir(user_id)
            filepath = user_dir / f"{token}.json"
            
            # Security checks
            if not filepath.exists():
                logger.debug("Document data not found for deletion")
                return False
            
            if not self._validate_path(filepath, user_dir):
                raise ValueError("Invalid path - potential traversal attempt detected")
            
            # Load and verify ownership before deletion
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    secure_data = json.load(f)
                
                if secure_data.get("user_id") != str(user_id):
                    raise ValueError("Unauthorized deletion attempt")
            except json.JSONDecodeError:
                # If file is corrupted, allow deletion
                logger.warning("Corrupted document data file; proceeding with deletion")
            
            # Delete file
            os.unlink(filepath)
            logger.info("Deleted document data")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete document data: {e}")
            return False
    
    def delete_user_data(self, user_id: str) -> int:
        """
        Delete all document data for a specific user
        
        Args:
            user_id: User ID (from authenticated endpoint)
            
        Returns:
            Number of files deleted
        """
        try:
            user_dir = self._get_user_dir(user_id)
            
            if not user_dir.exists():
                return 0
            
            deleted_count = 0
            for filepath in user_dir.glob("*.json"):
                try:
                    os.unlink(filepath)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete file {filepath}: {e}")
            
            # Try to remove user directory if empty
            try:
                user_dir.rmdir()
                logger.info(f"Removed empty user directory for user {user_id[:8]}...")
            except OSError:
                # Directory not empty, that's fine
                pass
            
            logger.info(f"Deleted {deleted_count} document data files for user {user_id[:8]}...")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete user document data: {e}")
            return 0
    
    def cleanup_old_files(self, max_age_hours: Optional[int] = None) -> int:
        """
        Clean up old document data files based on TTL
        
        Args:
            max_age_hours: Maximum age in hours (uses instance TTL if not provided)
            
        Returns:
            Number of files cleaned up
        """
        if max_age_hours is None:
            max_age_hours = self.ttl_hours
        
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        try:
            for user_dir in self.base_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                
                for filepath in user_dir.glob("*.json"):
                    try:
                        # Read metadata
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        created_at = datetime.fromisoformat(data.get("created_at"))
                        
                        # Delete if older than cutoff
                        if created_at < cutoff:
                            os.unlink(filepath)
                            cleaned_count += 1
                            logger.debug(f"Cleaned up old document data: {filepath.name[:8]}...")
                    
                    except (json.JSONDecodeError, KeyError, ValueError):
                        # If we can't read metadata or it's corrupted, delete it
                        try:
                            os.unlink(filepath)
                            cleaned_count += 1
                            logger.debug(f"Cleaned up corrupted document data: {filepath.name[:8]}...")
                        except Exception:
                            pass
                    
                    except Exception as e:
                        logger.warning(f"Error checking file {filepath}: {e}")
                
                # Try to remove empty user directories
                try:
                    if not any(user_dir.iterdir()):
                        user_dir.rmdir()
                except OSError:
                    pass
            
            if cleaned_count > 0:
                logger.info(f"Cleanup completed: removed {cleaned_count} old document data files")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return cleaned_count
    
    @contextmanager
    def temporary_storage(self, data: Dict[str, Any], user_id: str, document_id: str, processor_type: str = "unknown"):
        """
        Context manager for automatic cleanup of temporary document storage
        
        Args:
            data: Document data
            user_id: User ID (from authenticated endpoint)
            document_id: Document ID
            processor_type: Type of processor used
            
        Yields:
            Storage token
        """
        token = None
        try:
            token = self.store(data, user_id, document_id, processor_type)
            yield token
        finally:
            if token:
                self.delete(token, user_id)
    
    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get information about storage usage
        
        Returns:
            Dictionary with storage statistics
        """
        try:
            total_files = 0
            total_size_bytes = 0
            users_count = 0
            
            for user_dir in self.base_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                
                users_count += 1
                
                for filepath in user_dir.glob("*.json"):
                    total_files += 1
                    try:
                        total_size_bytes += filepath.stat().st_size
                    except Exception:
                        pass
            
            return {
                "base_dir": str(self.base_dir),
                "total_users": users_count,
                "total_files": total_files,
                "total_size_mb": total_size_bytes / (1024 * 1024),
                "ttl_hours": self.ttl_hours
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {
                "base_dir": str(self.base_dir),
                "error": str(e)
            }


# Global instance
_document_storage_service: Optional[DocumentStorageService] = None


def get_document_storage_service(base_dir: str = None, ttl_hours: int = 2) -> DocumentStorageService:
    """
    Get or create global document storage service instance
    
    Args:
        base_dir: Base directory for storage (only used on first call)
        ttl_hours: TTL for stored files (only used on first call)
        
    Returns:
        DocumentStorageService instance
    """
    global _document_storage_service
    
    if _document_storage_service is None:
        if base_dir is None:
            # Import here to avoid circular dependency
            from app.config import DOCUMENT_STORAGE_DIR, DOCUMENT_STORAGE_TTL_HOURS
            base_dir = DOCUMENT_STORAGE_DIR
            ttl_hours = DOCUMENT_STORAGE_TTL_HOURS
        
        _document_storage_service = DocumentStorageService(base_dir, ttl_hours)
    
    return _document_storage_service
