# Document Processing Flow - Complete Technical Traceback

This document provides a comprehensive technical analysis of how documents flow through the Attenly application from upload to vector database storage. Use this guide to understand the current architecture and identify where new file ingestion types should be integrated.

## Overview

The document processing pipeline follows a sophisticated multi-stage architecture:
1. **File Upload & Validation** → 2. **Classification & Routing** → 3. **Content Extraction** → 4. **Two-Level Chunking** → 5. **Vector Storage**

Each document goes through ~15 different classes/services and multiple processing stages before being stored in the vector database.

---

## Stage 1: File Upload & Initial Processing

### Entry Point: FastAPI Router
**File**: `backend/app/routers/agents.py`  
**Function**: `upload_files()` (lines 85-220)

```python
@router.post("/files/upload")
async def upload_files(files: List[UploadFile] = File(...), current_user = Depends(get_current_user)):
```

**Processing Steps**:
1. **File Reception**: Receives `List[UploadFile]` from FastAPI
2. **User Context Setup**: 
   - Gets current user via `get_current_user()`
   - Initializes `uploaded_files_storage[user_id]` dictionary
   - Clears any existing report cache
3. **Vector Store Initialization**: 
   - `vector_store_manager.get_store(user_id)` creates user-specific ChromaDB collection
4. **File Processing Loop**: Each file goes through:
   - Content reading: `content = await file.read()`
   - Hash calculation: `calculate_content_hash(content)` (SHA-256)
   - Duplicate detection: `find_duplicate_file(user_id, content_hash)`

**Key Classes/Functions Used**:
- `VectorStoreManager.get_store()` → Creates `VectorStore` instance
- `calculate_content_hash()` → SHA-256 hash for duplicate detection
- `find_duplicate_file()` → Searches existing user files by hash
- `PerformanceMonitor` → Tracks timing metrics throughout

---

## Stage 2: Document Validation & Classification

### Document Processor Entry
**File**: `backend/app/services/document_processor.py`  
**Class**: `DocumentProcessor`  
**Method**: `validate_document()` → `process_document()`

```python
validation_result = document_processor.validate_document(content, file.filename)
# If validation passes:
processing_result = await document_processor.process_document(
    file_id=file_id, content=content, filename=file.filename, vector_store=vector_store
)
```

### Document Classification Pipeline
**File**: `backend/app/services/document_classifier.py`  
**Class**: `DocumentClassifier`

**Classification Process**:
1. **File Type Detection** (`_detect_file_type()`):
   ```python
   extension_map = {
       'pdf': FileType.PDF,
       'docx': FileType.DOCX,
       'doc': FileType.DOC,
       'txt': FileType.TXT
   }
   ```

2. **PDF Content Analysis** (`_analyze_pdf_content()`):
   - Opens PDF with PyMuPDF: `doc = fitz.open(stream=content, filetype="pdf")`
   - Analyzes first 5 pages for performance
   - Calculates metrics:
     - `avg_words_per_page` (threshold: 50 words)
     - `text_density` (threshold: 0.005)
     - `total_images` per page
   - **Content Type Classification**:
     - `TEXT_BASED`: Extractable text content
     - `IMAGE_BASED`: Primarily scanned/image content  
     - `MIXED`: Both text and images
     - `EMPTY`: No meaningful content

3. **Processor Recommendation** (`_recommend_processor()`):
   - `TEXT_BASED` PDF → `ProcessorType.PDF`
   - `IMAGE_BASED` PDF → `ProcessorType.OCR` (**Now Available**)
   - `MIXED` PDF → `ProcessorType.OCR` (**Now Available**)
   - Other file types → `ProcessorType.UNSUPPORTED`

**Enums Used**:
```python
class FileType(Enum):
    PDF = "pdf"
    DOCX = "docx" 
    DOC = "doc"
    TXT = "txt"
    UNKNOWN = "unknown"

class ContentType(Enum):
    TEXT_BASED = "text_based"
    IMAGE_BASED = "image_based" 
    MIXED = "mixed"
    EMPTY = "empty"
    UNKNOWN = "unknown"

class ProcessorType(Enum):
    PDF = "pdf"
    OCR = "ocr"                    # OCR processor for image-based PDFs
    UNSUPPORTED = "unsupported"
```

