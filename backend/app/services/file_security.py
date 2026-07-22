"""File upload validation and basic content-safety checks."""
import os
import magic
import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class FileSecurityService:
    """
    File upload validation service.
    
    Features:
    - MIME type validation with whitelist
    - File extension validation
    - File size limits
    - Content-based file type detection
    - Basic size and binary-content heuristics (not antivirus scanning)
    - Path traversal prevention
    - Filename sanitization
    """
    
    # MIME type whitelist for document uploads
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'application/x-pdf',
        'text/plain',
        'text/csv',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/rtf',
        'text/rtf',
        # HTML types for template uploads
        'text/html',
        'application/xhtml+xml',
    }
    
    # File extension whitelist (normalized to lowercase)
    ALLOWED_EXTENSIONS = {
        '.pdf',
        '.txt',
        '.csv',
        '.doc',
        '.docx',
        '.xls',
        '.xlsx',
        '.rtf',
        # HTML extensions for template uploads
        '.html',
        '.htm',
    }
    
    # Dangerous file extensions that should never be allowed
    DANGEROUS_EXTENSIONS = {
        '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar',
        '.app', '.deb', '.pkg', '.dmg', '.rpm', '.msi', '.ps1', '.sh', '.php',
        '.asp', '.aspx', '.jsp', '.py', '.rb', '.pl', '.cgi', '.htaccess'
    }
    
    # Magic number signatures for common file types (first 16 bytes)
    FILE_SIGNATURES = {
        'pdf': [b'%PDF-'],
        'doc': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],  # OLE2 compound document
        'docx': [b'PK\x03\x04'],  # ZIP file (Office Open XML)
        'txt': [],  # Plain text has no magic number
        'rtf': [b'{\\rtf'],
        'html': [b'<!DOCTYPE', b'<!doctype', b'<html', b'<HTML', b'<Html'],  # HTML documents
    }
    
    def __init__(self, max_file_size_mb: int = 50):
        """
        Initialize file security service.
        
        Args:
            max_file_size_mb: Maximum allowed file size in megabytes
        """
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.max_file_size_mb = max_file_size_mb
        
        # Try to initialize libmagic for content-based detection
        self.magic_available = self._init_magic()
    
    def _init_magic(self) -> bool:
        """Initialize python-magic for file type detection."""
        try:
            # Test if magic is available and working
            magic.from_buffer(b"test", mime=True)
            logger.info("python-magic initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"python-magic not available: {e}")
            return False
    
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal and other attacks.
        
        Args:
            filename: Original filename
            
        Returns:
            str: Sanitized filename
        """
        if not filename:
            return "unnamed_file"
        
        # Remove path components (prevent directory traversal)
        filename = os.path.basename(filename)
        
        # Remove or replace dangerous characters
        dangerous_chars = '<>:"|?*\\'
        for char in dangerous_chars:
            filename = filename.replace(char, '_')
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Limit filename length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255-len(ext)] + ext
        
        # Ensure we have a filename
        if not filename or filename in ['.', '..']:
            filename = "sanitized_file"
        
        return filename
    
    def detect_file_type(self, content: bytes) -> Optional[str]:
        """
        Detect file type based on content (magic numbers).
        
        Args:
            content: File content bytes
            
        Returns:
            Optional[str]: Detected file type or None if unknown
        """
        if not content:
            return None
        
        # Check first 16 bytes against known signatures
        header = content[:16]
        
        for file_type, signatures in self.FILE_SIGNATURES.items():
            for signature in signatures:
                if header.startswith(signature):
                    return file_type
        
        # Use python-magic if available
        if self.magic_available:
            try:
                detected_mime = magic.from_buffer(content, mime=True)
                if detected_mime == 'application/pdf':
                    return 'pdf'
                elif detected_mime in ['application/msword', 'application/vnd.ms-office']:
                    return 'doc'
                elif detected_mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    return 'docx'
                elif detected_mime == 'text/plain':
                    return 'txt'
                elif detected_mime in ['application/rtf', 'text/rtf']:
                    return 'rtf'
            except Exception as e:
                logger.warning(f"Magic detection failed: {e}")
        
        return None
    
    def validate_file_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Validate file content for security issues.
        
        Args:
            content: File content bytes
            filename: Original filename
            
        Returns:
            Dict: Validation result with success status and details
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "detected_type": None,
            "content_hash": hashlib.sha256(content).hexdigest()
        }
        
        # Basic content checks
        if not content:
            validation_result["valid"] = False
            validation_result["errors"].append("File is empty")
            return validation_result
        
        # File size validation
        if len(content) > self.max_file_size_bytes:
            validation_result["valid"] = False
            validation_result["errors"].append(
                f"File size {len(content) / 1024 / 1024:.1f}MB exceeds maximum allowed size of {self.max_file_size_mb}MB"
            )
        
        # Detect actual file type
        detected_type = self.detect_file_type(content)
        validation_result["detected_type"] = detected_type
        
        # Check for executable content patterns
        if self._contains_executable_patterns(content):
            validation_result["valid"] = False
            validation_result["errors"].append("File contains potentially executable content")
        
        # PDF-specific validation
        if detected_type == 'pdf':
            pdf_validation = self._validate_pdf_content(content)
            if not pdf_validation["valid"]:
                validation_result["valid"] = False
                validation_result["errors"].extend(pdf_validation["errors"])
        
        # Check for embedded objects (basic detection)
        if self._contains_suspicious_embedded_objects(content):
            validation_result["warnings"].append("File may contain embedded objects")
        
        return validation_result
    
    def validate_upload(
        self, 
        content: bytes, 
        filename: str, 
        declared_mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate upload metadata and content with basic safety heuristics.
        
        Args:
            content: File content bytes
            filename: Original filename
            declared_mime_type: MIME type from upload headers
            
        Returns:
            Dict: Complete validation result
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "sanitized_filename": "",
            "detected_type": None,
            "mime_type_valid": True,
            "extension_valid": True,
            "content_valid": True,
            "size_valid": True,
            "basic_safety_checks_passed": True
        }
        
        # Sanitize filename
        validation_result["sanitized_filename"] = self.sanitize_filename(filename)
        
        # Validate filename and extension
        file_ext = os.path.splitext(validation_result["sanitized_filename"])[1].lower()
        
        # Check for dangerous extensions
        if file_ext in self.DANGEROUS_EXTENSIONS:
            validation_result["valid"] = False
            validation_result["extension_valid"] = False
            validation_result["errors"].append(f"File extension '{file_ext}' is not allowed for security reasons")
        
        # Check against allowed extensions
        elif file_ext not in self.ALLOWED_EXTENSIONS:
            validation_result["valid"] = False
            validation_result["extension_valid"] = False
            validation_result["errors"].append(
                f"File extension '{file_ext}' is not allowed. Allowed extensions: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )
        
        # Validate MIME type if provided
        if declared_mime_type and declared_mime_type not in self.ALLOWED_MIME_TYPES:
            validation_result["valid"] = False
            validation_result["mime_type_valid"] = False
            validation_result["errors"].append(
                f"MIME type '{declared_mime_type}' is not allowed. Allowed types: {', '.join(sorted(self.ALLOWED_MIME_TYPES))}"
            )
        
        # Validate file content
        content_validation = self.validate_file_content(content, filename)
        validation_result["detected_type"] = content_validation["detected_type"]
        validation_result["content_hash"] = content_validation["content_hash"]
        
        if not content_validation["valid"]:
            validation_result["valid"] = False
            validation_result["content_valid"] = False
            validation_result["errors"].extend(content_validation["errors"])
        
        validation_result["warnings"].extend(content_validation["warnings"])
        
        # MIME type vs content type validation
        if declared_mime_type and content_validation["detected_type"]:
            if not self._mime_type_matches_content(declared_mime_type, content_validation["detected_type"]):
                validation_result["warnings"].append(
                    f"Declared MIME type '{declared_mime_type}' may not match detected file type '{content_validation['detected_type']}'"
                )
        
        # File size check
        if len(content) > self.max_file_size_bytes:
            validation_result["valid"] = False
            validation_result["size_valid"] = False
            validation_result["errors"].append(
                f"File size {len(content) / 1024 / 1024:.1f}MB exceeds maximum allowed size of {self.max_file_size_mb}MB"
            )
        
        # Lightweight heuristics only. Deployments that require antivirus scanning
        # should scan uploads before they reach Attenly.
        basic_safety_result = self._run_basic_file_safety_checks(
            content,
            validation_result["sanitized_filename"],
        )
        if not basic_safety_result["passed"]:
            validation_result["valid"] = False
            validation_result["basic_safety_checks_passed"] = False
            validation_result["errors"].append(
                f"File failed basic safety validation: {basic_safety_result['details']}"
            )
        
        return validation_result
    
    def _contains_executable_patterns(self, content: bytes) -> bool:
        """Check for patterns that indicate executable content."""
        # Check for common executable patterns
        executable_patterns = [
            b'MZ',  # DOS/Windows executable
            b'\x7fELF',  # Linux executable
            b'\xfe\xed\xfa',  # Mach-O executable (macOS)
            b'#!/bin/',  # Unix script shebang
            b'#!/usr/',  # Unix script shebang
            b'<script',  # JavaScript
            b'javascript:',  # JavaScript URL
            b'vbscript:',  # VBScript URL
        ]
        
        header = content[:1024].lower()  # Check first KB
        
        for pattern in executable_patterns:
            if pattern.lower() in header:
                return True
        
        return False
    
    def _contains_suspicious_embedded_objects(self, content: bytes) -> bool:
        """Check for suspicious embedded objects or macros."""
        suspicious_patterns = [
            b'<object',  # Embedded objects
            b'<embed',   # Embedded content
            b'ActiveX',  # ActiveX controls
            b'macro',    # Macros
            b'VBA',      # Visual Basic for Applications
        ]
        
        header = content[:4096].lower()  # Check first 4KB
        
        for pattern in suspicious_patterns:
            if pattern.lower() in header:
                return True
        
        return False
    
    def _validate_pdf_content(self, content: bytes) -> Dict[str, Any]:
        """Validate PDF-specific content."""
        result = {"valid": True, "errors": []}
        
        # Check PDF header
        if not content.startswith(b'%PDF-'):
            result["valid"] = False
            result["errors"].append("Invalid PDF header")
        
        # Check for PDF trailer
        if b'%%EOF' not in content[-1024:]:
            result["valid"] = False
            result["errors"].append("PDF file appears to be truncated or corrupted")
        
        # Check for suspicious PDF content
        suspicious_pdf_patterns = [
            b'/JavaScript',
            b'/JS',
            b'/Launch',
            b'/EmbeddedFile',
            b'/XFA'
        ]
        
        for pattern in suspicious_pdf_patterns:
            if pattern in content:
                result["errors"].append(f"PDF contains potentially dangerous content: {pattern.decode('utf-8', errors='ignore')}")
                # Don't mark as invalid, just warn
        
        return result
    
    def _mime_type_matches_content(self, declared_mime: str, detected_type: str) -> bool:
        """Check if declared MIME type matches detected content type."""
        mime_mappings = {
            'application/pdf': 'pdf',
            'application/x-pdf': 'pdf',
            'application/msword': 'doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'text/plain': 'txt',
            'application/rtf': 'rtf',
            'text/rtf': 'rtf'
        }
        
        expected_type = mime_mappings.get(declared_mime)
        return expected_type == detected_type if expected_type else True
    
    def _run_basic_file_safety_checks(
        self,
        content: bytes,
        filename: str,
    ) -> Dict[str, Any]:
        """
        Apply small upload-safety heuristics.

        This is not an antivirus or malware scanner. Organizations with malware
        scanning requirements should add that control at their ingress layer.
        """
        result = {"passed": True, "details": "Basic file safety checks passed"}
        
        # Check file size (extremely large files could be suspicious)
        if len(content) > 100 * 1024 * 1024:  # 100MB
            result["passed"] = False
            result["details"] = "File size exceeds security limits"
        
        # Check for null bytes (could indicate binary in text file)
        if b'\x00' in content[:1024] and filename.lower().endswith(('.txt', '.csv')):
            result["passed"] = False
            result["details"] = "Text file contains binary data"

        return result

# Global instance
_file_security_service = None

def get_file_security_service() -> FileSecurityService:
    """Get or create the global file security service instance."""
    global _file_security_service
    if _file_security_service is None:
        from app.config import MAX_FILE_SIZE_MB
        _file_security_service = FileSecurityService(max_file_size_mb=MAX_FILE_SIZE_MB)
    return _file_security_service
