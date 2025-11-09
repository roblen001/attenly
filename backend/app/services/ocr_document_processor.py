"""
OCR Document Processor

Document processor implementation for image-based PDFs using OCR.
Follows the same BaseDocumentProcessor pattern as PDFDocumentProcessor
but uses OCR service instead of direct PDF text extraction.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from .ocr_service import ocr_service
from .base_document_processor import BaseDocumentProcessor

logger = logging.getLogger(__name__)


class OCRDocumentProcessor(BaseDocumentProcessor):
    """OCR-specific document processor for image-based PDFs"""
    
    def __init__(self):
        """Initialize OCR document processor"""
        self.ocr_service = ocr_service
        logger.info("OCR document processor initialized")
    
    @property
    def supported_extensions(self) -> List[str]:
        """Return list of supported file extensions"""
        return ['.pdf']  # OCR processes PDFs that are image-based
    
    @property
    def processor_name(self) -> str:
        """Return human-readable name of the processor"""
        return "OCR Processor"
    
    def validate_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Validate PDF document before OCR processing
        
        Args:
            content: File content as bytes
            filename: Original filename
            
        Returns:
            Validation result dictionary
        """
        
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
        
        # Check file size limits (from config)
        from app.config import OCR_MAX_FILE_SIZE_MB
        if validation_result["file_info"]["size_mb"] > OCR_MAX_FILE_SIZE_MB:
            validation_result["valid"] = False
            validation_result["errors"].append(f"File size exceeds {OCR_MAX_FILE_SIZE_MB}MB limit for OCR processing")
        
        # Check if file is empty
        if len(content) == 0:
            validation_result["valid"] = False
            validation_result["errors"].append("File is empty")
        
        # Try to validate PDF structure using PyMuPDF
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            
            if len(doc) == 0:
                validation_result["valid"] = False
                validation_result["errors"].append("PDF contains no pages")
            else:
                # Check page count limits (optimized for 1GB RAM instances)
                from app.config import OCR_MAX_PAGES_PER_REQUEST
                if len(doc) > OCR_MAX_PAGES_PER_REQUEST:
                    validation_result["valid"] = False
                    validation_result["errors"].append(
                        f"PDF has {len(doc)} pages, exceeds limit of {OCR_MAX_PAGES_PER_REQUEST} pages for OCR processing. "
                        f"This limit prevents memory exhaustion on resource-constrained instances. "
                        f"Please split your document into smaller files or use a text-based PDF if possible."
                    )
                elif len(doc) > 20:
                    validation_result["warnings"].append(
                        f"PDF with {len(doc)} pages will require extended processing time. "
                        f"OCR processing is memory-intensive - expect 2-5 minutes for documents of this size."
                    )
            
            validation_result["file_info"]["pages"] = len(doc)
            doc.close()
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Invalid PDF file: {str(e)}")
        
        # Add OCR-specific warnings with memory context
        if validation_result["valid"]:
            validation_result["warnings"].extend([
                "Document will be processed using OCR - processing may take several minutes",
                "OCR quality depends on document image quality and resolution",
                "Processing uses optimized settings for memory-constrained environments"
            ])
        
        return validation_result
    
    async def extract_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        """
        Extract content from PDF using OCR (async for memory management)
        
        Args:
            content: PDF file content as bytes
            filename: Original filename
            
        Returns:
            Content extraction result
        """
        
        try:
            logger.info(f"Starting OCR content extraction for {filename}")
            
            # First check if OCR service dependencies are available
            try:
                health_check = self.ocr_service.health_check()
                if not health_check.get("service_available", False):
                    error_msg = f"OCR service not available: {health_check.get('error', 'Unknown error')}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "content_type": "pdf_ocr",
                        "processor": self.processor_name,
                        "error": error_msg
                    }
            except Exception as health_error:
                error_msg = f"OCR service health check failed: {str(health_error)}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": error_msg
                }
            
            # Calculate timeout based on estimated page count
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                num_pages = len(doc)
                doc.close()
                logger.info(f"PDF has {num_pages} pages - starting OCR processing")
                
                # Add progress indication for larger documents
                if num_pages > 10:
                    logger.info(f"Processing {num_pages}-page document may take 3-5 minutes on memory-constrained instances")
            except Exception as pdf_error:
                logger.warning(f"Failed to determine PDF page count: {pdf_error}")
                num_pages = 10  # Default estimate if we can't determine
            
            timeout = self.ocr_service.calculate_timeout(num_pages)
            logger.info(f"OCR timeout set to {timeout}s for {num_pages} pages")
            
            # Process with OCR (now async)
            try:
                ocr_result = await self.ocr_service.process_pdf_bytes(content, filename, timeout)
            except ImportError as ie:
                error_msg = f"OCR dependencies not installed: {str(ie)}. Please ensure python-doctr[torch], torch, and torchvision are properly installed."
                logger.error(error_msg)
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": error_msg
                }
            except MemoryError as mem_error:
                error_msg = (
                    f"Out of memory during OCR processing of {filename}. "
                    f"The document may be too large for available resources. "
                    f"Try: (1) reducing document size, (2) splitting into smaller files, "
                    f"or (3) using a text-based PDF instead of scanned images."
                )
                logger.error(error_msg)
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": error_msg
                }
            except Exception as ocr_error:
                error_msg = f"OCR processing failed: {str(ocr_error)}"
                logger.error(error_msg)
                # Check if error message indicates memory issues
                if "memory" in str(ocr_error).lower() or "oom" in str(ocr_error).lower():
                    error_msg += " (Possible memory exhaustion - try a smaller document)"
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": error_msg
                }
            
            if not ocr_result.success:
                error_msg = ocr_result.error_message or "OCR processing failed"
                logger.error(f"OCR processing failed for {filename}: {error_msg}")
                
                # Enhance error message with helpful context
                if "timeout" in error_msg.lower():
                    error_msg += " - Document too large for current timeout settings"
                elif "memory" in error_msg.lower() or "oom" in error_msg.lower():
                    error_msg += " - Try reducing document size or page count"
                
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": error_msg
                }
            
            # Check quality metrics for fallback decision
            if not ocr_result.quality_metrics.meets_quality_threshold:
                logger.warning(f"OCR quality below threshold for {filename}: "
                             f"confidence={ocr_result.quality_metrics.mean_word_confidence:.3f}, "
                             f"coverage={ocr_result.quality_metrics.coverage_ratio:.3f}")
                
                # Fallback to empty document as specified
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": f"OCR quality below threshold (confidence: {ocr_result.quality_metrics.mean_word_confidence:.2f}, "
                            f"coverage: {ocr_result.quality_metrics.coverage_ratio:.2f}). "
                            f"Document treated as empty. Try uploading a higher quality scan or text-based PDF.",
                    "quality_metrics": ocr_result.quality_metrics
                }
            
            # Convert to Attenly schema with bounding boxes
            # Generate document_id from filename for bbox tracking
            import uuid
            document_id = str(uuid.uuid4())
            
            try:
                attently_data = self.ocr_service.convert_to_attenly_schema(
                    ocr_result.doctr_export, 
                    filename,
                    document_id
                )
            except Exception as schema_error:
                error_msg = f"Failed to convert OCR results to internal format: {str(schema_error)}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "content_type": "pdf_ocr",
                    "processor": self.processor_name,
                    "error": error_msg
                }
            
            # Write debug output files
            # self._write_debug_files(filename, ocr_result.doctr_export, attently_data, ocr_result.quality_metrics)
            
            logger.info(f"OCR extraction successful for {filename}: {len(attently_data['pages'])} pages, "
                       f"{attently_data['statistics']['total_tokens']} tokens, "
                       f"processing time: {ocr_result.processing_time:.1f}s")
            
            return {
                "success": True,
                "content_type": "pdf_ocr",
                "processor": self.processor_name,
                "data": attently_data,
                "processing_time": ocr_result.processing_time,
                "quality_metrics": ocr_result.quality_metrics
            }
            
        except ImportError as ie:
            error_msg = f"OCR dependencies missing: {str(ie)}. Please install python-doctr[torch], torch, and torchvision."
            logger.error(error_msg)
            return {
                "success": False,
                "content_type": "pdf_ocr",
                "processor": self.processor_name,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"OCR content extraction failed for {filename}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "content_type": "pdf_ocr",
                "processor": self.processor_name,
                "error": error_msg
            }
    
    def get_preview(self, content: bytes, filename: str, max_pages: int = 3) -> Dict[str, Any]:
        """
        Generate preview of OCR content
        
        Args:
            content: PDF file content as bytes
            filename: Original filename
            max_pages: Maximum pages to preview (limited for OCR due to processing cost)
            
        Returns:
            Preview information
        """
        
        try:
            logger.info(f"Generating OCR preview for {filename} (max {max_pages} pages)")
            
            # For OCR preview, we'll limit to fewer pages due to processing cost
            preview_max_pages = min(max_pages, 2)  # Limit OCR preview to 2 pages max
            
            # Calculate timeout for preview (shorter than full processing)
            timeout = min(120, self.ocr_service.calculate_timeout(preview_max_pages))
            
            # Process with OCR
            ocr_result = self.ocr_service.process_pdf_bytes(content, filename, timeout)
            
            if not ocr_result.success:
                return {
                    "success": False,
                    "processor": self.processor_name,
                    "filename": filename,
                    "error": ocr_result.error_message
                }
            
            # Convert to Attenly schema and extract preview
            attently_data = self.ocr_service.convert_to_attenly_schema(ocr_result.doctr_export, filename)
            
            # Build preview from first few pages
            preview_pages = attently_data["pages"][:preview_max_pages]
            sample_text = ""
            
            for page in preview_pages:
                sample_text += f"\n--- PAGE {page['page_number']} ---\n"
                page_content = page["markdown"][:500]  # First 500 chars per page
                sample_text += page_content
                if len(page["markdown"]) > 500:
                    sample_text += "...\n"
            
            return {
                "success": True,
                "processor": self.processor_name,
                "filename": filename,
                "preview_pages": len(preview_pages),
                "total_pages": attently_data["metadata"]["total_pages"],
                "sample_text": sample_text,
                "estimated_tokens": attently_data["statistics"]["total_tokens"],
                "tables_detected": attently_data["statistics"]["total_tables"],
                "paragraphs_detected": attently_data["statistics"]["total_paragraphs"],
                "processing_time": ocr_result.processing_time,
                "quality_metrics": {
                    "mean_confidence": ocr_result.quality_metrics.mean_word_confidence,
                    "coverage_ratio": ocr_result.quality_metrics.coverage_ratio,
                    "total_words": ocr_result.quality_metrics.total_words,
                    "meets_quality_threshold": ocr_result.quality_metrics.meets_quality_threshold
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to generate OCR preview for {filename}: {e}")
            return {
                "success": False,
                "processor": self.processor_name,
                "filename": filename,
                "error": str(e)
            }
    
    def _write_debug_files(self, filename: str, doctr_export: Dict[str, Any], 
                           attenly_data: Dict[str, Any], quality_metrics: Any):
        """
        Write debug output files for OCR processing
        
        Args:
            filename: Original filename
            doctr_export: Raw doctr export data
            attenly_data: Converted Attenly schema data
            quality_metrics: OCR quality metrics
        """
        
        try:
            # Create debug directory
            debug_dir = Path("ocr_debug")
            debug_dir.mkdir(exist_ok=True)
            
            # Create timestamp and safe filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")[:50]
            base_name = f"{timestamp}_{safe_filename}"
            
            # Write raw doctr export
            doctr_file = debug_dir / f"{base_name}_doctr_export.json"
            with open(doctr_file, 'w', encoding='utf-8') as f:
                json.dump(doctr_export, f, indent=2, ensure_ascii=False)
            
            # Write converted Attenly data
            attenly_file = debug_dir / f"{base_name}_attenly_schema.json"
            with open(attenly_file, 'w', encoding='utf-8') as f:
                json.dump(attenly_data, f, indent=2, ensure_ascii=False)
            
            # Write extracted text content
            text_file = debug_dir / f"{base_name}_extracted_text.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"# OCR Extraction Debug Output\n")
                f.write(f"# File: {filename}\n")
                f.write(f"# Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"# Pages: {len(attenly_data['pages'])}\n")
                f.write(f"# Total tokens: {attenly_data['statistics']['total_tokens']}\n")
                f.write(f"# Quality metrics: confidence={quality_metrics.mean_word_confidence:.3f}, ")
                f.write(f"coverage={quality_metrics.coverage_ratio:.3f}, ")
                f.write(f"meets_threshold={quality_metrics.meets_quality_threshold}\n\n")
                
                f.write("# Full Markdown Content:\n")
                f.write(attenly_data['full_markdown'])
                
                f.write("\n\n# Page-by-Page Content:\n")
                for page in attenly_data['pages']:
                    f.write(f"\n--- PAGE {page['page_number']} ({page['token_count']} tokens) ---\n")
                    f.write(page['markdown'])
                    f.write("\n")
            
            # Write quality metrics
            metrics_file = debug_dir / f"{base_name}_quality_metrics.json"
            metrics_data = {
                "filename": filename,
                "timestamp": datetime.now().isoformat(),
                "mean_word_confidence": quality_metrics.mean_word_confidence,
                "coverage_ratio": quality_metrics.coverage_ratio,
                "total_words": quality_metrics.total_words,
                "confident_words": quality_metrics.confident_words,
                "meets_quality_threshold": quality_metrics.meets_quality_threshold,
                "pages_processed": len(attenly_data['pages']),
                "total_tokens": attenly_data['statistics']['total_tokens']
            }
            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(metrics_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Debug files written for {filename}:")
            logger.info(f"  - DocTR export: {doctr_file}")
            logger.info(f"  - Attenly schema: {attenly_file}")
            logger.info(f"  - Extracted text: {text_file}")
            logger.info(f"  - Quality metrics: {metrics_file}")
            
        except Exception as e:
            logger.warning(f"Failed to write debug files for {filename}: {e}")
    
    def get_processor_info(self) -> Dict[str, Any]:
        """Get information about OCR processor capabilities"""
        return {
            "processor_name": self.processor_name,
            "supported_extensions": self.supported_extensions,
            "ocr_info": self.ocr_service.get_model_info(),
            "processing_limits": {
                "max_pages": "Configured via OCR_MAX_PAGES_PER_REQUEST",
                "max_file_size_mb": "Configured via OCR_MAX_FILE_SIZE_MB",
                "timeout_calculation": "Dynamic based on page count"
            },
            "quality_thresholds": {
                "confidence_threshold": "Configured via OCR_CONFIDENCE_THRESHOLD",
                "coverage_threshold": "Configured via OCR_COVERAGE_THRESHOLD"
            }
        }
