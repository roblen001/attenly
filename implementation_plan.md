# Implementation Plan: OCR Performance Optimization

## Overview

Optimize OCR processing to reduce memory usage and drastically improve performance for documents in the 10-50 page range on 2GB+ instances. The current implementation reloads the entire PDF from disk multiple times (9 times for an 8-page document), causing processing times exceeding 300 seconds. The optimized implementation will load the PDF once and process it in appropriately-sized chunks, reducing processing time to 60-90 seconds for typical documents.

### Current Performance Issues

1. **Critical: Excessive Disk I/O** - The system calls `DocumentFile.from_pdf()` inside a loop, reloading the entire PDF from disk for every page chunk (lines ~204-215 in `ocr_service.py`)
2. **Over-conservative Configuration** - Settings optimized for 1GB instances are being used on 2GB+ instances:
   - `OCR_PAGE_CHUNK_SIZE=1` (processes one page at a time)
   - `OCR_PDF_SCALE=1.8` (lower than optimal resolution)
   - `OCR_RECO_BATCH_SIZE=8` (small recognition batch size)
3. **Unnecessary Model Unloading** - `OCR_UNLOAD_MODELS_AFTER_USE=true` causes model reload overhead
4. **Redundant PDF Loading** - First loads at scale=1.0 to count pages, then reloads for each chunk at target scale

### Solution Architecture

**Phase 1: Fix Critical I/O Bottleneck (80% improvement)**
- Load PDF once into memory at target scale (eliminate probe load)
- Store loaded document pages in memory
- Slice in-memory array for chunk processing (eliminate per-chunk reloads)

**Phase 2: Optimize Configuration (20% improvement)**
- Increase chunk size to 5 pages for 2GB+ instances
- Increase PDF scale to 2.5 for better quality
- Increase recognition batch size to 32
- Disable model unloading for faster repeated processing
- Allow 2 concurrent requests

**Phase 3: Add Monitoring (Quality of life)**
- Enhanced progress logging with timing information
- Memory usage tracking at key stages
- Performance metrics for optimization validation

### Expected Performance Gains

- **Current**: 8-page document = 300+ seconds
- **After Phase 1**: 8-page document = 120 seconds (60% reduction)
- **After Phase 2**: 8-page document = 60-90 seconds (70-80% reduction)
- **Memory**: Reduced peak memory due to eliminating redundant loads

## Types

No new type definitions required. Existing types in `ocr_service.py` are sufficient:
- `OCRQualityMetrics` (dataclass) - existing
- `OCRResult` (dataclass) - existing  
- `VerticalRule`, `HorizontalRule` type aliases - not modified

## Files

### Modified Files

**1. `backend/app/services/ocr_service.py`**
- Primary changes in `_process_pdf_internal()` method (lines ~180-280)
- Modify PDF loading logic to load once instead of multiple times
- Update chunking loop to slice in-memory document array
- Add enhanced progress logging and timing
- Remove redundant probe load for page counting
- Update memory management calls

**2. `backend/app/config.py`**
- Update OCR configuration defaults for 2GB+ instances
- Add comments documenting recommended settings by instance size
- Modify lines ~92-135 (OCR CONFIGURATION section)

**3. `backend/.env.example`**
- Update example environment variables to reflect optimized defaults
- Add documentation for performance tuning parameters

### No New Files Created

All changes are modifications to existing files. No new modules, classes, or services required.

### No Files Deleted

All existing files remain in use.

## Functions

### Modified Functions

**1. `OCRService._process_pdf_internal()` in `backend/app/services/ocr_service.py`**
- **Current location**: Lines ~180-280
- **Required changes**:
  1. Remove probe load at scale=1.0 (lines ~205-209)
  2. Load PDF once at target scale before loop
  3. Replace loop's `DocumentFile.from_pdf()` call with array slicing
  4. Add timing variables for progress logging
  5. Update memory management to account for single load
  6. Enhance progress logging with percentage complete and ETA

