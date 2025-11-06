-- Migration: Make full_text optional
-- The DocumentViewer component extracts text from native PDFs using PDF.js,
-- so storing full_text in the database is redundant and wastes space.

-- =============================================================================
-- MAKE FULL_TEXT OPTIONAL
-- =============================================================================

-- Make full_text column nullable
ALTER TABLE saved_report_documents 
ALTER COLUMN full_text DROP NOT NULL;

-- Update column comment to indicate it's deprecated
COMMENT ON COLUMN saved_report_documents.full_text IS 
'DEPRECATED: No longer populated. DocumentViewer extracts text directly from native PDFs using PDF.js. This column is kept nullable for backward compatibility but will always be NULL for new reports.';

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Verify column is now nullable
-- SELECT column_name, is_nullable, data_type
-- FROM information_schema.columns
-- WHERE table_name = 'saved_report_documents' AND column_name = 'full_text';

-- =============================================================================
-- NOTES
-- =============================================================================

-- Rationale:
-- 1. DocumentViewer uses PDF.js to extract text on-the-fly from native PDFs
-- 2. Storing full_text duplicates data and wastes database space
-- 3. Making it nullable allows us to stop populating it without breaking existing queries
-- 4. Legacy reports with full_text will continue to work (though the value is ignored)
-- 5. New reports will have NULL full_text, saving significant storage space
--
-- Migration Strategy:
-- - Phase 1: Make column nullable (this migration)
-- - Phase 2: Stop populating full_text in application code
-- - Phase 3: (Future) Optionally drop the column after confirming no dependencies