---

## Stage 3: Content Extraction & PDF Processing

### Document Processor Architecture
**File**: `backend/app/services/document_processor.py`

The system uses a **plugin-like architecture** with abstract base classes:

```python
class BaseDocumentProcessor(ABC):
    @abstractmethod
    def supported_extensions(self) -> List[str]
    @abstractmethod  
    def validate_document(self, content: bytes, filename: str) -> Dict[str, Any]
    @abstractmethod
    def extract_content(self, content: bytes, filename: str) -> Dict[str, Any]
```

### PDF Document Processor
**Class**: `PDFDocumentProcessor` (inherits from `BaseDocumentProcessor`)

**Processing Pipeline**:
1. **Validation**: 
   - File extension check
   - Size limit check (500MB)
   - PDF structure validation with PyMuPDF

2. **Content Extraction** (`extract_content()`):
   - Calls `PDFProcessor.process_pdf(content, filename)`
   - Returns structured data with pages, metadata, statistics

### PDF Parser - Core Content Processing
**File**: `backend/app/services/pdf_parser.py`  
**Class**: `PDFProcessor`

This is the most complex part of the pipeline with sophisticated table detection and text extraction:

**Main Processing Method**:
```python
def process_pdf(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    pdf_data = pdf_to_structured_data(pdf_bytes, filename)
    # Add token counts and enhance metadata
    # Returns structured data with pages, tables, paragraphs
```

**PDF Processing Steps** (per page):

1. **Word Extraction**: 
   ```python
   words = page.get_text("words")  # PyMuPDF
   words.sort(key=lambda w: (round(w[1], 1), w[0]))  # Sort by position
   ```

2. **Character Width Calculation**:
   ```python
   widths = [(w[2] - w[0]) / max(len(w[4]), 1) for w in words if w[4].strip()]
   char_w = statistics.median(widths)  # Used for column alignment
   ```

3. **Row Grouping** (`_group_words_into_rows()`):
   - Groups words by Y-coordinate within tolerance
   - Handles superscripts with special tolerance
   - Creates text lines from word positions

4. **Table Structure Detection**:
   - **Vertical Rules** (`_collect_vertical_rules()`):
     ```python
     for d in page.get_drawings():  # Extract vector graphics
         # Detects vertical lines, rectangles, and quadrilaterals
         # Groups and merges nearby vertical lines
     ```
   - **Horizontal Rules** (`_collect_horizontal_rules()`):
     ```python
     # Similar process for horizontal lines
     # Merges segments within tolerance thresholds
     ```

5. **Table Formatting** (`_replace_tables_in_lines()`):
   - Inserts vertical bars (`|`) at detected column boundaries
   - Adds horizontal dashes (`-`) for table separators
   - Creates markdown-compatible table structure

6. **Content Structuring**:
   - `_identify_table_blocks()`: Finds table boundaries in formatted text
   - `_identify_paragraph_blocks()`: Identifies paragraph boundaries for chunking

**Output Structure**:
```python
{
    "pages": [
        {
            "page_number": int,
            "lines": List[str],          # Raw text lines
            "markdown": str,             # Formatted markdown with tables
            "tables": List[Dict],        # Table metadata
            "paragraphs": List[Dict],    # Paragraph metadata
            "token_count": int           # Using tiktoken
        }
    ],
    "full_markdown": str,
    "metadata": {...},
    "statistics": {
        "total_tokens": int,
        "total_tables": int,
        "total_paragraphs": int
    }
}
```

### OCR Document Processor
**Class**: `OCRDocumentProcessor` (inherits from `BaseDocumentProcessor`)
**File**: `backend/app/services/ocr_document_processor.py`

**Processing Pipeline for Image-Based PDFs**:
1. **Validation**: 
   - File extension check (PDF only)
   - Size limit check (configurable via `OCR_MAX_FILE_SIZE_MB`)
   - Page count limits (configurable via `OCR_MAX_PAGES_PER_REQUEST`)
   - PDF structure validation with PyMuPDF

