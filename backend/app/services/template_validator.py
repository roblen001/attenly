"""
Template Validator Service

Validates uploaded template files before processing:
- Checks file type (DOCX, PDF, HTML)
- Enforces 2-page limit
- Uses PyMuPDF for exact PDF page counting
- Estimates pages for DOCX/HTML based on character count (~1800 chars/page)
"""

import io
import logging
from typing import Tuple
import fitz  # PyMuPDF
import mammoth
from bs4 import BeautifulSoup

from app.schemas import TemplateValidationResult

logger = logging.getLogger(__name__)


class TemplateValidator:
    """Stateless service for template file validation"""
    
    MAX_PAGES = 2
    CHARS_PER_PAGE = 1800  # Approximate characters per page
    MAX_FILE_SIZE_MB = 10  # Maximum file size
    ALLOWED_EXTENSIONS = ['.docx', '.pdf', '.html', '.htm']
    
    def validate_template_file(
        self, 
        content: bytes, 
        filename: str
    ) -> TemplateValidationResult:
        """
        Entry point for validation
        
        Args:
            content: File content as bytes
            filename: Original filename
            
        Returns:
            TemplateValidationResult with validation status and details
        """
        errors = []
        warnings = []
        estimated_pages = 0
        
        try:
            # Check file size
            file_size_mb = len(content) / (1024 * 1024)
            if file_size_mb > self.MAX_FILE_SIZE_MB:
                errors.append(f"File size ({file_size_mb:.1f}MB) exceeds maximum ({self.MAX_FILE_SIZE_MB}MB)")
                return TemplateValidationResult(
                    valid=False,
                    errors=errors,
                    warnings=warnings,
                    estimated_pages=0
                )
            
            # Check file type
            try:
                file_type = self._check_file_type(filename)
            except ValueError as e:
                errors.append(str(e))
                return TemplateValidationResult(
                    valid=False,
                    errors=errors,
                    warnings=warnings,
                    estimated_pages=0
                )
            
            # Count/estimate pages based on file type
            if file_type == 'pdf':
                estimated_pages = self._count_pdf_pages(content)
            elif file_type == 'docx':
                estimated_pages = self._estimate_docx_pages(content)
            elif file_type == 'html':
                estimated_pages = self._estimate_html_pages(content.decode('utf-8', errors='ignore'))
            
            # Check page limit
            if estimated_pages > self.MAX_PAGES:
                errors.append(
                    f"Template exceeds maximum page limit. "
                    f"Found: {estimated_pages} pages, Maximum: {self.MAX_PAGES} pages. "
                    f"Please reduce the template length."
                )
            elif estimated_pages == 0:
                warnings.append("Could not estimate page count. Template may be empty or invalid.")
            
            # Determine validity
            valid = len(errors) == 0
            
            return TemplateValidationResult(
                valid=valid,
                errors=errors,
                warnings=warnings,
                estimated_pages=estimated_pages
            )
            
        except Exception as e:
            logger.error(f"Unexpected error during template validation: {str(e)}", exc_info=True)
            errors.append(f"Validation error: {str(e)}")
            return TemplateValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                estimated_pages=0
            )
    
    def _check_file_type(self, filename: str) -> str:
        """
        Validate file extension and return normalized type
        
        Args:
            filename: Original filename
            
        Returns:
            One of: 'pdf', 'docx', 'html'
            
        Raises:
            ValueError: If file type is not supported
        """
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.pdf'):
            return 'pdf'
        elif filename_lower.endswith('.docx'):
            return 'docx'
        elif filename_lower.endswith('.doc'):
            # Old .doc format not supported - only modern .docx
            raise ValueError(
                f"Old .doc format is not supported. "
                f"Please save your file as .docx format in Microsoft Word and try again. "
                f"(File > Save As > Select 'Word Document (.docx)')"
            )
        elif filename_lower.endswith('.html') or filename_lower.endswith('.htm'):
            return 'html'
        else:
            supported = ", ".join(self.ALLOWED_EXTENSIONS)
            raise ValueError(
                f"Unsupported file type. File: {filename}. "
                f"Supported types: {supported}"
            )
    
    def _count_pdf_pages(self, pdf_bytes: bytes) -> int:
        """
        Exact page count using PyMuPDF
        
        Args:
            pdf_bytes: PDF file content
            
        Returns:
            Number of pages in PDF
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = doc.page_count
            doc.close()
            
            logger.info(f"PDF page count: {page_count}")
            return page_count
            
        except Exception as e:
            logger.error(f"Error counting PDF pages: {str(e)}")
            # If we can't count, assume it's too large to be safe
            return self.MAX_PAGES + 1
    
    def _estimate_docx_pages(self, docx_bytes: bytes) -> int:
        """
        Character-based estimation (~1800 chars/page)
        
        Args:
            docx_bytes: DOCX file content
            
        Returns:
            Estimated number of pages
        """
        try:
            # Extract text using mammoth
            result = mammoth.extract_raw_text(io.BytesIO(docx_bytes))
            text = result.value
            
            # Count characters (excluding excessive whitespace)
            text_cleaned = " ".join(text.split())
            char_count = len(text_cleaned)
            
            # Estimate pages
            estimated_pages = max(1, (char_count + self.CHARS_PER_PAGE - 1) // self.CHARS_PER_PAGE)
            
            logger.info(f"DOCX estimation: {char_count} chars → {estimated_pages} pages")
            return estimated_pages
            
        except Exception as e:
            logger.error(f"Error estimating DOCX pages: {str(e)}")
            # If we can't estimate, assume it's too large to be safe
            return self.MAX_PAGES + 1
    
    def _estimate_html_pages(self, html_string: str) -> int:
        """
        Character-based estimation for HTML
        
        Args:
            html_string: HTML content as string
            
        Returns:
            Estimated number of pages
        """
        try:
            # Parse HTML and extract text
            soup = BeautifulSoup(html_string, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Count characters (excluding excessive whitespace)
            text_cleaned = " ".join(text.split())
            char_count = len(text_cleaned)
            
            # Estimate pages
            estimated_pages = max(1, (char_count + self.CHARS_PER_PAGE - 1) // self.CHARS_PER_PAGE)
            
            logger.info(f"HTML estimation: {char_count} chars → {estimated_pages} pages")
            return estimated_pages
            
        except Exception as e:
            logger.error(f"Error estimating HTML pages: {str(e)}")
            # If we can't estimate, assume it's too large to be safe
            return self.MAX_PAGES + 1