**Current problematic code** (lines ~204-217):
```python
for chunk_idx, start in enumerate(range(0, total_pages, chunk_size)):
    end = min(start + chunk_size, total_pages)
    
    # Loads entire PDF from disk EVERY iteration
    doc_window = DocumentFile.from_pdf(tmp_path, scale=chosen_scale)[start:end]
```

**Optimized code**:
```python
# Load PDF once at target scale (outside loop)
doc_full = DocumentFile.from_pdf(tmp_path, scale=chosen_scale)
total_pages = len(doc_full)

for chunk_idx, start in enumerate(range(0, total_pages, chunk_size)):
    end = min(start + chunk_size, total_pages)
    
    # Slice in-memory array (no disk I/O)
    doc_window = doc_full[start:end]
```

**2. `OCRService._choose_scale()` in `backend/app/services/ocr_service.py`**
- **Current location**: Lines ~154-158
- **Required changes**: Update thresholds to reflect optimized chunk sizes for 2GB instances

**3. `OCRService.get_model_info()` in `backend/app/services/ocr_service.py`**
- **Current location**: Lines ~455-485
- **Required changes**: Add performance optimization flags to returned info dict

### No New Functions

All optimizations use existing function structure.

### No Functions Removed

All existing functions remain, only internal implementation changes.

## Classes

### Modified Classes

**1. `OCRService` in `backend/app/services/ocr_service.py`**
- **Current location**: Lines ~64-505
- **Specific modifications**:
  - Update `_process_pdf_internal()` method implementation
  - Update `_choose_scale()` method logic
  - Add performance tracking variables to `__init__()` if needed
  - No changes to class structure, inheritance, or public API
  - No changes to singleton pattern implementation

### No New Classes

All changes are internal modifications to existing `OCRService` class.

### No Classes Removed

All existing classes remain in use.

## Dependencies

No new dependencies required. All optimization work uses existing packages:
- `torch` - already installed
- `doctr` (python-doctr[torch]) - already installed
- `psutil` - already installed for memory monitoring
- `asyncio` - Python standard library
- `tempfile` - Python standard library

### Version Constraints

No version changes required. Current versions in `requirements.txt` are compatible:
```
python-doctr[torch]==0.8.1
torch>=2.0.0,<3.0.0
torchvision>=0.15.0,<1.0.0
psutil==6.0.0
```

## Testing

### Manual Testing Strategy

**Test Case 1: Small Document (5-10 pages)**
1. Upload 8-page PDF through the application
2. Monitor processing time - should complete in 60-90 seconds
3. Verify OCR output quality matches previous implementation
4. Check logs for "Memory" entries to confirm single load

**Test Case 2: Medium Document (20-30 pages)**
1. Upload 25-page PDF through the application  
2. Monitor processing time - should complete in 180-240 seconds
3. Verify memory usage stays under 1.5GB
4. Check progress logging shows percentage complete

**Test Case 3: Large Document (40-50 pages)**
1. Upload 50-page PDF through the application
2. Monitor processing time - should complete in 360-450 seconds
3. Verify no out-of-memory errors
4. Confirm quality metrics meet thresholds

**Test Case 4: Concurrent Processing**
1. Upload 2 documents simultaneously
2. Verify both complete successfully
3. Check memory usage stays reasonable
4. Confirm request queue handles concurrency properly

### Validation Checklist

- [ ] Processing time reduced by at least 60% for 8-page documents
- [ ] OCR quality metrics (confidence, coverage) unchanged from baseline
- [ ] Memory usage does not exceed 1.5GB for typical documents
- [ ] Progress logging shows accurate percentage complete
- [ ] No regression in error handling or quality thresholds
- [ ] Concurrent document processing works correctly
- [ ] All existing tests pass (if any exist)

### Performance Baseline Collection

Before implementing changes:
1. Process 5-page, 10-page, 25-page, and 50-page documents
2. Record processing times, memory usage, and quality metrics
3. Use as comparison baseline after optimization

### Monitoring Points

