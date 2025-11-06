-- Migration: Add PDF binary storage for saved reports
-- This enables native PDF viewing with highlighting for saved reports
-- OCR documents won't have PDFs (NULL values allowed)

-- Add column for storing PDF binary data
ALTER TABLE saved_report_documents 
ADD COLUMN pdf_binary BYTEA;

-- Add comment for documentation
COMMENT ON COLUMN saved_report_documents.pdf_binary IS 
'Original PDF binary data for native PDF viewing. NULL for OCR documents or reports saved before this migration.';

-- Add index for faster queries when checking PDF availability
CREATE INDEX IF NOT EXISTS idx_saved_report_documents_pdf_exists
  ON saved_report_documents(report_id, document_id) 
  WHERE pdf_binary IS NOT NULL;

-- Add index for document lookups (optimize retrieval)
CREATE INDEX IF NOT EXISTS idx_saved_report_documents_lookup
  ON saved_report_documents(report_id, document_id);
