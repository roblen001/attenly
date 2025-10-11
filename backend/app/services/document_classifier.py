"""
Document Classifier Service

Analyzes uploaded documents to determine file type, content type, and appropriate processor.
This service sits before processor selection to enable proper routing and future OCR integration.

Architecture:
- Detects file type from extension and content
- Analyzes content type (text-based, image-based, mixed)
- Routes to appropriate processor
- Provides extensible foundation for OCR integration
"""

import logging
import re
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class FileType(Enum):
    """Supported file types"""
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    TXT = "txt"
    UNKNOWN = "unknown"


class ContentType(Enum):
    """Content analysis results"""
    TEXT_BASED = "text_based"      # Extractable text content
    IMAGE_BASED = "image_based"    # Primarily images/scanned content
    MIXED = "mixed"                # Both text and images
    EMPTY = "empty"                # No meaningful content
    UNKNOWN = "unknown"            # Cannot determine


class ProcessorType(Enum):
    """Available processors"""
    PDF = "pdf"
    OCR = "ocr"                    # OCR processor for image-based PDFs
    # DOCX = "docx"                  # Future DOCX processor
    UNSUPPORTED = "unsupported"


class DocumentClassifier:
    """
    Document classifier that analyzes files and routes them to appropriate processors
    """
    
    # Configuration thresholds
    MIN_WORDS_THRESHOLD = 50      # Below this = likely image-based
    MIN_TEXT_DENSITY_THRESHOLD = 0.005       # Text-to-content ratio threshold
    MAX_PAGES_TO_ANALYZE = 5               # Analyze first N pages for performance
    
    def __init__(self):
        """Initialize the document classifier"""
        logger.info("Document classifier initialized")
    
    def classify_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Classify a document and determine appropriate processing route
        
        Args:
            content: Document file content as bytes
            filename: Original filename
            
        Returns:
            Classification result with file type, content type, and processor recommendation
        """
        
        try:
            logger.info(f"Classifying document: {filename}")
            
            # Step 1: Determine file type
            file_type = self._detect_file_type(content, filename)
            
            # Step 2: Analyze content type (currently only for PDFs)
            content_analysis = self._analyze_content_type(content, file_type)
            
            # Step 3: Determine recommended processor
            processor_recommendation = self._recommend_processor(file_type, content_analysis)
            
            # Step 4: Compile classification result
            result = {
                "file_type": file_type.value,
                "content_type": content_analysis["content_type"].value,
                "recommended_processor": processor_recommendation.value,
                "confidence": content_analysis.get("confidence", 1.0),
                "metadata": {
                    "filename": filename,
                    "size_bytes": len(content),
                    "size_mb": len(content) / (1024 * 1024),
                    **content_analysis.get("metadata", {})
                },
                "processing_notes": self._generate_processing_notes(
                    file_type, content_analysis["content_type"], processor_recommendation
                )
            }
            
            logger.info(f"Classification complete: {file_type.value} -> {processor_recommendation.value}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to classify document {filename}: {e}")
            return {
                "file_type": FileType.UNKNOWN.value,
                "content_type": ContentType.UNKNOWN.value,
                "recommended_processor": ProcessorType.UNSUPPORTED.value,
                "confidence": 0.0,
                "metadata": {
                    "filename": filename,
                    "size_bytes": len(content),
                    "size_mb": len(content) / (1024 * 1024),
                    "error": str(e)
                },
                "processing_notes": [f"Classification failed: {str(e)}"]
            }
    
    def _detect_file_type(self, content: bytes, filename: str) -> FileType:
        """
        Detect file type from extension and content analysis
        
        Args:
            content: File content bytes
            filename: Original filename
            
        Returns:
            Detected file type
        """
        
        # Extract file extension
        if '.' not in filename:
            return FileType.UNKNOWN
        
        extension = filename.split('.')[-1].lower()
        
        # Map extensions to file types
        extension_map = {
            'pdf': FileType.PDF,
            'docx': FileType.DOCX,
            'doc': FileType.DOC,
            'txt': FileType.TXT
        }
        
        file_type = extension_map.get(extension, FileType.UNKNOWN)
        
        # Validate file type with content analysis for PDFs
        if file_type == FileType.PDF:
            if not self._validate_pdf_content(content):
                return FileType.UNKNOWN
        
        return file_type
    
    def _validate_pdf_content(self, content: bytes) -> bool:
        """
        Validate that content is actually a PDF file
        
        Args:
            content: File content bytes
            
        Returns:
            True if valid PDF, False otherwise
        """
        
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            is_valid = len(doc) >= 0  # Even empty PDFs are valid
            doc.close()
            return is_valid
        except Exception:
            return False
    
    def _analyze_content_type(self, content: bytes, file_type: FileType) -> Dict[str, Any]:
        """
        Analyze content type based on file type
        
        Args:
            content: File content bytes
            file_type: Detected file type
            
        Returns:
            Content analysis results
        """
        
        if file_type == FileType.PDF:
            return self._analyze_pdf_content(content)
        elif file_type in [FileType.DOCX, FileType.DOC]:
            # Future: Add DOCX content analysis
            return {
                "content_type": ContentType.TEXT_BASED,  # Assume text-based for now
                "confidence": 0.8,
                "metadata": {}
            }
        elif file_type == FileType.TXT:
            return {
                "content_type": ContentType.TEXT_BASED,
                "confidence": 1.0,
                "metadata": {}
            }
        else:
            return {
                "content_type": ContentType.UNKNOWN,
                "confidence": 0.0,
                "metadata": {}
            }
    
    def _analyze_pdf_content(self, content: bytes) -> Dict[str, Any]:
        """
        Analyze PDF content to determine if it's text-based or image-based
        
        Args:
            content: PDF content bytes
            
        Returns:
            Content analysis with type, confidence, and metadata
        """
        
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            
            if len(doc) == 0:
                doc.close()
                return {
                    "content_type": ContentType.EMPTY,
                    "confidence": 1.0,
                    "metadata": {"total_pages": 0, "avg_words_per_page": 0, "text_density": 0.0}
                }
            
            # Analyze first few pages for performance
            pages_to_analyze = min(len(doc), self.MAX_PAGES_TO_ANALYZE)
            total_words = 0
            total_text_length = 0
            total_images = 0
            
            for page_num in range(pages_to_analyze):
                page = doc[page_num]
                
                # Extract text and count words
                text = page.get_text()
                words = len(text.split()) if text else 0
                total_words += words
                total_text_length += len(text) if text else 0
                
                # Count images
                image_list = page.get_images()
                total_images += len(image_list)
            total_pages = len(doc)
            doc.close()
            
            # Calculate metrics
            avg_words_per_page = total_words # total words in the first couple of pages
            
            # Estimate text density (rough approximation)
            # This is a simplified metric - could be enhanced with more sophisticated analysis
            text_density = min(1.0, total_text_length / max(1, pages_to_analyze * 1000))  # Normalize to page size
            # Determine content type based on thresholds
            if avg_words_per_page < self.MIN_WORDS_THRESHOLD:
                if total_images > 0:
                    content_type = ContentType.IMAGE_BASED
                    confidence = 0.9
                else:
                    content_type = ContentType.EMPTY
                    confidence = 0.8
            elif text_density < self.MIN_TEXT_DENSITY_THRESHOLD and total_images > pages_to_analyze:
                content_type = ContentType.IMAGE_BASED
                confidence = 0.7
            else:
                content_type = ContentType.TEXT_BASED
                confidence = 0.9
            
            return {
                "content_type": content_type,
                "confidence": confidence,
                "metadata": {
                    "total_pages": total_pages,
                    "pages_analyzed": pages_to_analyze,
                    "avg_words_per_page": round(avg_words_per_page, 1),
                    "text_density": round(text_density, 3),
                    "total_images": total_images,
                    "images_per_page": round(total_images / pages_to_analyze, 1) if pages_to_analyze > 0 else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze PDF content: {e}")
            return {
                "content_type": ContentType.UNKNOWN,
                "confidence": 0.0,
                "metadata": {"error": str(e)}
            }
    
    def _recommend_processor(self, file_type: FileType, content_analysis: Dict[str, Any]) -> ProcessorType:
        """
        Recommend appropriate processor based on file type and content analysis
        
        Args:
            file_type: Detected file type
            content_analysis: Content analysis results
            
        Returns:
            Recommended processor type
        """
        
        content_type = content_analysis["content_type"]
        
        if file_type == FileType.PDF:
            if content_type == ContentType.TEXT_BASED:
                return ProcessorType.PDF
            elif content_type in [ContentType.IMAGE_BASED, ContentType.MIXED]:
                return ProcessorType.OCR  # Use OCR processor for image-based PDFs
            elif content_type == ContentType.EMPTY:
                return ProcessorType.UNSUPPORTED
            else:
                return ProcessorType.UNSUPPORTED
        
        elif file_type in [FileType.DOCX, FileType.DOC]:
            # Future: Return ProcessorType.DOCX when DOCX processor is implemented
            return ProcessorType.UNSUPPORTED
        
        elif file_type == FileType.TXT:
            # Future: Could add TXT processor
            return ProcessorType.UNSUPPORTED
        
        else:
            return ProcessorType.UNSUPPORTED
    
    def _generate_processing_notes(
        self, 
        file_type: FileType, 
        content_type: ContentType, 
        processor: ProcessorType
    ) -> List[str]:
        """
        Generate helpful processing notes for users
        
        Args:
            file_type: Detected file type
            content_type: Analyzed content type
            processor: Recommended processor
            
        Returns:
            List of processing notes and recommendations
        """
        
        notes = []
        
        if processor == ProcessorType.UNSUPPORTED:
            if file_type == FileType.PDF and content_type == ContentType.IMAGE_BASED:
                notes.extend([
                    "This PDF appears to be image-based or scanned and requires OCR processing.",
                    "OCR support is planned for a future release.",
                    "For now, please convert the document using OCR software and upload a text-based PDF."
                ])
            elif file_type == FileType.PDF and content_type == ContentType.MIXED:
                notes.extend([
                    "This PDF contains both text and images.",
                    "Some content may not be processed correctly without OCR support.",
                    "Consider converting image portions to text before uploading."
                ])
            elif file_type == FileType.PDF and content_type == ContentType.EMPTY:
                notes.append("This PDF appears to be empty or contains no extractable content.")
            elif file_type in [FileType.DOCX, FileType.DOC]:
                notes.extend([
                    "DOCX/DOC file support is planned for a future release.",
                    "Please convert to PDF format for now."
                ])
            elif file_type == FileType.UNKNOWN:
                notes.extend([
                    "File type not recognized or supported.",
                    "Please upload a PDF file with extractable text content."
                ])
            else:
                notes.append("File type not currently supported.")
        
        elif processor == ProcessorType.PDF:
            notes.append("Document ready for text extraction and processing.")
        elif processor == ProcessorType.OCR:
            notes.extend([
                "Document will be processed using OCR for text extraction.",
                "Processing may take several minutes depending on document size.",
                "OCR quality depends on document image quality and resolution."
            ])
        
        return notes
    
    def get_supported_file_types(self) -> List[str]:
        """
        Get list of supported file extensions
        
        Returns:
            List of supported file extensions
        """
        return [".pdf"]  # Currently only PDF is fully supported
    
    def get_classification_info(self) -> Dict[str, Any]:
        """
        Get information about classification capabilities and thresholds
        
        Returns:
            Classification configuration and capabilities
        """
        return {
            "supported_file_types": [ft.value for ft in FileType if ft != FileType.UNKNOWN],
            "content_types": [ct.value for ct in ContentType],
            "processor_types": [pt.value for pt in ProcessorType],
            "thresholds": {
                "min_words_per_page": self.MIN_WORDS_THRESHOLD,
                "min_text_density": self.MIN_TEXT_DENSITY_THRESHOLD,
                "max_pages_analyzed": self.MAX_PAGES_TO_ANALYZE
            },
            "current_capabilities": {
                "pdf_text_extraction": True,
                "pdf_image_detection": True,
                "ocr_processing": True,   # Now available
                "docx_processing": False  # Future feature
            }
        }
