"""
Centralized Configuration for Attenly Backend (updated for small, fast docTR defaults)
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# AUTHENTICATION & EXTERNAL SERVICES
# =============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =============================================================================
# EMAIL SERVICE CONFIGURATION
# =============================================================================

# Email provider (Resend)
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET")

# Internal authentication (for cron endpoints)
INTERNAL_CRON_SECRET = os.getenv("INTERNAL_CRON_SECRET")

# Email domains
EMAIL_INGEST_DOMAIN = os.getenv("EMAIL_INGEST_DOMAIN", "mail.attenly.ca")
EMAIL_FROM_DOMAIN = os.getenv("EMAIL_FROM_DOMAIN", "mail.attenly.ca")
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", f"noreply@{EMAIL_FROM_DOMAIN}")

# Application URL (for links in emails)
APP_URL = os.getenv("APP_URL", "https://app.attenly.ca")
API_URL = os.getenv("API_URL", "https://api.attenly.ca")

# Email feature limits (optional - have sensible defaults)
EMAIL_RATE_LIMIT_JOBS_PER_DAY = int(os.getenv("EMAIL_RATE_LIMIT_JOBS_PER_DAY", "20"))
EMAIL_MAX_ATTACHMENT_SIZE_MB = int(os.getenv("EMAIL_MAX_ATTACHMENT_SIZE_MB", "25"))
EMAIL_MAX_TOTAL_SIZE_MB = int(os.getenv("EMAIL_MAX_TOTAL_SIZE_MB", "50"))
EMAIL_ALLOWED_TYPES = os.getenv(
    "EMAIL_ALLOWED_TYPES", 
    "pdf,docx,txt,png,jpg,jpeg,gif,webp"
).split(",")

# Email attachment allowed extensions (centralized configuration)
# These should match the file uploader's allowed types
EMAIL_ALLOWED_EXTENSIONS = [f".{ext.strip()}" for ext in EMAIL_ALLOWED_TYPES]

# Maximum number of attachments per email
EMAIL_MAX_ATTACHMENTS = int(os.getenv("EMAIL_MAX_ATTACHMENTS", "10"))

EMAIL_VERIFICATION_EXPIRY_HOURS = int(os.getenv("EMAIL_VERIFICATION_EXPIRY_HOURS", "24"))

# =============================================================================
# SUPABASE STORAGE CONFIGURATION
# =============================================================================

STORAGE_BUCKET_NAME = os.getenv("STORAGE_BUCKET_NAME", "report-documents")
STORAGE_SIGNED_URL_EXPIRY_SECONDS = int(os.getenv("STORAGE_SIGNED_URL_EXPIRY_SECONDS", "3600"))  # 1 hour
STORAGE_MAX_FILE_SIZE_MB = int(os.getenv("STORAGE_MAX_FILE_SIZE_MB", "100"))

# =============================================================================
# LLM SERVICE CONFIGURATION
# =============================================================================

LLM_MODEL_NAME = "gemini-2.5-flash-lite"
LLM_MAX_CONTEXT_TOKENS_PER_QUESTION = 4000
LLM_TEMPERATURE = 0.0
LLM_THINKING_BUDGET = 0
LLM_RESPONSE_FORMAT = "application/json"

# =============================================================================
# VECTOR SEARCH CONFIGURATION
# =============================================================================

VECTOR_SEARCH_TOP_K_PER_QUESTION = 10
VECTOR_SEARCH_MAX_SOURCE_QUOTES = 3

# =============================================================================
# EMBEDDING GENERATION CONFIGURATION
# =============================================================================

EMBEDDING_BATCH_SIZE = 100
EMBEDDING_MAX_RETRIES = 1
EMBEDDING_TIMEOUT_SECONDS = 30
EMBEDDING_MODEL_NAME = "gemini-embedding-001"
EMBEDDING_MAX_CONCURRENT_BATCHES = 1

# =============================================================================
# INTELLIGENT QUOTE EXTRACTION CONFIGURATION (needed by llm_service)
# =============================================================================

QUOTE_CONTEXT_CHARS = int(os.getenv("QUOTE_CONTEXT_CHARS", "50"))   # chars before/after quote
MAX_QUOTE_LENGTH = int(os.getenv("MAX_QUOTE_LENGTH", "300"))        # max quote length
MIN_ANSWER_CONFIDENCE = float(os.getenv("MIN_ANSWER_CONFIDENCE", "0.7"))

ANSWER_NOT_FOUND_PHRASES: List[str] = [
    "not found", "not specified", "not available", "not mentioned",
    "not provided", "unknown", "unclear", "not stated", "not indicated",
    "no information", "cannot be determined", "not disclosed",
]

# =============================================================================
# DOCUMENT CHUNKING CONFIGURATION
# =============================================================================

CHUNK_L1_TARGET_TOKENS = 1200
CHUNK_L1_MAX_TOKENS = 2000
CHUNK_L2_WINDOW_TOKENS = 512
CHUNK_L2_OVERLAP_TOKENS = 80

# =============================================================================
# DOCUMENT PROCESSING CONFIGURATION
# =============================================================================

MAX_FILE_SIZE_MB = 50
SUPPORTED_FILE_TYPES = [".pdf", ".docx", ".txt"]

PDF_MAX_PAGES = 500
PDF_EXTRACT_IMAGES = False

# =============================================================================
# OCR CONFIGURATION (CPU-only, small instance)
# =============================================================================

OCR_CACHE_DIR = os.getenv("DOCTR_CACHE_DIR", "/cache/attenly/doctr")
OCR_CUDA_DEVICES = ""  # force CPU path

# Processing Limits (optimized for small Koyeb instances)
OCR_MAX_PAGES_PER_REQUEST = int(os.getenv("OCR_MAX_PAGES", "30"))
OCR_MAX_FILE_SIZE_MB = int(os.getenv("OCR_MAX_FILE_SIZE_MB", "60"))

# Memory Management
OCR_ENABLE_REQUEST_QUEUE = os.getenv("OCR_ENABLE_REQUEST_QUEUE", "false").lower() in ("1", "true", "yes")
OCR_MAX_CONCURRENT_REQUESTS = int(os.getenv("OCR_MAX_CONCURRENT_REQUESTS", "1"))  # default 1 to avoid contention
OCR_UNLOAD_MODELS_AFTER_USE = os.getenv("OCR_UNLOAD_MODELS_AFTER_USE", "true").lower() in ("1", "true", "yes")
OCR_FORCE_GC_FREQUENCY = int(os.getenv("OCR_FORCE_GC_FREQUENCY", "1"))  # Force GC every N chunks

# Quality Thresholds
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.55"))
OCR_COVERAGE_THRESHOLD = float(os.getenv("OCR_COVERAGE_THRESHOLD", "0.65"))

# Timeouts — CPU is slower, give more headroom
OCR_BASE_TIMEOUT_SECONDS = int(os.getenv("OCR_BASE_TIMEOUT", "180"))
OCR_TIMEOUT_PER_50_PAGES = int(os.getenv("OCR_TIMEOUT_PER_50_PAGES", "180"))
OCR_MAX_TIMEOUT_SECONDS = int(os.getenv("OCR_MAX_TIMEOUT", "900"))

# ---------------------------
# docTR model architectures
# ---------------------------
# Smallest/fastest recommended pair for CPU:
#   - Detection: db_mobilenet_v3_large
#   - Recognition: crnn_mobilenet_v3_small
OCR_DET_ARCH = os.getenv("OCR_DET_ARCH", "db_mobilenet_v3_large")
OCR_RECO_ARCH = os.getenv("OCR_RECO_ARCH", "crnn_mobilenet_v3_small")

# Batch sizes (conservative defaults for 1–2 GB RAM)
OCR_DET_BATCH_SIZE = int(os.getenv("OCR_DET_BATCH_SIZE", "1"))
OCR_RECO_BATCH_SIZE = int(os.getenv("OCR_RECO_BATCH_SIZE", "32"))

# ---------------------------
# Rendering / scaling policy
# ---------------------------
# Prefer pixel-budgeted rendering to prevent OOM.
# If PDF_USE_PIXEL_BUDGET=true, PDF_TARGET_DPI and PDF_MAX_MEGAPIXELS take precedence
# over OCR_PDF_SCALE. Keep OCR_PDF_SCALE for backward compatibility.
PDF_USE_PIXEL_BUDGET = os.getenv("PDF_USE_PIXEL_BUDGET", "true").lower() in ("1", "true", "yes")
PDF_TARGET_DPI = int(os.getenv("PDF_TARGET_DPI", "200"))
PDF_MAX_MEGAPIXELS = float(os.getenv("PDF_MAX_MEGAPIXELS", "1.6"))  # ~1.6 MP/page ≈ stable on tiny CPUs

# Legacy scale knob (ignored if pixel budget is enabled)
OCR_PDF_SCALE = float(os.getenv("OCR_PDF_SCALE", "1.2"))

# Chunked processing
OCR_PAGE_CHUNK_SIZE = int(os.getenv("OCR_PAGE_CHUNK_SIZE", "1"))  # safest on tiny instances

# Longer docs auto-reduce scale further (only relevant if not using pixel budget)
OCR_LONG_DOC_PAGE_THRESHOLD = int(os.getenv("OCR_LONG_DOC_PAGE_THRESHOLD", "40"))
OCR_REDUCED_SCALE_FOR_LONG_DOCS = float(os.getenv("OCR_REDUCED_SCALE_FOR_LONG_DOCS", "1.8"))

# AMP off on CPU for stability/accuracy
OCR_ENABLE_MIXED_PRECISION = os.getenv("OCR_ENABLE_MIXED_PRECISION", "false").lower() in ("1", "true", "yes")

# CPU threads for PyTorch / BLAS (keep to 1 on tiny instances to avoid oversubscription)
OCR_TORCH_NUM_THREADS = int(os.getenv("OCR_TORCH_NUM_THREADS", "1"))

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

DATABASE_URL = "sqlite:///./app.db"
DATABASE_ECHO = False

# =============================================================================
# DEVELOPMENT & DEBUGGING
# =============================================================================

ENVIRONMENT = "development"
DEBUG_MODE = False

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# =============================================================================
# PERFORMANCE & OPTIMIZATION
# =============================================================================

MAX_CONCURRENT_UPLOADS = 2
MAX_CONCURRENT_LLM_REQUESTS = 1

ENABLE_CACHING = False
CACHE_TTL_SECONDS = 3600

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_config():
    errors = []

    # Required env
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL is required")
    if not SUPABASE_KEY:
        errors.append("SUPABASE_KEY is required")
    if not SUPABASE_ANON_KEY:
        errors.append("SUPABASE_ANON_KEY is required for user operations")
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is required for LLM functionality")

    # LLM ranges
    if LLM_MAX_CONTEXT_TOKENS_PER_QUESTION < 1000:
        errors.append("LLM_MAX_CONTEXT_TOKENS_PER_QUESTION must be at least 1000")
    if LLM_MAX_CONTEXT_TOKENS_PER_QUESTION > 32000:
        errors.append("LLM_MAX_CONTEXT_TOKENS_PER_QUESTION should not exceed 32000")
    if not 0.0 <= LLM_TEMPERATURE <= 2.0:
        errors.append("LLM_TEMPERATURE must be between 0.0 and 2.0")

    # Vector search
    if VECTOR_SEARCH_TOP_K_PER_QUESTION < 1:
        errors.append("VECTOR_SEARCH_TOP_K_PER_QUESTION must be at least 1")
    if VECTOR_SEARCH_TOP_K_PER_QUESTION > 100:
        errors.append("VECTOR_SEARCH_TOP_K_PER_QUESTION should not exceed 100")

    # Chunking
    if CHUNK_L1_TARGET_TOKENS >= CHUNK_L1_MAX_TOKENS:
        errors.append("CHUNK_L1_TARGET_TOKENS must be less than CHUNK_L1_MAX_TOKENS")
    if CHUNK_L2_OVERLAP_TOKENS >= CHUNK_L2_WINDOW_TOKENS:
        errors.append("CHUNK_L2_OVERLAP_TOKENS must be less than CHUNK_L2_WINDOW_TOKENS")

    # Files
    if MAX_FILE_SIZE_MB < 1:
        errors.append("MAX_FILE_SIZE_MB must be at least 1")

    # OCR
    if OCR_MAX_PAGES_PER_REQUEST < 1:
        errors.append("OCR_MAX_PAGES_PER_REQUEST must be at least 1")
    if OCR_MAX_PAGES_PER_REQUEST > 1000:
        errors.append("OCR_MAX_PAGES_PER_REQUEST should not exceed 1000")
    if OCR_MAX_CONCURRENT_REQUESTS < 1:
        errors.append("OCR_MAX_CONCURRENT_REQUESTS must be at least 1")
    if OCR_MAX_CONCURRENT_REQUESTS > 10:
        errors.append("OCR_MAX_CONCURRENT_REQUESTS should not exceed 10")
    if OCR_FORCE_GC_FREQUENCY < 1:
        errors.append("OCR_FORCE_GC_FREQUENCY must be at least 1")
    if OCR_MAX_FILE_SIZE_MB < 1:
        errors.append("OCR_MAX_FILE_SIZE_MB must be at least 1")
    if OCR_MAX_FILE_SIZE_MB > 500:
        errors.append("OCR_MAX_FILE_SIZE_MB should not exceed 500")
    if not 0.0 <= OCR_CONFIDENCE_THRESHOLD <= 1.0:
        errors.append("OCR_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0")
    if not 0.0 <= OCR_COVERAGE_THRESHOLD <= 1.0:
        errors.append("OCR_COVERAGE_THRESHOLD must be between 0.0 and 1.0")
    if OCR_BASE_TIMEOUT_SECONDS < 10:
        errors.append("OCR_BASE_TIMEOUT_SECONDS must be at least 10")
    if OCR_BASE_TIMEOUT_SECONDS > 3600:
        errors.append("OCR_BASE_TIMEOUT_SECONDS should not exceed 3600")
    if OCR_TIMEOUT_PER_50_PAGES < 10:
        errors.append("OCR_TIMEOUT_PER_50_PAGES must be at least 10")
    if OCR_TIMEOUT_PER_50_PAGES > 3600:
        errors.append("OCR_TIMEOUT_PER_50_PAGES should not exceed 3600")
    if OCR_MAX_TIMEOUT_SECONDS < OCR_BASE_TIMEOUT_SECONDS:
        errors.append("OCR_MAX_TIMEOUT_SECONDS must be at least OCR_BASE_TIMEOUT_SECONDS")
    if OCR_MAX_TIMEOUT_SECONDS > 7200:
        errors.append("OCR_MAX_TIMEOUT_SECONDS should not exceed 7200")
    if OCR_PAGE_CHUNK_SIZE < 1:
        errors.append("OCR_PAGE_CHUNK_SIZE must be at least 1")
    if OCR_LONG_DOC_PAGE_THRESHOLD < 1:
        errors.append("OCR_LONG_DOC_PAGE_THRESHOLD must be at least 1")
    if OCR_REDUCED_SCALE_FOR_LONG_DOCS <= 0.0:
        errors.append("OCR_REDUCED_SCALE_FOR_LONG_DOCS must be positive")
    if OCR_TORCH_NUM_THREADS < 1:
        errors.append("OCR_TORCH_NUM_THREADS must be at least 1")

    # Pixel budget / rendering
    if PDF_TARGET_DPI < 72:
        errors.append("PDF_TARGET_DPI must be at least 72")
    if PDF_MAX_MEGAPIXELS <= 0.5:
        errors.append("PDF_MAX_MEGAPIXELS must be greater than 0.5")
    # Note: OCR_PDF_SCALE is ignored if PDF_USE_PIXEL_BUDGET is true

    # Quote extraction
    if QUOTE_CONTEXT_CHARS < 0:
        errors.append("QUOTE_CONTEXT_CHARS must be non-negative")
    if QUOTE_CONTEXT_CHARS > 200:
        errors.append("QUOTE_CONTEXT_CHARS should not exceed 200")
    if MAX_QUOTE_LENGTH < 50:
        errors.append("MAX_QUOTE_LENGTH must be at least 50")
    if MAX_QUOTE_LENGTH > 1000:
        errors.append("MAX_QUOTE_LENGTH should not exceed 1000")
    if not 0.0 <= MIN_ANSWER_CONFIDENCE <= 1.0:
        errors.append("MIN_ANSWER_CONFIDENCE must be between 0.0 and 1.0")

    # Email configuration (only validate if email feature is being used)
    # Note: These are only required if users enable email ingest feature
    # Application can run without these if email feature is not used
    if EMAIL_RATE_LIMIT_JOBS_PER_DAY < 1:
        errors.append("EMAIL_RATE_LIMIT_JOBS_PER_DAY must be at least 1")
    if EMAIL_RATE_LIMIT_JOBS_PER_DAY > 1000:
        errors.append("EMAIL_RATE_LIMIT_JOBS_PER_DAY should not exceed 1000")
    if EMAIL_MAX_ATTACHMENT_SIZE_MB < 1:
        errors.append("EMAIL_MAX_ATTACHMENT_SIZE_MB must be at least 1")
    if EMAIL_MAX_ATTACHMENT_SIZE_MB > 100:
        errors.append("EMAIL_MAX_ATTACHMENT_SIZE_MB should not exceed 100")
    if EMAIL_MAX_TOTAL_SIZE_MB < EMAIL_MAX_ATTACHMENT_SIZE_MB:
        errors.append("EMAIL_MAX_TOTAL_SIZE_MB must be at least EMAIL_MAX_ATTACHMENT_SIZE_MB")
    if EMAIL_MAX_TOTAL_SIZE_MB > 200:
        errors.append("EMAIL_MAX_TOTAL_SIZE_MB should not exceed 200")
    if EMAIL_VERIFICATION_EXPIRY_HOURS < 1:
        errors.append("EMAIL_VERIFICATION_EXPIRY_HOURS must be at least 1")
    if EMAIL_VERIFICATION_EXPIRY_HOURS > 168:  # 7 days
        errors.append("EMAIL_VERIFICATION_EXPIRY_HOURS should not exceed 168 (7 days)")

    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

# =============================================================================
# CONFIGURATION SUMMARY
# =============================================================================

def get_config_summary() -> dict:
    return {
        "environment": ENVIRONMENT,
        "debug_mode": DEBUG_MODE,
        "llm": {
            "model_name": LLM_MODEL_NAME,
            "max_context_tokens_per_question": LLM_MAX_CONTEXT_TOKENS_PER_QUESTION,
            "temperature": LLM_TEMPERATURE,
            "api_key_configured": bool(GEMINI_API_KEY)
        },
        "vector_search": {
            "top_k_per_question": VECTOR_SEARCH_TOP_K_PER_QUESTION,
            "max_source_quotes": VECTOR_SEARCH_MAX_SOURCE_QUOTES
        },
        "chunking": {
            "l1_target_tokens": CHUNK_L1_TARGET_TOKENS,
            "l1_max_tokens": CHUNK_L1_MAX_TOKENS,
            "l2_window_tokens": CHUNK_L2_WINDOW_TOKENS,
            "l2_overlap_tokens": CHUNK_L2_OVERLAP_TOKENS
        },
        "file_processing": {
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "supported_types": SUPPORTED_FILE_TYPES,
            "pdf_max_pages": PDF_MAX_PAGES
        },
        "database": {"url_configured": bool(DATABASE_URL), "echo": DATABASE_ECHO},
        "supabase": {"url_configured": bool(SUPABASE_URL), "key_configured": bool(SUPABASE_KEY)},
        "quote_extraction": {
            "context_chars": QUOTE_CONTEXT_CHARS,
            "max_quote_length": MAX_QUOTE_LENGTH,
            "min_answer_confidence": MIN_ANSWER_CONFIDENCE
        },
        "ocr": {
            "det_arch": OCR_DET_ARCH,
            "reco_arch": OCR_RECO_ARCH,
            "det_bs": OCR_DET_BATCH_SIZE,
            "reco_bs": OCR_RECO_BATCH_SIZE,
            "scale": OCR_PDF_SCALE,
            "use_pixel_budget": PDF_USE_PIXEL_BUDGET,
            "target_dpi": PDF_TARGET_DPI,
            "max_megapixels": PDF_MAX_MEGAPIXELS,
            "page_chunk_size": OCR_PAGE_CHUNK_SIZE,
            "max_pages_per_request": OCR_MAX_PAGES_PER_REQUEST,
            "long_doc_page_threshold": OCR_LONG_DOC_PAGE_THRESHOLD,
            "reduced_scale_for_long_docs": OCR_REDUCED_SCALE_FOR_LONG_DOCS,
            "mixed_precision": OCR_ENABLE_MIXED_PRECISION,
            "torch_num_threads": OCR_TORCH_NUM_THREADS,
            "enable_request_queue": OCR_ENABLE_REQUEST_QUEUE,
            "max_concurrent_requests": OCR_MAX_CONCURRENT_REQUESTS,
            "unload_models_after_use": OCR_UNLOAD_MODELS_AFTER_USE,
            "force_gc_frequency": OCR_FORCE_GC_FREQUENCY,
        }
    }

# =============================================================================
# RECOMMENDED CONFIGURATIONS
# =============================================================================

# 1GB RAM Koyeb instance (OPTIMIZED FOR OOM PREVENTION):
# - OCR_DET_ARCH=db_mobilenet_v3_large
# - OCR_RECO_ARCH=crnn_mobilenet_v3_small
# - PDF_USE_PIXEL_BUDGET=true
# - PDF_TARGET_DPI=200
# - PDF_MAX_MEGAPIXELS=1.6
# - OCR_MAX_PAGES=30 (hard limit for safety)
# - OCR_DET_BATCH_SIZE=1, OCR_RECO_BATCH_SIZE=32
# - OCR_PAGE_CHUNK_SIZE=1 (single page chunks)
# - OCR_TORCH_NUM_THREADS=1 (and also set OMP/OPENBLAS/MKL/NUMEXPR to 1 in env)
# - OCR_ENABLE_REQUEST_QUEUE=true (serialize OCR requests)
# - OCR_MAX_CONCURRENT_REQUESTS=1 (prevent concurrent overload)
# - OCR_UNLOAD_MODELS_AFTER_USE=true (free memory after each document)
# - OCR_FORCE_GC_FREQUENCY=1 (aggressive garbage collection)
#
# For 2GB+ RAM instances (better performance):
# - PDF_MAX_MEGAPIXELS=2.0
# - OCR_RECO_BATCH_SIZE=32
# - OCR_PAGE_CHUNK_SIZE=2–3
# - OCR_ENABLE_REQUEST_QUEUE=false (allow concurrent processing)
# - OCR_UNLOAD_MODELS_AFTER_USE=false (keep models loaded for speed)
