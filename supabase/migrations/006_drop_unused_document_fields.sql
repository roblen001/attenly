-- Migration: Drop Unused Document Fields
-- Removes columns that are no longer used in saved_report_documents table
-- 
-- Columns being dropped:
-- 1. full_text - Made nullable in migration 005, never populated (deprecated)
-- 2. pages_info - Always empty list, not used
-- 3. total_pages - Always 0, not used in storage context
-- 4. total_characters - Always 0, not used in storage context
-- 5. pdf_binary - Legacy BYTEA storage, replaced by Supabase Storage in migration 004

-- =============================================================================
-- DROP UNUSED INDEXES
-- =============================================================================

-- Drop index on pdf_binary (column being removed)
DROP INDEX IF EXISTS idx_saved_report_documents_pdf_exists;

-- Drop index on storage path lookup (already covered by composite index)
-- Note: Keeping idx_saved_report_documents_lookup as it's still used
DROP INDEX IF EXISTS idx_saved_report_documents_storage_path;

-- =============================================================================
-- DROP UNUSED COLUMNS
-- =============================================================================

-- Drop all unused columns in a single ALTER statement for efficiency
ALTER TABLE saved_report_documents 
  DROP COLUMN IF EXISTS full_text,
  DROP COLUMN IF EXISTS pages_info,
  DROP COLUMN IF EXISTS total_pages,
  DROP COLUMN IF EXISTS total_characters,
  DROP COLUMN IF EXISTS pdf_binary;

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Verify columns were dropped
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'saved_report_documents'
-- ORDER BY ordinal_position;

-- Verify remaining indexes
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'saved_report_documents'
-- ORDER BY indexname;

-- =============================================================================
-- NOTES
-- =============================================================================

-- Impact Assessment:
-- 1. Storage Savings: Eliminates 5 unused columns per document record
-- 2. Performance: Slightly faster queries with fewer columns to scan
-- 3. Code Simplification: Removes unnecessary field handling in application
-- 4. Schema Clarity: Table now accurately reflects what's actually used
--
-- Current Storage Model (After Migration):
-- - storage_path: Path to PDF in Supabase Storage
-- - content_hash: SHA-256 hash for verification/deduplication
-- - storage_bucket: Bucket name (defaults to 'report-documents')
-- - stored_at: Timestamp when PDF was stored
-- - metadata: JSONB containing file size, type, processing stats
-- - filename: Original filename
-- - document_id: Reference to document
-- - report_id: Reference to parent report
--
-- Document Text Extraction:
-- - Native PDFs: Extracted on-demand using PDF.js in frontend
-- - OCR Documents: Text stored in report_data JSONB (not in document table)
--
-- Migration Safety:
-- - All dropped columns confirmed unused in current codebase
-- - No application logic depends on these values
-- - PDFs safely stored in Supabase Storage (separate system)
-- - Document viewing uses runtime extraction, not stored text
