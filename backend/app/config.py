"""
Centralized Configuration for Attenly Backend

This file contains all configurable parameters for the backend services.
Modify these values to tune performance, adjust processing limits, and customize behavior.
"""

import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# AUTHENTICATION & EXTERNAL SERVICES
# =============================================================================

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # Service role key
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")  # Public anon key for user operations

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =============================================================================
# LLM SERVICE CONFIGURATION
# =============================================================================

# Model Selection
LLM_MODEL_NAME = "gemini-2.5-flash-lite"

# Context and Token Limits
LLM_MAX_CONTEXT_TOKENS_PER_QUESTION = 4000 # Recommended: 4000-8000 for dev, 8000-12000 for prod
LLM_TEMPERATURE = 0.0

# Processing Configuration
LLM_THINKING_BUDGET = 0  # 0 for cost optimization
LLM_RESPONSE_FORMAT = "application/json"

# =============================================================================
# VECTOR SEARCH CONFIGURATION
# =============================================================================

# Search Parameters
VECTOR_SEARCH_TOP_K_PER_QUESTION = 10
VECTOR_SEARCH_MAX_SOURCE_QUOTES = 3

# =============================================================================
# EMBEDDING GENERATION CONFIGURATION
# =============================================================================

# Batch Embedding Parameters
EMBEDDING_BATCH_SIZE = 100  # Number of texts to embed in a single batch (max 100 for Google AI)
EMBEDDING_MAX_RETRIES = 1  # Maximum number of retry attempts for failed batches
EMBEDDING_TIMEOUT_SECONDS = 30  # Timeout for embedding API requests
EMBEDDING_MODEL_NAME = "gemini-embedding-001"  # Google AI embedding model (correct name for batch API)
EMBEDDING_MAX_CONCURRENT_BATCHES = 1  # Maximum concurrent batch requests

# =============================================================================
# INTELLIGENT QUOTE EXTRACTION CONFIGURATION
# =============================================================================

# Quote Extraction Features
QUOTE_CONTEXT_CHARS = 50  # Characters of context before/after extracted quote
MAX_QUOTE_LENGTH = 300    # Maximum length of extracted quote text
MIN_ANSWER_CONFIDENCE = 0.7  # Minimum confidence threshold for including quotes

# Answer Quality Analysis
ANSWER_NOT_FOUND_PHRASES = [
    "not found", "not specified", "not available", "not mentioned", 
    "not provided", "unknown", "unclear", "not stated", "not indicated",
    "no information", "cannot be determined", "not disclosed"
]

# =============================================================================
# DOCUMENT CHUNKING CONFIGURATION
# =============================================================================

# L1 Chunk Configuration (Semantic sections)
CHUNK_L1_TARGET_TOKENS = 1200
CHUNK_L1_MAX_TOKENS = 2000

# L2 Chunk Configuration (Sliding windows for vector search)
CHUNK_L2_WINDOW_TOKENS = 512
CHUNK_L2_OVERLAP_TOKENS = 80

# =============================================================================
# DOCUMENT PROCESSING CONFIGURATION
# =============================================================================

# File Upload Limits
MAX_FILE_SIZE_MB = 50
SUPPORTED_FILE_TYPES = [".pdf", ".docx", ".txt"]

# PDF Processing
PDF_MAX_PAGES = 500
PDF_EXTRACT_IMAGES = False

# =============================================================================
# OCR CONFIGURATION
# =============================================================================

# Model and Cache Configuration
OCR_CACHE_DIR = os.getenv("ATTENLY_CACHE_DIR", "/cache/attenly/doctr")
OCR_CUDA_DEVICES = os.getenv("CUDA_VISIBLE_DEVICES", "")  # Empty = CPU only

# Processing Limits
OCR_MAX_PAGES_PER_REQUEST = int(os.getenv("OCR_MAX_PAGES", "150"))
OCR_MAX_FILE_SIZE_MB = int(os.getenv("OCR_MAX_FILE_SIZE_MB", "60"))

# Quality Thresholds
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.55"))
OCR_COVERAGE_THRESHOLD = float(os.getenv("OCR_COVERAGE_THRESHOLD", "0.65"))

# Timeout Configuration
OCR_BASE_TIMEOUT_SECONDS = int(os.getenv("OCR_BASE_TIMEOUT", "120"))  # 120s for 50 pages
OCR_TIMEOUT_PER_50_PAGES = int(os.getenv("OCR_TIMEOUT_PER_50_PAGES", "120"))
OCR_MAX_TIMEOUT_SECONDS = int(os.getenv("OCR_MAX_TIMEOUT", "480"))  # 8 minutes max

# Model Configuration
OCR_DET_ARCH = "db_resnet50"
OCR_RECO_ARCH = "parseq"
OCR_DET_BATCH_SIZE = 4
OCR_RECO_BATCH_SIZE = 1024
OCR_PDF_SCALE = 4.17  # 300 DPI equivalent

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Database Settings
DATABASE_URL = "sqlite:///./app.db"
DATABASE_ECHO = False

# =============================================================================
# DEVELOPMENT & DEBUGGING
# =============================================================================

# Environment
ENVIRONMENT = "development"
DEBUG_MODE = False

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# =============================================================================
# PERFORMANCE & OPTIMIZATION
# =============================================================================

# Concurrency
MAX_CONCURRENT_UPLOADS = 5
MAX_CONCURRENT_LLM_REQUESTS = 3

