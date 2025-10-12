"""
OCR Service using DocTR

Production-ready OCR service that adapts the working doctr code into a structured
service for processing image-based PDFs with lower memory usage. This version:
- Processes PDFs in PAGE CHUNKS to avoid holding the whole document in RAM
- Uses torch.inference_mode() and optional mixed precision (configurable)
- Reduces default batch sizes (config-driven)
- Frees GPU/CPU memory between chunks (gc + torch.cuda.empty_cache)
- Allows scale reduction automatically for long PDFs (config-driven)
"""

import os
import gc
import math
import logging
import tempfile
import threading
import signal
import sys
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from contextlib import contextmanager

import torch
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from app.config import (
    OCR_CACHE_DIR, OCR_CUDA_DEVICES, OCR_DET_ARCH, OCR_RECO_ARCH,
    OCR_DET_BATCH_SIZE, OCR_RECO_BATCH_SIZE, OCR_PDF_SCALE,
    OCR_CONFIDENCE_THRESHOLD, OCR_COVERAGE_THRESHOLD,
    OCR_PAGE_CHUNK_SIZE, OCR_LONG_DOC_PAGE_THRESHOLD, OCR_REDUCED_SCALE_FOR_LONG_DOCS,
    OCR_ENABLE_MIXED_PRECISION, OCR_TORCH_NUM_THREADS,
    OCR_ENABLE_REQUEST_QUEUE, OCR_MAX_CONCURRENT_REQUESTS,
    OCR_UNLOAD_MODELS_AFTER_USE, OCR_FORCE_GC_FREQUENCY
)

logger = logging.getLogger(__name__)


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