2. **OCR Processing** (`extract_content()`):
   - Calls `OCRService.process_pdf_bytes(content, filename, timeout)`
   - Dynamic timeout calculation based on page count
   - Quality metrics assessment with fallback logic
   - Returns structured data compatible with existing pipeline

### OCR Service - Core Text Extraction
**File**: `backend/app/services/ocr_service.py`  
**Class**: `OCRService`

**Main Processing Method**:
```python
def process_pdf_bytes(self, content: bytes, filename: str, timeout_seconds: int = 300) -> OCRResult:
    # Load PDF with DocTR at 300 DPI equivalent
    docs = DocumentFile.from_pdf(tmp_path, scale=OCR_PDF_SCALE)  # 4.17
    
    # Run OCR with exact configuration from working script
    result = self.model(docs)
    export_data = result.export()
    
    # Calculate quality metrics and convert to Attenly schema
```

**OCR Processing Steps**:

1. **Model Initialization** (Singleton Pattern):
   ```python
   self.model = ocr_predictor(
       det_arch="db_resnet50",    # Text detection architecture
       reco_arch="parseq",        # Text recognition architecture  
       pretrained=True,
       det_bs=4,                  # Detection batch size
       reco_bs=1024,             # Recognition batch size
       resolve_lines=True,        # Group words into lines
       resolve_blocks=True,       # Group lines into blocks
   )
   ```

2. **CUDA Optimization** (if available):
   ```python
   if torch.cuda.is_available() and OCR_CUDA_DEVICES:
       self.model.det_predictor.model.cuda()
       self.model.reco_predictor.model.cuda()
   ```

3. **Quality Assessment**:
   ```python
   def _calculate_quality_metrics(self, doctr_export: Dict[str, Any]) -> OCRQualityMetrics:
       # Calculate mean confidence across all detected words
       # Calculate coverage ratio (confident words / total words)
       # Determine if quality meets configured thresholds
   ```

4. **Schema Conversion**:
   ```python
   def convert_to_attenly_schema(self, doctr_export: Dict[str, Any], filename: str) -> Dict[str, Any]:
       # Convert DocTR's pages/blocks/lines/words structure
       # Generate markdown text from OCR results
       # Create compatible metadata and statistics
       # Maintain same structure as PDFProcessor output
   ```

5. **Debug Output** 
   - Raw DocTR export data → `ocr_debug/{timestamp}_{filename}_doctr_export.json`
   - Converted Attenly schema → `ocr_debug/{timestamp}_{filename}_attently_schema.json`
   - Extracted text content → `ocr_debug/{timestamp}_{filename}_extracted_text.txt`
   - Quality metrics → `ocr_debug/{timestamp}_{filename}_quality_metrics.json`

**OCR Configuration** (`backend/app/config.py`):
```python
# Model and Cache Configuration
OCR_CACHE_DIR = "/var/cache/attenly/doctr"
OCR_CUDA_DEVICES = ""  # Empty = CPU only

# Processing Limits  
OCR_MAX_PAGES_PER_REQUEST = 150
OCR_MAX_FILE_SIZE_MB = 60

# Quality Thresholds
OCR_CONFIDENCE_THRESHOLD = 0.55    # Minimum word confidence
OCR_COVERAGE_THRESHOLD = 0.65      # Minimum coverage ratio

# Timeout Configuration (Dynamic)
OCR_BASE_TIMEOUT_SECONDS = 120     # Base timeout for 50 pages
OCR_TIMEOUT_PER_50_PAGES = 120     # Additional time per 50 pages
OCR_MAX_TIMEOUT_SECONDS = 480      # 8 minutes maximum
```

**OCR Output Structure** (Same as PDF):
```python
{
    "pages": [
        {
            "page_number": int,
            "lines": List[str],          # OCR extracted text lines
            "markdown": str,             # Formatted markdown 
            "tables": List[Dict],        # Empty for now (future enhancement)
            "paragraphs": List[Dict],    # Simple paragraph grouping
            "token_count": int           # Using tiktoken
        }
    ],
    "full_markdown": str,
    "metadata": {
        "creator": "OCR Processor",
        "filename": str,
        "total_pages": int
    },
    "statistics": {
        "total_tokens": int,
        "total_tables": 0,           # OCR doesn't detect tables yet
        "total_paragraphs": int
    }
}
```