# Caching (for future use)
ENABLE_CACHING = False
CACHE_TTL_SECONDS = 3600

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_config():
    """
    Validate configuration values and raise errors for invalid settings.
    Call this during application startup to catch configuration issues early.
    """
    errors = []
    
    # Required environment variables
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL is required")
    if not SUPABASE_KEY:
        errors.append("SUPABASE_KEY is required")
    if not SUPABASE_ANON_KEY:
        errors.append("SUPABASE_ANON_KEY is required for user operations")
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is required for LLM functionality")
    
    # Validate numeric ranges
    if LLM_MAX_CONTEXT_TOKENS_PER_QUESTION < 1000:
        errors.append("LLM_MAX_CONTEXT_TOKENS_PER_QUESTION must be at least 1000")
    if LLM_MAX_CONTEXT_TOKENS_PER_QUESTION > 32000:
        errors.append("LLM_MAX_CONTEXT_TOKENS_PER_QUESTION should not exceed 32000")
    
    if not 0.0 <= LLM_TEMPERATURE <= 2.0:
        errors.append("LLM_TEMPERATURE must be between 0.0 and 2.0")
    
    if VECTOR_SEARCH_TOP_K_PER_QUESTION < 1:
        errors.append("VECTOR_SEARCH_TOP_K_PER_QUESTION must be at least 1")
    if VECTOR_SEARCH_TOP_K_PER_QUESTION > 100:
        errors.append("VECTOR_SEARCH_TOP_K_PER_QUESTION should not exceed 100")
    
    if CHUNK_L1_TARGET_TOKENS >= CHUNK_L1_MAX_TOKENS:
        errors.append("CHUNK_L1_TARGET_TOKENS must be less than CHUNK_L1_MAX_TOKENS")
    
    if CHUNK_L2_OVERLAP_TOKENS >= CHUNK_L2_WINDOW_TOKENS:
        errors.append("CHUNK_L2_OVERLAP_TOKENS must be less than CHUNK_L2_WINDOW_TOKENS")
    
    if MAX_FILE_SIZE_MB < 1:
        errors.append("MAX_FILE_SIZE_MB must be at least 1")
    
    # Validate quote extraction parameters
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
    
    # Validate embedding configuration
    if EMBEDDING_BATCH_SIZE < 1:
        errors.append("EMBEDDING_BATCH_SIZE must be at least 1")
    if EMBEDDING_BATCH_SIZE > 100:
        errors.append("EMBEDDING_BATCH_SIZE should not exceed 100 (Google AI limit)")
    
    if EMBEDDING_MAX_RETRIES < 0:
        errors.append("EMBEDDING_MAX_RETRIES must be non-negative")
    if EMBEDDING_MAX_RETRIES > 10:
        errors.append("EMBEDDING_MAX_RETRIES should not exceed 10")
    
    if EMBEDDING_TIMEOUT_SECONDS < 5:
        errors.append("EMBEDDING_TIMEOUT_SECONDS must be at least 5")
    if EMBEDDING_TIMEOUT_SECONDS > 300:
        errors.append("EMBEDDING_TIMEOUT_SECONDS should not exceed 300")
    
    if EMBEDDING_MAX_CONCURRENT_BATCHES < 1:
        errors.append("EMBEDDING_MAX_CONCURRENT_BATCHES must be at least 1")
    if EMBEDDING_MAX_CONCURRENT_BATCHES > 10:
        errors.append("EMBEDDING_MAX_CONCURRENT_BATCHES should not exceed 10")
    
    # Validate OCR configuration
    if OCR_MAX_PAGES_PER_REQUEST < 1:
        errors.append("OCR_MAX_PAGES_PER_REQUEST must be at least 1")
    if OCR_MAX_PAGES_PER_REQUEST > 1000:
        errors.append("OCR_MAX_PAGES_PER_REQUEST should not exceed 1000")
    
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
    if OCR_MAX_TIMEOUT_SECONDS > 7200:  # 2 hours max
        errors.append("OCR_MAX_TIMEOUT_SECONDS should not exceed 7200")
    
    if errors:
        raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors))

# =============================================================================
# CONFIGURATION SUMMARY
# =============================================================================

def get_config_summary() -> dict:
    """
    Get a summary of current configuration for debugging and monitoring.
    Excludes sensitive values like API keys.
    """
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
        "database": {
            "url_configured": bool(DATABASE_URL),
            "echo": DATABASE_ECHO
        },
        "supabase": {
            "url_configured": bool(SUPABASE_URL),
            "key_configured": bool(SUPABASE_KEY)
        },
        "quote_extraction": {
            "context_chars": QUOTE_CONTEXT_CHARS,
            "max_quote_length": MAX_QUOTE_LENGTH,
            "min_answer_confidence": MIN_ANSWER_CONFIDENCE
        }
    }

# =============================================================================
# RECOMMENDED CONFIGURATIONS
# =============================================================================

# Development Configuration Recommendations:
# - LLM_MAX_CONTEXT_TOKENS_PER_QUESTION: 4000-8000 (balance cost vs quality)
# - LLM_TEMPERATURE: 0.1 (consistent extraction)
# - VECTOR_SEARCH_TOP_K_PER_QUESTION: 5-10 (good coverage without noise)
# - CHUNK_L1_TARGET_TOKENS: 1000-1500 (good semantic chunks)
# - CHUNK_L2_WINDOW_TOKENS: 512 (optimal for vector search)

# Production Configuration Recommendations:
# - LLM_MAX_CONTEXT_TOKENS_PER_QUESTION: 8000-12000 (higher quality)
# - VECTOR_SEARCH_TOP_K_PER_QUESTION: 10-15 (comprehensive coverage)
# - Enable caching for better performance
# - Use PostgreSQL instead of SQLite
# - Set appropriate file size limits based on infrastructure