class OCRService:
    """
    Production OCR service using DocTR with memory-conscious execution.
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
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self.model = None
        self._model_lock = threading.Lock()

        # Log psutil availability
        if not PSUTIL_AVAILABLE:
            logger.warning("psutil not available, memory monitoring disabled")

        # Initialize request queue semaphore for memory-constrained instances
        if OCR_ENABLE_REQUEST_QUEUE:
            self._request_semaphore = asyncio.Semaphore(OCR_MAX_CONCURRENT_REQUESTS)
            logger.info(f"OCR request queue enabled: max {OCR_MAX_CONCURRENT_REQUESTS} concurrent requests")
        else:
            self._request_semaphore = None
            logger.info("OCR request queue disabled")

        # Memory/allocator hygiene to reduce RSS spikes
        os.environ.setdefault("MALLOC_ARENA_MAX", "2")
        if OCR_TORCH_NUM_THREADS and OCR_TORCH_NUM_THREADS > 0:
            try:
                torch.set_num_threads(OCR_TORCH_NUM_THREADS)
            except Exception as e:
                logger.warning(f"Failed to set torch num threads: {e}")

        # Initialize tiktoken for token counting
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
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
            os.environ.setdefault('TORCH_HOME', str(cache_dir / 'torch'))
            os.environ.setdefault('HF_HOME', str(cache_dir / 'huggingface'))
            logger.info(f"OCR cache directory: {cache_dir}")
        except Exception as e:
            logger.warning(f"Failed to setup cache directory: {e}")

    def _initialize_model(self):
        """
        Initialize DocTR model (adapted from original script), with eval + no grad.
        """
        if self.model is not None:
            return

        with self._model_lock:
            if self.model is not None:
                return

            try:
                logger.info("Initializing DocTR OCR model...")
                # Imports validated at module import time

                # Build predictor with smaller default batches from config
                self.model = ocr_predictor(
                    det_arch=OCR_DET_ARCH,        # e.g., "db_resnet50"
                    reco_arch=OCR_RECO_ARCH,      # e.g., "parseq"
                    pretrained=True,
                    det_bs=OCR_DET_BATCH_SIZE,    # smaller to reduce peak memory
                    reco_bs=OCR_RECO_BATCH_SIZE,  # much smaller to reduce peak memory
                    resolve_lines=True,
                    resolve_blocks=True,
                )

                # Ensure eval and no grad
                try:
                    self.model.det_predictor.model.eval()
                    self.model.reco_predictor.model.eval()
                except Exception:
                    pass  # Older Doctr versions may differ

                # CUDA setup
                if torch.cuda.is_available() and OCR_CUDA_DEVICES:
                    logger.info("Moving models to CUDA...")
                    try:
                        self.model.det_predictor.model.cuda()
                        self.model.reco_predictor.model.cuda()
                        logger.info("DocTR models on CUDA")
                    except Exception as cuda_error:
                        logger.warning(f"CUDA setup failed, falling back to CPU: {cuda_error}")
                else:
                    logger.info("DocTR models on CPU")

                logger.info("DocTR OCR model initialization complete")

            except ImportError as ie:
                error_msg = (
                    f"OCR dependencies not installed or not available: {str(ie)}. "
                    "Please ensure python-doctr[torch], torch, and torchvision are properly installed."
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

    def _export_merge(self, exports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple Doctr exports (page-wise) into one."""
        if not exports:
            return {"pages": []}

        merged = dict(exports[0])  # shallow copy ok
        merged["pages"] = []
        for e in exports:
            merged["pages"].extend(e.get("pages", []))
        return merged

    def _choose_scale(self, num_pages: int) -> float:
        """Reduce scale automatically for very long documents to save RAM/VRAM."""
        if num_pages >= OCR_LONG_DOC_PAGE_THRESHOLD:
            return float(OCR_REDUCED_SCALE_FOR_LONG_DOCS)
        return float(OCR_PDF_SCALE)

    def _get_memory_stats(self) -> Dict[str, float]:
        """Get current memory usage statistics in MB"""
        if not PSUTIL_AVAILABLE:
            return {"available": False}

        try:
            process = psutil.Process()
            mem_info = process.memory_info()
            return {
                "available": True,
                "rss_mb": mem_info.rss / 1024 / 1024,
                "vms_mb": mem_info.vms / 1024 / 1024,
            }
        except Exception as e:
            logger.warning(f"Failed to get memory stats: {e}")
            return {"available": False}

    def _force_gc(self) -> None:
        """Aggressive garbage collection to free memory"""
        try:
            # Multiple GC passes for thorough cleanup
            gc.collect()
            gc.collect()

            # Clear PyTorch cache if CUDA is available
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception as e:
                    logger.debug(f"CUDA cache clear failed: {e}")

        except Exception as e:
            logger.warning(f"Forced GC failed: {e}")

    def _unload_models(self) -> None:
        """Explicitly unload DocTR models to free memory"""
        if not OCR_UNLOAD_MODELS_AFTER_USE:
            return

        try:
            mem_before = self._get_memory_stats()

            if self.model is not None:
                # Delete model references
                try:
                    del self.model.det_predictor.model
                    del self.model.reco_predictor.model
                except Exception:
                    pass

                del self.model
                self.model = None

                # Aggressive cleanup
                self._force_gc()

                mem_after = self._get_memory_stats()
                if mem_before.get("available") and mem_after.get("available"):
                    freed_mb = mem_before.get("rss_mb", 0) - mem_after.get("rss_mb", 0)
                    logger.info(f"Models unloaded. Memory freed: {freed_mb:.1f}MB")
                else:
                    logger.info("Models unloaded successfully")

        except Exception as e:
            logger.warning(f"Model unloading failed: {e}")

    async def process_pdf_bytes(self, content: bytes, filename: str, timeout_seconds: int = 300) -> OCRResult:
        """
        Process PDF bytes through OCR pipeline with chunked page inference to lower memory usage.
        Optionally uses request queue to prevent concurrent overload on memory-constrained instances.
        """
        start_time = time.time()

        # Use semaphore if request queue is enabled
        if self._request_semaphore is not None:
            async with self._request_semaphore:
                return await self._process_pdf_internal(content, filename, timeout_seconds, start_time)
        else:
            return await self._process_pdf_internal(content, filename, timeout_seconds, start_time)

    async def _process_pdf_internal(self, content: bytes, filename: str, timeout_seconds: int, start_time: float) -> OCRResult:
        """Internal PDF processing method with memory management"""
        try:
            # Log memory before processing
            mem_before = self._get_memory_stats()
            if mem_before.get("available"):
                logger.info(f"OCR starting - Memory: {mem_before.get('rss_mb', 0):.1f}MB RSS")

            # Ensure model is initialized
            self._initialize_model()
            if self.model is None:
                return OCRResult(success=False, error_message="OCR model not available")

            # Create temporary file for DocumentFile.from_pdf
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name

            try:
                with self._timeout_handler(timeout_seconds):
                    # First pass: count pages cheaply (without scaling high)
                    # We load at tiny scale just to determine page count; very low memory.
                    probe_docs = DocumentFile.from_pdf(tmp_path, scale=1.0)
                    total_pages = len(probe_docs)
                    del probe_docs
                    gc.collect()

                    chosen_scale = self._choose_scale(total_pages)
                    chunk_size = max(1, int(OCR_PAGE_CHUNK_SIZE))

                    logger.info(
                        f"OCR starting: {filename} | pages={total_pages} | "
                        f"scale={chosen_scale} | chunk_size={chunk_size}"
                    )

                    exports: List[Dict[str, Any]] = []
                    use_cuda = torch.cuda.is_available() and bool(OCR_CUDA_DEVICES)
                    autocast_device = "cuda" if use_cuda else "cpu"

                    # Process in chunks to keep memory bounded
                    for chunk_idx, start in enumerate(range(0, total_pages, chunk_size)):
                        end = min(start + chunk_size, total_pages)

                        # Load only the current page window at desired scale
                        # (re-load the PDF at each iteration to avoid holding all pages in RAM)
                        doc_window = DocumentFile.from_pdf(tmp_path, scale=chosen_scale)[start:end]

                        # Inference with no grad and optional mixed precision
                        with torch.inference_mode():
                            if OCR_ENABLE_MIXED_PRECISION:
                                with torch.autocast(device_type=autocast_device, dtype=torch.float16 if use_cuda else torch.bfloat16):
                                    result = self.model(doc_window)
                            else:
                                result = self.model(doc_window)

                        # Export and store
                        export_data = result.export()
                        exports.append(export_data)

                        # Free memory of the window before next chunk
                        del doc_window, result, export_data
                        gc.collect()
                        if use_cuda:
                            try:
                                torch.cuda.empty_cache()
                            except Exception:
                                pass

                        # Aggressive GC at configured frequency
                        if OCR_FORCE_GC_FREQUENCY > 0 and (chunk_idx + 1) % OCR_FORCE_GC_FREQUENCY == 0:
                            self._force_gc()
                            mem_current = self._get_memory_stats()
                            if mem_current.get("available"):
                                logger.info(f"OCR chunk {chunk_idx + 1}: pages {start + 1}-{end}/{total_pages} | Memory: {mem_current.get('rss_mb', 0):.1f}MB RSS")
                        else:
                            logger.info(f"OCR chunk processed: pages {start + 1}-{end}/{total_pages}")

                    # Merge pages
                    export_merged = self._export_merge(exports)

                    logger.info(f"OCR processing completed: {len(export_merged.get('pages', []))} pages")

            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")

            # Calculate quality metrics
            quality_metrics = self._calculate_quality_metrics(
                export_merged,
                confidence_threshold=OCR_CONFIDENCE_THRESHOLD,
                coverage_threshold=OCR_COVERAGE_THRESHOLD
            )

            processing_time = time.time() - start_time

            # Log memory after processing
            mem_after = self._get_memory_stats()
            if mem_after.get("available"):
                logger.info(f"OCR completed - Memory: {mem_after.get('rss_mb', 0):.1f}MB RSS | Time: {processing_time:.1f}s")

            # Unload models if configured (for memory-constrained instances)
            self._unload_models()

            return OCRResult(
                success=True,
                doctr_export=export_merged,
                quality_metrics=quality_metrics,
                processing_time=processing_time
            )

        except TimeoutException as e:
            processing_time = time.time() - start_time
            logger.error(f"OCR processing timed out after {processing_time:.1f}s: {filename}")
            self._unload_models()  # Clean up on timeout
            return OCRResult(
                success=False,
                error_message=f"Processing timed out after {timeout_seconds} seconds",
                processing_time=processing_time
            )

        except MemoryError as e:
            processing_time = time.time() - start_time
            logger.error(f"OCR ran out of memory processing {filename}: {e}")
            self._unload_models()  # Clean up on OOM
            return OCRResult(
                success=False,
                error_message="Out of memory. Document may be too large for available resources. Try reducing the document size or page count.",
                processing_time=processing_time
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"OCR processing failed for {filename}: {e}")
            self._unload_models()  # Clean up on error
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
            try:
                return len(self.encoder.encode(text))
            except Exception:
                pass
        # Fallback heuristic
        return max(1, len(text) // 4)

    def convert_to_attenly_schema(self, doctr_export: Dict[str, Any], filename: str = "") -> Dict[str, Any]:
        """
        Convert DocTR export to Attenly-compatible schema
        """
        try:
            pages_data = []
            all_lines = []

            for page_idx, page_data in enumerate(doctr_export.get("pages", [])):
                # Extract text lines from doctr structure
                text_lines = []
                for block in page_data.get("blocks", []):
                    for line in block.get("lines", []):
                        line_text = " ".join(word.get("value", "") for word in line.get("words", []))
                        if line_text.strip():
                            text_lines.append(line_text.strip())

                page_markdown = "\n".join(text_lines)
                token_count = self._count_tokens(page_markdown)

                # Simple paragraph detection
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
                    "markdown": page_markdown,
                    "tables": [],  # Table detection omitted
                    "paragraphs": paragraphs,
                    "token_count": token_count
                }
                pages_data.append(page_content)

                # Add to full content
                all_lines.append(f"\n--- PAGE {page_idx + 1} ---\n")
                all_lines.extend(text_lines)

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
                    "total_tables": 0,
                    "total_paragraphs": sum(len(p["paragraphs"]) for p in pages_data)
                }
            }

        except Exception as e:
            logger.error(f"Failed to convert doctr export: {e}")
            raise ValueError(f"Schema conversion failed: {str(e)}")

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about OCR model configuration"""
        mem_stats = self._get_memory_stats()
        info = {
            "model_initialized": self.model is not None,
            "cuda_available": torch.cuda.is_available(),
            "cuda_devices": OCR_CUDA_DEVICES or "CPU only",
            "det_arch": OCR_DET_ARCH,
            "reco_arch": OCR_RECO_ARCH,
            "det_batch_size": OCR_DET_BATCH_SIZE,
            "reco_batch_size": OCR_RECO_BATCH_SIZE,
            "pdf_scale": OCR_PDF_SCALE,
            "page_chunk_size": OCR_PAGE_CHUNK_SIZE,
            "long_doc_page_threshold": OCR_LONG_DOC_PAGE_THRESHOLD,
            "reduced_scale_for_long_docs": OCR_REDUCED_SCALE_FOR_LONG_DOCS,
            "mixed_precision": OCR_ENABLE_MIXED_PRECISION,
            "cache_dir": OCR_CACHE_DIR,
            "confidence_threshold": OCR_CONFIDENCE_THRESHOLD,
            "coverage_threshold": OCR_COVERAGE_THRESHOLD,
            "torch_num_threads": OCR_TORCH_NUM_THREADS,
            "enable_request_queue": OCR_ENABLE_REQUEST_QUEUE,
            "max_concurrent_requests": OCR_MAX_CONCURRENT_REQUESTS,
            "unload_models_after_use": OCR_UNLOAD_MODELS_AFTER_USE,
            "force_gc_frequency": OCR_FORCE_GC_FREQUENCY,
        }

        if mem_stats.get("available"):
            info["current_memory_mb"] = mem_stats.get("rss_mb", 0)

        return info

    def calculate_timeout(self, num_pages: int) -> int:
        """
        Calculate processing timeout based on page count
        """
        from app.config import OCR_BASE_TIMEOUT_SECONDS, OCR_TIMEOUT_PER_50_PAGES, OCR_MAX_TIMEOUT_SECONDS

        additional_time = (num_pages // 50) * OCR_TIMEOUT_PER_50_PAGES
        timeout = OCR_BASE_TIMEOUT_SECONDS + additional_time
        return min(timeout, OCR_MAX_TIMEOUT_SECONDS)

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on OCR service"""
        try:
            self._initialize_model()
            model_healthy = self.model is not None

            return {
                "service_available": True,
                "model_loaded": model_healthy,
                "cuda_available": torch.cuda.is_available(),
                "cache_dir_writable": os.access(OCR_CACHE_DIR, os.W_OK) if os.path.exists(OCR_CACHE_DIR) else False
            }

        except Exception as e:
            logger.error(f"OCR health check failed: {e}")
            return {
                "service_available": False,
                "error": str(e)
            }


# Global instance
ocr_service = OCRService()