**Quality Control & Fallback**:
- Documents with quality below thresholds are treated as empty
- Configurable confidence and coverage thresholds
- Detailed quality metrics logged for troubleshooting
- Fallback to empty document maintains pipeline integrity

---

## Stage 4: Two-Level Chunking Strategy

**File**: `backend/app/services/chunking_service.py`  
**Class**: `ChunkingService`

The system implements a sophisticated **two-level chunking strategy** optimized for both LLM context and vector search:

### L1 Chunks (Semantic Sections)
**Target**: 1000-1600 tokens  
**Method**: `_create_page_based_chunks()`

```python
def _create_page_based_chunks(self, document_id: str, pdf_data: Dict[str, Any], filename: str) -> List[Dict]:
    chunks = []
    current_chunk = self._new_l1_chunk(document_id, filename)
    
    for page in pdf_data["pages"]:
        page_tokens = page["token_count"]
        
        # If adding this page would exceed L1_MAX, finalize current chunk
        if current_chunk["token_count"] + page_tokens > self.L1_MAX and current_chunk["text"]:
            chunks.append(current_chunk.copy())
            current_chunk = self._new_l1_chunk(document_id, filename)
```

**L1 Chunk Structure**:
```python
{
    "chunk_id": "L1_uuid",
    "document_id": str,
    "level": 1,
    "text": str,                    # Full text with page markers
    "start_page": int,
    "end_page": int, 
    "filename": str,
    "token_count": int,
    "tables": List[Dict],          # All tables in this chunk
    "paragraphs": List[Dict]       # All paragraphs in this chunk
}
```

### L2 Chunks (Search Windows)
**Target**: 512 tokens with 128 token overlap  
**Method**: `_create_window_chunks()`

```python
def _create_window_chunks(self, l1_chunk: Dict) -> List[Dict]:
    # Split text into tokens using tiktoken
    if self.encoder:
        tokens = self.encoder.encode(text)
    
    # Create sliding windows
    while start_idx < len(tokens):
        end_idx = min(start_idx + self.L2_WINDOW, len(tokens))
        window_tokens = tokens[start_idx:end_idx]
        window_text = self.encoder.decode(window_tokens)
        
        # Move to next window with overlap
        start_idx += self.L2_WINDOW - self.L2_OVERLAP
```

**L2 Chunk Structure**:
```python
{
    "chunk_id": "L2_uuid",
    "parent_id": "L1_uuid",        # Links back to L1 chunk
    "document_id": str,
    "level": 2,
    "text": str,                   # Window text
    "offset_start": int,           # Token position in parent
    "offset_end": int,
    "token_count": int,
    "window_index": int,           # Sequential window number
    "filename": str,
    "start_page": int,
    "end_page": int
}
```

**Token Counting**:
```python
try:
    import tiktoken
    self.encoder = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
except ImportError:
    # Fallback: ~4 characters per token
    return len(text) // 4
```

---

## Stage 5: Vector Storage & Embeddings

**File**: `backend/app/services/vector_store.py`  
**Class**: `VectorStore`

### Vector Store Architecture
The system uses **user-isolated ChromaDB collections** with batch embedding generation:

```python
def __init__(self, user_id: str):
    self.collection_name = f"user_{user_id}"
    self.client = chromadb.EphemeralClient()
    self.collection = self.client.get_or_create_collection(
        name=self.collection_name,
        metadata={"user_id": user_id, "embedding_model": "text-embedding-004"}
    )
```

### Embedding Generation
**File**: `backend/app/services/embedding_batch_service.py`

Uses **Google's text-embedding-004 model** with optimized batch processing:

