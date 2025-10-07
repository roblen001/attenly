"""
OCR Service using DocTR + optional Table Structure (PP-StructureV3)

Production-ready OCR service that adapts the working doctr code into a structured
service for processing image-based PDFs. Maintains the proven model configuration
while adding proper error handling, timeouts, and integration with Attenly's pipeline.

New in this version:
- Optional table detection & structure recovery via PaddleOCR PP-StructureV3
- Per-page table HTML -> Markdown conversion (keeps borders/rowspan/colspan semantics)
- Everything is fail-safe: if table deps are missing, you still get normal OCR.

Based on the original working script: scripts/ocr_pdf_to_html.py
"""

import os
import logging
import tempfile
import threading
import signal
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from contextlib import contextmanager

import torch
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

# --- Optional deps for table extraction (fail-safe if missing) ---
import fitz  # PyMuPDF
from paddleocr import PPStructureV3
from bs4 import BeautifulSoup


from app.config import (
    OCR_CACHE_DIR, OCR_CUDA_DEVICES, OCR_DET_ARCH, OCR_RECO_ARCH,
    OCR_DET_BATCH_SIZE, OCR_RECO_BATCH_SIZE, OCR_PDF_SCALE,
    OCR_CONFIDENCE_THRESHOLD, OCR_COVERAGE_THRESHOLD
)

logger = logging.getLogger(__name__)


# -------------------- Configuration toggles (safe defaults) --------------------

# Enable/disable the table stage globally (flip to False to disable quickly)
ENABLE_TABLE_DETECTION = True

# Rasterization resolution for table detection (effective ~300 DPI)
TABLE_DPI = 300

# Which PP-Structure pipeline to use
TABLE_ENGINE_VERSION = "PP-StructureV3"

# Ignore tiny/empty HTMLs
TABLE_MIN_HTML_LEN = 30

# If True, append tables (as Markdown) after OCR text in a convenience field
APPEND_TABLES_TO_PAGE_MARKDOWN = True

# -----------------------------------------------------------------------------


@dataclass
class OCRQualityMetrics:
    """Quality metrics for OCR processing results"""
    mean_word_confidence: float
    coverage_ratio: float
    total_words: int
    confident_words: int
    meets_quality_threshold: bool


@dataclass
class OCRResult:
    """Result of OCR processing operation"""
    success: bool
    doctr_export: Optional[Dict[str, Any]] = None
    quality_metrics: Optional[OCRQualityMetrics] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None


class TimeoutException(Exception):
    """Custom exception for operation timeouts"""
    pass


# -------------------------- TableDetector helper ------------------------------