Log the following metrics for comparison:
- Total processing time
- Time per page
- Memory usage (RSS) at start, middle, and end
- Number of PDF loads from disk (should be 1 after optimization)
- Quality metrics: mean confidence, coverage ratio

## Implementation Order

### Step 1: Create Performance Baseline
**Purpose**: Establish metrics for comparison
- Process test documents (5, 10, 25 pages) with current implementation
- Record processing times and memory usage
- Save logs for comparison
- Document quality metrics as baseline

**Validation**: Have timing and memory baseline data

### Step 2: Optimize PDF Loading in ocr_service.py
**Purpose**: Fix critical disk I/O bottleneck
- Modify `_process_pdf_internal()` to load PDF once
- Remove probe load at scale=1.0
- Change loop to use in-memory array slicing
- Add timing variables for progress logging

**Files**: `backend/app/services/ocr_service.py` (lines ~180-280)

**Validation**: 
- Check logs show "Loading PDF once at scale X.X" message
- Verify no "probe_docs = DocumentFile.from_pdf" in logs
- Test with 8-page document, should see 60% time reduction

### Step 3: Enhance Progress Logging
**Purpose**: Provide visibility into optimization gains
- Add percentage complete to chunk processing logs
- Add estimated time remaining calculation
- Log memory stats at chunk boundaries
- Add total processing time summary

**Files**: `backend/app/services/ocr_service.py` (lines ~220-250)

**Validation**: 
- Logs show "Processing chunk X of Y (Z% complete)"
- Memory stats visible in logs
- Final log shows total time

### Step 4: Update Configuration Defaults for 2GB Instances
**Purpose**: Leverage available memory for better performance
- Increase `OCR_PAGE_CHUNK_SIZE` from 1 to 5
- Increase `OCR_PDF_SCALE` from 1.8 to 2.5
- Increase `OCR_RECO_BATCH_SIZE` from 8 to 32
- Set `OCR_UNLOAD_MODELS_AFTER_USE` to false
- Increase `OCR_MAX_CONCURRENT_REQUESTS` from 1 to 2

**Files**: `backend/app/config.py` (lines ~92-135)

**Validation**:
- Verify config values updated correctly
- Test processing shows chunk size of 5 in logs
- Memory usage remains under 1.5GB

### Step 5: Update Environment Example File
**Purpose**: Document optimized settings for users
- Update `.env.example` with new defaults
- Add comments explaining tuning for different instance sizes
- Document relationship between chunk size and memory

**Files**: `backend/.env.example`

**Validation**: File contains clear documentation of settings

### Step 6: Performance Validation Testing
**Purpose**: Confirm optimization goals achieved
- Process same test documents as baseline
- Compare processing times (target: 60-70% reduction)
- Verify memory usage acceptable
- Confirm quality metrics unchanged
- Test concurrent processing

**Validation**:
- 8-page document: 300s → 60-90s (achieved)
- 25-page document: Processing time acceptable
- 50-page document: No OOM errors
- Quality metrics within 5% of baseline

### Step 7: Update Memory Bank Documentation
**Purpose**: Record optimization work for future reference
- Update `memory-bank/activeContext.md` with changes
- Update `memory-bank/progress.md` with completed work
- Document performance improvements achieved
- Add notes on tuning for different instance sizes

**Validation**: Memory bank reflects current system state

### Dependencies Between Steps
- Step 2 must complete before Step 3 (logging depends on new structure)
- Step 4 should follow Step 2 (validate I/O fix before config changes)
- Step 6 requires Steps 2-5 complete (full validation)
- Step 7 is final documentation step

### Rollback Strategy
If issues arise:
1. Configuration changes (Step 4) can be reverted via environment variables
2. Code changes (Steps 2-3) can be reverted via git
3. Keep baseline metrics to compare against
4. Test with small documents first before large ones

### Success Criteria
- Processing time reduction of 60%+ for typical documents
- No increase in memory usage
- Quality metrics maintained
- No new errors or edge case failures
- Code remains maintainable and well-documented