```python
async def store_document_chunks(self, document_id: str, l1_chunks: List[Dict], l2_chunks: List[Dict]) -> int:
    # Prepare L2 chunks for embedding
    documents = [l2_chunk["text"] for l2_chunk in l2_chunks]
    
    # Generate embeddings in batches
    embeddings = await self.embedding_service.generate_embeddings_batch(documents)
    
    # Store in ChromaDB with pre-computed embeddings
    self.collection.add(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )
```

### Metadata Structure
Each L2 chunk is stored with rich metadata for filtering and retrieval:

```python
metadata = {
    "document_id": document_id,
    "parent_id": l2_chunk["parent_id"],      # Link to L1 chunk
    "level": 2,
    "token_count": l2_chunk["token_count"],
    "window_index": l2_chunk["window_index"],
    "filename": l2_chunk["filename"],
    "start_page": l2_chunk["start_page"],
    "end_page": l2_chunk["end_page"],
    "offset_start": l2_chunk["offset_start"],
    "offset_end": l2_chunk["offset_end"],
    # Parent chunk metadata
    "parent_start_page": parent_chunk["start_page"],
    "parent_end_page": parent_chunk["end_page"],
    "has_tables": len(parent_chunk.get("tables", [])) > 0,
    "table_count": len(parent_chunk.get("tables", [])),
    "paragraph_count": len(parent_chunk.get("paragraphs", []))
}
```

---

## Performance Monitoring & Optimization

**File**: `backend/app/services/performance_monitor.py`  
**Class**: `PerformanceMonitor`

The system tracks detailed timing metrics throughout the pipeline:

### Timing Breakdown (per file):
1. **File Upload Read**: `file_upload_read`
2. **Hash Calculation**: `hash_calculation`  
3. **Duplicate Check**: `duplicate_check`
4. **Document Validation**: `document_validation`
5. **Document Processing Pipeline**: `document_processing_pipeline`
6. **Classification**: `document_classification`
7. **Content Extraction**: `content_extraction`
8. **L1 Chunking**: `l1_chunking`
9. **L2 Chunking**: `l2_chunking`
10. **Vector Storage**: `vector_storage`
11. **Batch Embedding Generation**: `batch_embedding_generation`

### Usage Example:
```python
with time_operation("content_extraction", {"filename": filename}) as timer:
    extraction_result = processor.extract_content(content, filename)
    performance_monitor.update_file_metric(file_id, "content_extraction_time", timer.stop().duration)
```

---

## Integration Points for New File Types

### 1. Document Classification (`document_classifier.py`)

**Add new file type**:
```python
class FileType(Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    # ADD NEW FILE TYPES HERE
    XLSX = "xlsx"
    CSV = "csv"
```

**Extend file type detection**:
```python
def _detect_file_type(self, content: bytes, filename: str) -> FileType:
    extension_map = {
        'pdf': FileType.PDF,
        'docx': FileType.DOCX,
        # ADD NEW MAPPINGS HERE
        'xlsx': FileType.XLSX,
        'csv': FileType.CSV,
    }
```

**Add content analysis method**:
```python
def _analyze_content_type(self, content: bytes, file_type: FileType) -> Dict[str, Any]:
    if file_type == FileType.XLSX:
        return self._analyze_excel_content(content)
    elif file_type == FileType.CSV:
        return self._analyze_csv_content(content)
```

### 2. Document Processor (`document_processor.py`)

**Create new processor class**:
```python
class ExcelDocumentProcessor(BaseDocumentProcessor):
    @property
    def supported_extensions(self) -> List[str]:
        return ['.xlsx', '.xls']
    
    @property  
    def processor_name(self) -> str:
        return "Excel Processor"
    
    def validate_document(self, content: bytes, filename: str) -> Dict[str, Any]:
        # Excel-specific validation
        pass
        
    def extract_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        # Excel-specific content extraction
        # Must return data compatible with ChunkingService
        pass
```

**Register new processor**:
```python
def _register_processors(self):
    # Existing processors...
    
    # Register new processors
    excel_processor = ExcelDocumentProcessor()
    for ext in excel_processor.supported_extensions:
        self.processors[ext.lower()] = excel_processor
```

### 3. Content Structure Requirements