class TableDetector:
    """
    Thin wrapper around PaddleOCR PP-StructureV3 to extract table HTML/Markdown per page.
    - Safe to construct even if dependencies are missing.
    - Returns {page_index: [ {bbox, html, markdown}, ... ] } on success, or {} on failure.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.engine = None
        self.available = False
        self._init_engine()

    def _init_engine(self):
        if not ENABLE_TABLE_DETECTION:
            logger.info("Table detection disabled by config.")
            return
        if PPStructureV3 is None:
            raise RuntimeError("PaddleOCR PP-StructureV3 not available.")            
        try:
            self.engine = PPStructureV3(
                use_doc_orientation_classify=True,   # handles sideways pages
                use_doc_unwarping=False,             # set True only for camera photos / perspective warp
            )

            self.available = True
            logger.info(f"TableDetector initialized with {TABLE_ENGINE_VERSION}")
        except Exception as e:
            logger.warning(f"Failed to init TableDetector: {e}")
            self.engine = None
            self.available = False

    def _pdf_to_pil_images(self, pdf_path: str, dpi: int = TABLE_DPI):
        """
        Render each PDF page to a PIL image (RGB).
        NOTE: We avoid importing PIL at module top to keep deps optional.
        """
        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) not installed.")
        try:
            from PIL import Image
            import io
        except Exception as e:
            raise RuntimeError("Pillow (PIL) not installed.") from e

        images = []
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        try:
            for page in doc:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                images.append((img, (pix.width, pix.height)))
        finally:
            doc.close()
        return images

    def _html_table_to_markdown(self, html: str) -> str:
        """
        Convert a single HTML <table> to GitHub-style Markdown.
        - Uses BeautifulSoup if available for robustness.
        - Falls back to a naive parser if bs4 is missing.
        """
        if not html or len(html) < TABLE_MIN_HTML_LEN:
            return ""

        # Prefer bs4 if available
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table")
            if not table:
                # Some outputs wrap the table inside <body> etc; try to find any table
                tables = soup.find_all("table")
                table = tables[0] if tables else None
            if not table:
                # If there's still no table, just return stripped text
                return soup.get_text("\n").strip()

            # Extract rows
            rows = []
            header_row = None
            for tr in table.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                row_vals = []
                colspans = []
                for c in cells:
                    text = c.get_text(" ", strip=True)
                    # Normalize pipes so Markdown isn't broken
                    text = text.replace("|", r"\|")
                    row_vals.append(text)
                    try:
                        colspans.append(int(c.get("colspan", "1")))
                    except ValueError:
                        colspans.append(1)
                if not row_vals:
                    continue
                # Expand colspans in MD by duplicating cell content (basic but works)
                expanded = []
                for val, span in zip(row_vals, colspans):
                    expanded += [val] * max(span, 1)
                # Detect header row if any <th> present
                if any(c.name == "th" for c in cells) and header_row is None:
                    header_row = expanded
                rows.append(expanded)

            # If we didn't see a header, synthesize from first row
            if header_row is None and rows:
                header_row = rows[0]

            # Normalize all row lengths
            width = max((len(r) for r in rows), default=0)
            norm = lambda r: r + [""] * (width - len(r))

            md_lines = []
            if header_row:
                md_lines.append("| " + " | ".join(norm(header_row)) + " |")
                md_lines.append("| " + " | ".join(["---"] * width) + " |")
                body_rows = rows[1:] if rows and rows[0] == header_row else rows
                for r in body_rows:
                    md_lines.append("| " + " | ".join(norm(r)) + " |")
            else:
                # No header at all—just dump as body
                for r in rows:
                    md_lines.append("| " + " | ".join(norm(r)) + " |")
            return "\n".join(md_lines).strip()

        # Fallback: naive (no bs4). Do a very light cleanup.
        text = html.replace("\n", " ").strip()
        return text  # worst-case: return HTML string; caller can still store it

    def detect_tables(self, pdf_path: str) -> Dict[int, List[Dict[str, Any]]]:
        """
        Run PP-StructureV3 on each page image; collect table HTML & Markdown.

        Returns:
            { page_index: [ { 'bbox': [x1,y1,x2,y2], 'html': str, 'markdown': str }, ... ] }
        """
        if not (ENABLE_TABLE_DETECTION and self.available):
            return {}

        try:
            images = self._pdf_to_pil_images(pdf_path, dpi=TABLE_DPI)
        except Exception as e:
            logger.warning(f"TableDetector rasterization failed: {e}")
            return {}

        results: Dict[int, List[Dict[str, Any]]] = {}
        for page_idx, (pil_img, _size) in enumerate(images):
            try:
                page_res = self.engine(pil_img)  # list of regions (tables, titles, etc.)
                tables: List[Dict[str, Any]] = []
                for region in page_res:
                    if region.get("type") != "table":
                        continue
                    # PP-Structure output schema commonly: region["res"]["html"] (or region["html"])
                    html = None
                    if isinstance(region.get("res"), dict):
                        html = region["res"].get("html") or region["res"].get("structure", {}).get("html")
                    if html is None:
                        html = region.get("html")
                    if not html or len(html) < TABLE_MIN_HTML_LEN:
                        continue

                    md = self._html_table_to_markdown(html)
                    entry = {
                        "bbox": region.get("bbox"),
                        "html": html,
                        "markdown": md or ""
                    }
                    tables.append(entry)
                if tables:
                    results[page_idx] = tables
            except Exception as e:
                logger.debug(f"TableDetector page {page_idx+1} failed: {e}")
                continue
            
        return results


# ------------------------------ OCR Service -----------------------------------

class OCRService:
    """
    Production OCR service using DocTR

    Adapts the proven working code from scripts/ocr_pdf_to_html.py into a
    structured service with proper error handling and production features.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern for model management"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize OCR service with lazy model loading"""
        if self._initialized:
            return

        self._initialized = True
        self.model = None
        self._model_lock = threading.Lock()

        # Initialize tiktoken for token counting
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken not available, using fallback token estimation")
            self.encoder = None

        # Setup cache directory
        self._setup_cache_directory()

        logger.info("OCR service initialized (models will be loaded on first use)")

    def _setup_cache_directory(self):
        """Setup cache directory for model storage"""
        try:
            cache_dir = Path(OCR_CACHE_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Set cache environment variables for doctr/torch
            os.environ.setdefault('TORCH_HOME', str(cache_dir / 'torch'))
            os.environ.setdefault('HF_HOME', str(cache_dir / 'huggingface'))

            logger.info(f"OCR cache directory: {cache_dir}")

        except Exception as e:
            logger.warning(f"Failed to setup cache directory: {e}")

    def _initialize_model(self):
        """
        Initialize DocTR model (adapted from original script)

        This preserves the exact working configuration from the original script
        """
        if self.model is not None:
            return

        with self._model_lock:
            if self.model is not None:
                return

            try:
                logger.info("Initializing DocTR OCR model...")

                # Check for required imports first
                try:
                    import torch  # noqa: F401
                    from doctr.models import ocr_predictor  # noqa: F401
                    logger.info("DocTR dependencies successfully imported")
                except ImportError as ie:
                    error_msg = f"Required OCR dependencies not available: {str(ie)}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                # Use exact same configuration as working script + orientation
                self.model = ocr_predictor(
                    det_arch=OCR_DET_ARCH,        # e.g., "db_resnet50"
                    reco_arch=OCR_RECO_ARCH,      # e.g., "parseq"
                    pretrained=True,
                    det_bs=OCR_DET_BATCH_SIZE,    # e.g., 4
                    reco_bs=OCR_RECO_BATCH_SIZE,  # e.g., 1024
                    resolve_lines=True,
                    resolve_blocks=True,
                    # Orientation: coarse (0/90/180/270)
                    # Note: For small skew, deskew upstream if needed.
                    detect_orientation=True,
                    straighten_pages=True,
                )

                # CUDA setup (exactly as in original script)
                if torch.cuda.is_available() and OCR_CUDA_DEVICES:
                    logger.info("Moving models to CUDA...")
                    try:
                        self.model.det_predictor.model.cuda()
                        self.model.reco_predictor.model.cuda()
                        logger.info("DocTR models loaded on CUDA")
                    except Exception as cuda_error:
                        logger.warning(f"CUDA setup failed, falling back to CPU: {cuda_error}")
                else:
                    logger.info("DocTR models loaded on CPU")

                logger.info("DocTR OCR model initialization complete")

            except ImportError as ie:
                error_msg = (
                    f"OCR dependencies not installed or not available: {str(ie)}. "
                    f"Please ensure python-doctr[torch], torch, and torchvision are properly installed."
                )
                logger.error(error_msg)
                self.model = None
                raise ValueError(error_msg)
            except Exception as e:
                error_msg = (
                    "OCR model initialization failed. This could be due to missing dependencies, "
                    f"insufficient memory, or model download issues. Error: {str(e)}"
                )
                logger.error(error_msg)
                self.model = None
                raise ValueError(error_msg)

    @contextmanager
    def _timeout_handler(self, timeout_seconds: int):
        """Context manager for handling operation timeouts"""
        def timeout_handler(signum, frame):
            raise TimeoutException(f"Operation timed out after {timeout_seconds} seconds")

        # Set up timeout signal (Unix only - for production deployment)
        old_handler = None
        try:
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_seconds)

            yield

        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)

    def process_pdf_bytes(self, content: bytes, filename: str, timeout_seconds: int = 300) -> OCRResult:
        """
        Process PDF bytes through OCR pipeline

        Adapts the core processing logic from the original script to work with
        byte content instead of file paths.

        Args:
            content: PDF file content as bytes
            filename: Original filename for metadata
            timeout_seconds: Processing timeout

        Returns:
            OCRResult with processing outcome
        """

        import time
        start_time = time.time()

        try:
            # Ensure model is initialized
            self._initialize_model()

            if self.model is None:
                return OCRResult(
                    success=False,
                    error_message="OCR model not available"
                )

            # Create temporary file for DocumentFile.from_pdf
            # (DocumentFile requires file path, not bytes directly)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name

            try:
                # Use timeout handler for the processing
                with self._timeout_handler(timeout_seconds):
                    # Load document with same scale as original script (300 DPI-ish)
                    logger.info(f"Loading PDF document: {filename}")
                    docs = DocumentFile.from_pdf(tmp_path, scale=OCR_PDF_SCALE)  # e.g., 4.17

                    # Run OCR with DocTR (exact same call as original script)
                    logger.info(f"Running OCR on {len(docs)} pages...")
                    result = self.model(docs)

                    # Export data (same as original script)
                    export_data = result.export()
                    logger.info(f"OCR processing completed: {len(export_data.get('pages', []))} pages")

                    # --- NEW: optional table detection (safe to fail without breaking OCR) ---
                    tables_by_page: Dict[int, List[Dict[str, Any]]] = {}
                    if ENABLE_TABLE_DETECTION:
                        try:
                            print("==================== Table Detection Stage ====================  ")
                            if _table_detector and _table_detector.available:
                                tables_by_page = _table_detector.detect_tables(tmp_path)
                            else:
                                logger.info("Table detection disabled or unavailable.")
                        except Exception as te:
                            logger.warning(f"Table detection failed (non-fatal): {te}")

                    # Attach to doctr_export under a namespaced key
                    export_data["_tables_by_page"] = tables_by_page
                    # -------------------------------------------------------------

            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")

            # Calculate quality metrics
            quality_metrics = self._calculate_quality_metrics(
                export_data,
                confidence_threshold=OCR_CONFIDENCE_THRESHOLD,
                coverage_threshold=OCR_COVERAGE_THRESHOLD
            )

            processing_time = time.time() - start_time

            return OCRResult(
                success=True,
                doctr_export=export_data,
                quality_metrics=quality_metrics,
                processing_time=processing_time
            )

        except TimeoutException as e:
            processing_time = time.time() - start_time
            logger.error(f"OCR processing timed out after {processing_time:.1f}s: {filename}")
            return OCRResult(
                success=False,
                error_message=f"Processing timed out after {timeout_seconds} seconds",
                processing_time=processing_time
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"OCR processing failed for {filename}: {e}")
            return OCRResult(
                success=False,
                error_message=str(e),
                processing_time=processing_time
            )

    def _calculate_quality_metrics(self, doctr_export: Dict[str, Any],
                                   confidence_threshold: float = 0.55,
                                   coverage_threshold: float = 0.65) -> OCRQualityMetrics:
        """Calculate OCR quality metrics for fallback decisions"""
        try:
            all_words = []
            total_confidence = 0.0

            for page_data in doctr_export.get("pages", []):
                for block in page_data.get("blocks", []):
                    for line in block.get("lines", []):
                        for word in line.get("words", []):
                            word_text = word.get("value", "").strip()
                            word_confidence = word.get("confidence", 0.0)

                            if word_text:
                                all_words.append({
                                    "text": word_text,
                                    "confidence": word_confidence
                                })
                                total_confidence += word_confidence

            if not all_words:
                return OCRQualityMetrics(0.0, 0.0, 0, 0, False)

            mean_confidence = total_confidence / len(all_words)
            confident_words = sum(1 for w in all_words if w["confidence"] >= confidence_threshold)
            coverage_ratio = confident_words / len(all_words)

            meets_threshold = (mean_confidence >= confidence_threshold and
                               coverage_ratio >= coverage_threshold)

            return OCRQualityMetrics(
                mean_word_confidence=mean_confidence,
                coverage_ratio=coverage_ratio,
                total_words=len(all_words),
                confident_words=confident_words,
                meets_quality_threshold=meets_threshold
            )

        except Exception as e:
            logger.error(f"Failed to calculate quality metrics: {e}")
            return OCRQualityMetrics(0.0, 0.0, 0, 0, False)

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if not text:
            return 0

        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            return max(1, len(text) // 4)

    def convert_to_attenly_schema(self, doctr_export: Dict[str, Any], filename: str = "") -> Dict[str, Any]:
        """
        Convert DocTR export to Attenly-compatible schema

        Args:
            doctr_export: Direct output from doctr result.export() (+ optional _tables_by_page)
            filename: Original filename for metadata

        Returns:
            Dictionary matching PDFProcessor.process_pdf() output format
        """
        try:
            pages_data = []
            all_lines = []

            tables_by_page: Dict[int, List[Dict[str, Any]]] = doctr_export.get("_tables_by_page", {})

            for page_idx, page_data in enumerate(doctr_export.get("pages", [])):
                # Extract text lines from doctr structure (keep your original behavior)
                text_lines: List[str] = []
                for block in page_data.get("blocks", []):
                    for line in block.get("lines", []):
                        line_text = " ".join(word.get("value", "") for word in line.get("words", []))
                        if line_text.strip():
                            text_lines.append(line_text.strip())

                page_markdown = "\n".join(text_lines)

                # --- NEW: tables (Markdown) for this page ---
                page_tables = []
                table_markdowns: List[str] = []
                for t in tables_by_page.get(page_idx, []):
                    entry = {
                        "bbox": t.get("bbox"),
                        "html": t.get("html"),
                        "markdown": t.get("markdown", "")
                    }
                    page_tables.append(entry)
                    if entry["markdown"]:
                        # Prefix with a minimal anchor so you can search later
                        table_markdowns.append(entry["markdown"])

                # Optionally build a convenience "markdown_with_tables"
                markdown_with_tables = page_markdown
                if APPEND_TABLES_TO_PAGE_MARKDOWN and table_markdowns:
                    # Separate text from tables cleanly
                    # (If you want to place tables at detected y-positions later,
                    # keep them separate; this concatenation is just a convenience.)
                    blocks = []
                    if page_markdown:
                        blocks.append(page_markdown)
                    for ti, md in enumerate(table_markdowns, start=1):
                        blocks.append(f"\n**Table {ti}**\n\n{md}")
                    markdown_with_tables = "\n\n".join(blocks).strip()

                token_count = self._count_tokens(page_markdown)

                # Simple paragraph detection (unchanged)
                paragraphs = []
                if text_lines:
                    paragraphs.append({
                        "start_line": 0,
                        "end_line": len(text_lines) - 1,
                        "content": page_markdown,
                        "type": "paragraph",
                        "token_count": token_count
                    })

                page_content = {
                    "page_number": page_idx + 1,
                    "lines": text_lines,
                    "markdown": page_markdown,  # OCR text only
                    # NEW convenience field that includes appended table MD
                    "markdown_with_tables": markdown_with_tables,
                    # Tables now present with bbox/html/markdown
                    "tables": page_tables,
                    "paragraphs": paragraphs,
                    "token_count": token_count
                }
                pages_data.append(page_content)

                # Add to full content (keep your original 'full_markdown')
                all_lines.extend([f"\n--- PAGE {page_idx + 1} ---\n"])
                all_lines.extend(text_lines)
                if APPEND_TABLES_TO_PAGE_MARKDOWN and table_markdowns:
                    # Also include tables in the full_markdown for convenience
                    for ti, md in enumerate(table_markdowns, start=1):
                        all_lines.append(f"\n**Table {ti}**\n\n{md}")

            full_markdown = "\n".join(all_lines)

            return {
                "pages": pages_data,
                "full_markdown": full_markdown,
                "metadata": {
                    "total_pages": len(pages_data),
                    "title": "",
                    "author": "",
                    "subject": "",
                    "creator": "OCR Processor",
                    "filename": filename
                },
                "statistics": {
                    "total_tokens": sum(p["token_count"] for p in pages_data),
                    "total_tables": sum(len(p["tables"]) for p in pages_data),  # NEW
                    "total_paragraphs": sum(len(p["paragraphs"]) for p in pages_data)
                }
            }

        except Exception as e:
            logger.error(f"Failed to convert doctr export: {e}")
            raise ValueError(f"Schema conversion failed: {str(e)}")

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about OCR model configuration"""
        return {
            "model_initialized": self.model is not None,
            "cuda_available": torch.cuda.is_available(),
            "cuda_devices": OCR_CUDA_DEVICES or "CPU only",
            "det_arch": OCR_DET_ARCH,
            "reco_arch": OCR_RECO_ARCH,
            "det_batch_size": OCR_DET_BATCH_SIZE,
            "reco_batch_size": OCR_RECO_BATCH_SIZE,
            "pdf_scale": OCR_PDF_SCALE,
            "cache_dir": OCR_CACHE_DIR,
            "confidence_threshold": OCR_CONFIDENCE_THRESHOLD,
            "coverage_threshold": OCR_COVERAGE_THRESHOLD
        }

    def calculate_timeout(self, num_pages: int) -> int:
        """
        Calculate processing timeout based on page count

        Args:
            num_pages: Number of pages in document

        Returns:
            Timeout in seconds
        """
        from app.config import OCR_BASE_TIMEOUT_SECONDS, OCR_TIMEOUT_PER_50_PAGES, OCR_MAX_TIMEOUT_SECONDS

        # Base timeout + additional time per 50 pages
        additional_time = (num_pages // 50) * OCR_TIMEOUT_PER_50_PAGES
        timeout = OCR_BASE_TIMEOUT_SECONDS + additional_time

        # Cap at maximum timeout
        return min(timeout, OCR_MAX_TIMEOUT_SECONDS)

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on OCR service"""
        try:
            self._initialize_model()
            model_healthy = self.model is not None

            # Also report table detector availability
            table_ok = bool(_table_detector and _table_detector.available)

            return {
                "service_available": True,
                "model_loaded": model_healthy,
                "cuda_available": torch.cuda.is_available(),
                "cache_dir_writable": os.access(OCR_CACHE_DIR, os.W_OK) if os.path.exists(OCR_CACHE_DIR) else False,
                "table_detection_available": table_ok
            }

        except Exception as e:
            logger.error(f"OCR health check failed: {e}")
            return {
                "service_available": False,
                "error": str(e)
            }


# Global instances
ocr_service = OCRService()
_table_detector = TableDetector()
