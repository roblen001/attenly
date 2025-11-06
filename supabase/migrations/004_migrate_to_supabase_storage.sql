-- Migration: Migrate PDF Storage to Supabase Storage
-- Adds storage metadata columns for Supabase Storage integration
-- Note: Since there are no existing users, we implement Storage-only approach

-- =============================================================================
-- ADD STORAGE METADATA COLUMNS
-- =============================================================================

-- Add storage path column (where the PDF is stored in Supabase Storage)
ALTER TABLE saved_report_documents 
ADD COLUMN IF NOT EXISTS storage_path TEXT;

-- Add content hash column (SHA-256 hash for verification and deduplication)
ALTER TABLE saved_report_documents 
ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- Add storage bucket column (defaults to 'report-documents')
ALTER TABLE saved_report_documents 
ADD COLUMN IF NOT EXISTS storage_bucket TEXT DEFAULT 'report-documents';

-- Add timestamp for when file was stored
ALTER TABLE saved_report_documents 
ADD COLUMN IF NOT EXISTS stored_at TIMESTAMPTZ DEFAULT NOW();

-- =============================================================================
-- ADD INDEXES FOR PERFORMANCE
-- =============================================================================

-- Index for storage path lookups
CREATE INDEX IF NOT EXISTS idx_saved_report_documents_storage_path
  ON saved_report_documents(storage_path)
  WHERE storage_path IS NOT NULL;

-- Index for content hash lookups (deduplication)
CREATE INDEX IF NOT EXISTS idx_saved_report_documents_content_hash
  ON saved_report_documents(content_hash)
  WHERE content_hash IS NOT NULL;

-- Composite index for report + document lookups
CREATE INDEX IF NOT EXISTS idx_saved_report_documents_lookup
  ON saved_report_documents(report_id, document_id);

-- =============================================================================
-- ADD COLUMN COMMENTS
-- =============================================================================

COMMENT ON COLUMN saved_report_documents.storage_path IS 
'Path to PDF file in Supabase Storage. Format: {user_id}/{report_id}/{content_hash}.pdf';

COMMENT ON COLUMN saved_report_documents.content_hash IS 
'SHA-256 hash of PDF content for verification and deduplication';

COMMENT ON COLUMN saved_report_documents.storage_bucket IS 
'Supabase Storage bucket name. Defaults to report-documents';

COMMENT ON COLUMN saved_report_documents.stored_at IS 
'Timestamp when PDF was uploaded to Storage';

COMMENT ON COLUMN saved_report_documents.pdf_binary IS 
'Legacy BYTEA storage - no longer populated. Kept for schema flexibility';

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Verify columns added
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'saved_report_documents'
-- ORDER BY ordinal_position;

-- Verify indexes created
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'saved_report_documents'
-- ORDER BY indexname;

-- =============================================================================
-- NOTES
-- =============================================================================

-- Storage-Only Approach:
-- Since there are no existing users, we implement a clean Storage-only approach:
-- 1. New PDFs are uploaded to Supabase Storage only (no BYTEA writes)
-- 2. storage_path contains the Storage path to the PDF
-- 3. content_hash enables deduplication and verification
-- 4. pdf_binary column kept for schema flexibility but not populated
--
-- Path Structure:
-- {user_id}/{report_id}/{content_hash}.pdf
-- Example: 550e8400-e29b-41d4-a716-446655440000/abc123/a1b2c3d4e5f6...789.pdf
--
-- Benefits:
-- 1. 90% cost reduction ($0.25/GB → $0.02/GB)
-- 2. Infinite scalability with object storage
-- 3. Natural deduplication via content-hash naming
-- 4. Faster queries (no large BYTEA columns)
-- 5. CDN-ready for global distribution