New processors must output data compatible with the chunking service:

```python
{
    "pages": [  # Can represent sheets, sections, etc.
        {
            "page_number": int,
            "markdown": str,        # Text content for chunking
            "token_count": int,
            "tables": List[Dict],   # Structured data elements
            "paragraphs": List[Dict]  # Text sections
        }
    ],
    "metadata": {
        "total_pages": int,
        # Processor-specific metadata
    },
    "statistics": {
        "total_tokens": int,
        "total_tables": int,
        "total_paragraphs": int
    }
}
```

### 4. OCR Integration Point

For image-based content, the integration point is in the document classification:

```python
def _recommend_processor(self, file_type: FileType, content_analysis: Dict[str, Any]) -> ProcessorType:
    content_type = content_analysis["content_type"]
    
    if file_type == FileType.PDF:
        if content_type == ContentType.IMAGE_BASED:
            return ProcessorType.OCR  # Add OCR processor type
```

**OCR processor structure**:
```python
class OCRDocumentProcessor(BaseDocumentProcessor):
    def __init__(self):
        self.ocr_service = OCRService()  # backend/app/services/ocr_service.py exists
    
    def extract_content(self, content: bytes, filename: str) -> Dict[str, Any]:
        # Use OCR to extract text from image-based content
        # Convert to same structure as PDFProcessor output
        pass
```

---

## Error Handling & State Management

### Document States
Documents maintain state throughout the pipeline:

```python
file_record = {
    "id": file_id,
    "name": filename,
    "content_hash": content_hash,
    "size": len(content), 
    "type": content_type,
    "content": content,
    "status": "processing"  # → "uploaded" | "failed" | "duplicate"
}
```

### Error Handling Strategy
- **Graceful Failures**: Individual file failures don't stop batch processing
- **Detailed Error Messages**: Specific error information for each failure type
- **State Persistence**: File status maintained throughout processing
- **Performance Monitoring**: Failed operations still tracked for optimization

### Memory Management
- **User Isolation**: Each user has separate vector store collection
- **Cleanup Methods**: `cleanup_user_session()` removes all user data
- **In-Memory Storage**: `uploaded_files_storage` dictionary per user
- **Cache Management**: Report cache cleared when files change

---

## Configuration & Customization

### Chunking Configuration
**File**: `backend/app/config.py`

```python
CHUNK_L1_TARGET_TOKENS = 1000    # Target size for L1 chunks
CHUNK_L1_MAX_TOKENS = 1600       # Maximum size for L1 chunks  
CHUNK_L2_WINDOW_TOKENS = 512     # L2 chunk window size
CHUNK_L2_OVERLAP_TOKENS = 128    # L2 chunk overlap
VECTOR_SEARCH_TOP_K_PER_QUESTION = 40  # Chunks per question
```

### Classification Thresholds
**File**: `backend/app/services/document_classifier.py`

```python
MIN_WORDS_THRESHOLD = 50              # Below this = likely image-based
MIN_TEXT_DENSITY_THRESHOLD = 0.005   # Text-to-content ratio
MAX_PAGES_TO_ANALYZE = 5             # Analyze first N pages
```

---

## Summary: Complete Processing Chain

A document uploaded to Attenly goes through this complete chain:

1. **FastAPI Router** (`agents.py`) receives upload
2. **Document Processor** (`document_processor.py`) orchestrates processing  
3. **Document Classifier** (`document_classifier.py`) analyzes file type/content
4. **PDF Document Processor** routes to PDF processing
5. **PDF Parser** (`pdf_parser.py`) extracts structured content with table detection
6. **Chunking Service** (`chunking_service.py`) creates two-level chunks
7. **Vector Store** (`vector_store.py`) generates embeddings and stores in ChromaDB
8. **Performance Monitor** (`performance_monitor.py`) tracks timing throughout

**Total Classes Involved**: ~15 classes across 8 service files  
**Total Processing Time**: Typically 2-10 seconds per document  
**Storage**: L2 chunks with embeddings in user-specific ChromaDB collections

This architecture provides a solid foundation for extending to new file types while maintaining performance and user isolation.
