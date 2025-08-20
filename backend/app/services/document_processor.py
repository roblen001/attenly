"""
Document Processor Service

Extensible document processing pipeline that supports multiple document types.
Uses a plugin-like architecture for different document processors with intelligent routing.

Architecture:
- DocumentClassifier: Analyzes files and determines appropriate processor
- BaseDocumentProcessor: Abstract base class for document processors
- PDFDocumentProcessor: PDF-specific processing implementation
- DocumentProcessor: Main orchestrator that routes to appropriate processor
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type
from .pdf_parser import PDFProcessor
from .chunking_service import ChunkingService
from .vector_store import VectorStore
from .document_classifier import DocumentClassifier, ProcessorType

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


class PDFDocumentProcessor(BaseDocumentProcessor):
    """PDF-specific document processor"""
    
    def __init__(self):
        self.pdf_processor = PDFProcessor()
    
    @property
    def supported_extensions(self) -> List[str]:
        return ['.pdf']
    
    @property
    def processor_name(self) -> str:
        return "PDF Processor"
    
    def validate_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Validate PDF document before processing"""
        
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "file_info": {
                "filename": filename,
                "size_bytes": len(content),
                "size_mb": len(content) / (1024 * 1024),
                "processor": self.processor_name
            }
        }
        
        # Check file extension
        if not filename.lower().endswith('.pdf'):
            validation_result["valid"] = False
            validation_result["errors"].append("File must be a PDF")
        
        # Check file size (10MB limit)
        max_size_mb = 10
        if validation_result["file_info"]["size_mb"] > max_size_mb:
            validation_result["valid"] = False
            validation_result["errors"].append(f"File size exceeds {max_size_mb}MB limit")
        
        # Check if file is empty
        if len(content) == 0:
            validation_result["valid"] = False
            validation_result["errors"].append("File is empty")
        
        # Try to validate PDF structure
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            
            if len(doc) == 0:
                validation_result["warnings"].append("PDF contains no pages")
            elif len(doc) > 100:
                validation_result["warnings"].append(f"Large PDF with {len(doc)} pages may take longer to process")
            
            validation_result["file_info"]["pages"] = len(doc)
            doc.close()
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Invalid PDF file: {str(e)}")
        
        return validation_result
    
    def extract_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Extract structured content from PDF"""
        
        try:
            pdf_data = self.pdf_processor.process_pdf(content, filename)
            
            if not pdf_data or not pdf_data.get("pages"):
                raise ValueError("Failed to extract content from PDF")
            
            return {
                "success": True,
                "content_type": "pdf",
                "processor": self.processor_name,
                "data": pdf_data
            }
            
        except Exception as e:
            logger.error(f"Failed to extract PDF content from {filename}: {e}")
            return {
                "success": False,
                "content_type": "pdf",
                "processor": self.processor_name,
                "error": str(e)
            }
    
    def get_preview(self, content: bytes, filename: str, max_pages: int = 3) -> Dict[str, Any]:
        """Generate preview of PDF content"""
        
        try:
            pdf_data = self.pdf_processor.process_pdf(content, filename)
            
            # Limit to preview pages
            preview_pages = pdf_data["pages"][:max_pages]
            
            # Extract sample text from first few pages
            sample_text = ""
            for page in preview_pages:
                sample_text += f"\n--- PAGE {page['page_number']} ---\n"
                sample_text += page["markdown"][:500]  # First 500 chars per page
                if len(page["markdown"]) > 500:
                    sample_text += "...\n"
            
            return {
                "success": True,
                "processor": self.processor_name,
                "filename": filename,
                "metadata": pdf_data["metadata"],
                "preview_pages": len(preview_pages),
                "total_pages": pdf_data["metadata"]["total_pages"],
                "sample_text": sample_text,
                "estimated_tokens": pdf_data["statistics"]["total_tokens"],
                "tables_detected": pdf_data["statistics"]["total_tables"],
                "paragraphs_detected": pdf_data["statistics"]["total_paragraphs"]
            }
            
        except Exception as e:
            logger.error(f"Failed to generate PDF preview for {filename}: {e}")
            return {
                "success": False,
                "processor": self.processor_name,
                "filename": filename,
                "error": str(e)
            }


# Future processors can be added here
# class DOCXDocumentProcessor(BaseDocumentProcessor):
#     """DOCX-specific document processor"""
#     
#     @property
#     def supported_extensions(self) -> List[str]:
#         return ['.docx', '.doc']
#     
#     @property
#     def processor_name(self) -> str:
#         return "DOCX Processor"
#     
#     # Implement abstract methods...


class DocumentProcessor:
    """Main orchestrator for document processing with multi-format support and intelligent routing"""
    
    def __init__(self):
        self.chunking_service = ChunkingService()
        self.classifier = DocumentClassifier()
        
        # Register available document processors
        self.processors: Dict[str, BaseDocumentProcessor] = {}
        self._register_processors()
        
        logger.info(f"Document processor initialized with {len(self.processors)} processors and classifier")
    
    def _register_processors(self):
        """Register all available document processors"""
        
        # Register PDF processor
        pdf_processor = PDFDocumentProcessor()
        for ext in pdf_processor.supported_extensions:
            self.processors[ext.lower()] = pdf_processor
        
        # Future processors can be registered here
        # docx_processor = DOCXDocumentProcessor()
        # for ext in docx_processor.supported_extensions:
        #     self.processors[ext.lower()] = docx_processor
    
    def get_processor_for_file(self, filename: str) -> Optional[BaseDocumentProcessor]:
        """Get the appropriate processor for a file based on its extension"""
        
        # Extract file extension
        if '.' not in filename:
            return None
        
        extension = '.' + filename.split('.')[-1].lower()
        return self.processors.get(extension)
    
    def _get_processor_by_type(self, processor_type: str) -> Optional[BaseDocumentProcessor]:
        """Get processor instance by processor type"""
        
        if processor_type == ProcessorType.PDF.value:
            return self.processors.get('.pdf')
        elif processor_type == ProcessorType.DOCX.value:
            return None # Future implementation
        elif processor_type == ProcessorType.OCR.value:
            return None  # Future OCR processor
        else:
            return None
    
    async def process_document(
        self, 
        file_id: str, 
        content: bytes, 
        filename: str, 
        vector_store: VectorStore
    ) -> Dict[str, Any]:
        """
        Process uploaded document through the complete pipeline with intelligent routing
        
        Args:
            file_id: Unique identifier for the file
            content: Document file content as bytes
            filename: Original filename
            vector_store: Session-specific vector store instance
            
        Returns:
            Dictionary with processing results and statistics
        """
        
        try:
            logger.info(f"Starting document processing for {filename} (ID: {file_id})")
            
            # Step 1: Classify document to determine appropriate processor
            logger.info("Step 1: Classifying document...")
            classification = self.classifier.classify_document(content, filename)
            
            # Check if document is supported for processing
            if classification["recommended_processor"] == ProcessorType.UNSUPPORTED.value:
                error_msg = "Document cannot be processed: " + "; ".join(classification["processing_notes"])
                logger.warning(f"Unsupported document {filename}: {error_msg}")
                return {
                    "success": False,
                    "document_id": file_id,
                    "filename": filename,
                    "error": error_msg,
                    "classification": classification,
                    "processing_stats": {
                        "total_pages": 0,
                        "total_tokens": 0,
                        "l1_chunks": 0,
                        "l2_chunks": 0,
                        "stored_chunks": 0
                    }
                }
            
            # Step 2: Get appropriate processor based on classification
            processor = self._get_processor_by_type(classification["recommended_processor"])
            if not processor:
                raise ValueError(f"No processor available for type: {classification['recommended_processor']}")
            
            logger.info(f"Using {processor.processor_name} for {filename} (confidence: {classification['confidence']:.2f})")
            
            # Step 3: Extract structured content
            logger.info("Step 2: Extracting document content...")
            extraction_result = processor.extract_content(content, filename)
            
            if not extraction_result["success"]:
                raise ValueError(f"Content extraction failed: {extraction_result.get('error', 'Unknown error')}")
            
            document_data = extraction_result["data"]
            logger.info(f"Extracted content using {processor.processor_name}")
            
            # Step 4: Create two-level chunks
            logger.info("Step 3: Creating two-level chunks...")
            l1_chunks, l2_chunks = self.chunking_service.create_two_level_chunks(
                document_id=file_id,
                pdf_data=document_data,  # Note: This works for PDF, may need abstraction for other types
                filename=filename
            )
            
            if not l1_chunks:
                raise ValueError("Failed to create document chunks")
            
            logger.info(f"Created {len(l1_chunks)} L1 chunks and {len(l2_chunks)} L2 chunks")
            
            # Step 5: Store chunks in vector database
            logger.info("Step 4: Storing chunks in vector database...")
            stored_count = vector_store.store_document_chunks(file_id, l1_chunks, l2_chunks)
            
            if stored_count == 0:
                raise ValueError("Failed to store chunks for document")
            
            # Step 6: Generate processing statistics
            chunk_stats = self.chunking_service.get_chunk_statistics(l1_chunks, l2_chunks)
            
            # Compile results
            result = {
                "success": True,
                "document_id": file_id,
                "filename": filename,
                "processor_used": processor.processor_name,
                "content_type": extraction_result.get("content_type", "unknown"),
                "classification": classification,
                "processing_stats": {
                    "total_pages": document_data["metadata"]["total_pages"],
                    "total_tokens": document_data["statistics"]["total_tokens"],
                    "total_tables": document_data["statistics"]["total_tables"],
                    "total_paragraphs": document_data["statistics"]["total_paragraphs"],
                    "l1_chunks": len(l1_chunks),
                    "l2_chunks": len(l2_chunks),
                    "stored_chunks": stored_count
                },
                "chunk_statistics": chunk_stats,
                "document_metadata": document_data["metadata"]
            }
            
            logger.info(f"Successfully processed document {filename}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to process document {filename}: {e}")
            return {
                "success": False,
                "document_id": file_id,
                "filename": filename,
                "error": str(e),
                "processing_stats": {
                    "total_pages": 0,
                    "total_tokens": 0,
                    "l1_chunks": 0,
                    "l2_chunks": 0,
                    "stored_chunks": 0
                }
            }
    
    def validate_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Validate document before processing using classifier and appropriate processor
        
        Args:
            content: File content as bytes
            filename: Original filename
            
        Returns:
            Validation result with success status and details
        """
        
        try:
            # Step 1: Use classifier for early validation and routing
            classification = self.classifier.classify_document(content, filename)
            
            # Step 2: For validation, we'll be more permissive and only block truly unsupported file types
            # Image-based PDFs will be allowed through validation but will fail during processing with helpful messages
            if classification["file_type"] == "unknown":
                return {
                    "valid": False,
                    "errors": ["File type not recognized or supported"],
                    "warnings": [],
                    "file_info": classification["metadata"],
                    "classification": classification
                }
            
            # Step 3: Get processor based on file type (not recommended processor)
            # This allows PDFs through even if they're image-based
            processor = self.get_processor_for_file(filename)
            if not processor:
                return {
                    "valid": False,
                    "errors": [f"No processor available for file type: {classification['file_type']}"],
                    "warnings": [],
                    "file_info": classification["metadata"],
                    "classification": classification
                }
            
            # Step 4: Use processor-specific validation (basic file structure validation)
            validation_result = processor.validate_document(content, filename)
            
            # Step 5: Add classification warnings for image-based content
            if classification["recommended_processor"] == ProcessorType.UNSUPPORTED.value:
                if not validation_result.get("warnings"):
                    validation_result["warnings"] = []
                validation_result["warnings"].extend([
                    "Document may contain image-based content that requires OCR processing",
                    "Processing may fail if document relies heavily on images or scanned content"
                ])
            
            # Step 6: Enhance validation result with classification info
            validation_result["classification"] = classification
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Failed to validate document {filename}: {e}")
            return {
                "valid": False,
                "errors": [f"Validation failed: {str(e)}"],
                "warnings": [],
                "file_info": {
                    "filename": filename,
                    "size_bytes": len(content),
                    "size_mb": len(content) / (1024 * 1024),
                    "processor": "None",
                    "error": str(e)
                }
            }
    
    async def reprocess_document(
        self, 
        file_id: str, 
        content: bytes, 
        filename: str, 
        vector_store: VectorStore
    ) -> Dict[str, Any]:
        """
        Reprocess a document (useful for updates or error recovery)
        
        Args:
            file_id: Unique identifier for the file
            content: Document file content as bytes
            filename: Original filename
            vector_store: Session-specific vector store instance
            
        Returns:
            Dictionary with reprocessing results
        """
        
        logger.info(f"Reprocessing document {filename} (ID: {file_id})")
        
        # First, clean up existing chunks
        vector_store.delete_document_chunks(file_id)
        
        # Then process as new document
        return await self.process_document(file_id, content, filename, vector_store)
    
    def get_document_preview(self, content: bytes, filename: str, max_pages: int = 3) -> Dict[str, Any]:
        """
        Generate a preview of document content without full processing
        
        Args:
            content: Document file content as bytes
            filename: Original filename
            max_pages: Maximum number of pages to preview
            
        Returns:
            Preview information including sample text and metadata
        """
        
        # Get appropriate processor
        processor = self.get_processor_for_file(filename)
        if not processor:
            return {
                "success": False,
                "filename": filename,
                "error": f"Unsupported file type: {filename}"
            }
        
        # Use processor-specific preview
        return processor.get_preview(content, filename, max_pages)
    
    def get_processing_capabilities(self) -> Dict[str, Any]:
        """Get information about processing capabilities and status"""
        
        # Check if required dependencies are available
        capabilities = {
            "chunking": True,       # Always available
            "vector_storage": False,
            "token_counting": False
        }
        
        # Check tiktoken availability
        try:
            import tiktoken
            capabilities["token_counting"] = True
        except ImportError:
            pass
        
        # Check ChromaDB availability
        try:
            import chromadb
            capabilities["vector_storage"] = True
        except ImportError:
            pass
        
        # Get supported formats from registered processors
        supported_formats = []
        processor_info = {}
        
        for ext, processor in self.processors.items():
            if ext not in supported_formats:
                supported_formats.append(ext)
            
            if processor.processor_name not in processor_info:
                processor_info[processor.processor_name] = {
                    "extensions": processor.supported_extensions,
                    "name": processor.processor_name
                }
        
        return {
            "capabilities": capabilities,
            "chunking_config": {
                "l1_target_tokens": self.chunking_service.L1_TARGET,
                "l1_max_tokens": self.chunking_service.L1_MAX,
                "l2_window_tokens": self.chunking_service.L2_WINDOW,
                "l2_overlap_tokens": self.chunking_service.L2_OVERLAP
            },
            "supported_formats": supported_formats,
            "processors": processor_info,
            "max_file_size_mb": 10  # Should match the limit in validation
        }
    
    def get_supported_extensions(self) -> List[str]:
        """Get list of all supported file extensions"""
        return list(self.processors.keys())
    
    def get_processor_info(self, filename: str) -> Optional[Dict[str, Any]]:
        """Get information about the processor that would handle a file"""
        
        processor = self.get_processor_for_file(filename)
        if not processor:
            return None
        
        return {
            "processor_name": processor.processor_name,
            "supported_extensions": processor.supported_extensions
        }
    
    def classify_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Classify a document without processing it
        
        Args:
            content: File content as bytes
            filename: Original filename
            
        Returns:
            Classification result with file type, content type, and processor recommendation
        """
        return self.classifier.classify_document(content, filename)
    
    def get_classification_info(self) -> Dict[str, Any]:
        """
        Get information about classification capabilities and thresholds
        
        Returns:
            Classification configuration and capabilities
        """
        return self.classifier.get_classification_info()
    
    def is_document_supported(self, content: bytes, filename: str) -> bool:
        """
        Quick check if a document is supported for processing
        
        Args:
            content: File content as bytes
            filename: Original filename
            
        Returns:
            True if document can be processed, False otherwise
        """
        try:
            classification = self.classifier.classify_document(content, filename)
            return classification["recommended_processor"] != ProcessorType.UNSUPPORTED.value
        except Exception:
            return False
