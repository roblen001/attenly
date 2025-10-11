"""
Base Document Processor

Abstract base class for document processors in the Attenly system.
This module provides the interface that all document processors must implement.

Separated from document_processor.py to avoid circular imports with processor implementations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class BaseDocumentProcessor(ABC):
    """Abstract base class for document processors"""
    
    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """Return list of supported file extensions (e.g., ['.pdf', '.docx'])"""
        pass
    
    @property
    @abstractmethod
    def processor_name(self) -> str:
        """Return human-readable name of the processor"""
        pass
    
    @abstractmethod
    def validate_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Validate document before processing"""
        pass
    
    @abstractmethod
    def extract_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Extract structured content from document"""
        pass
    
    @abstractmethod
    def get_preview(self, content: bytes, filename: str, max_pages: int = 3) -> Dict[str, Any]:
        """Generate preview of document content"""
        pass
