-- Supabase Storage Setup for Report Documents
-- This creates a private bucket with RLS policies for user-isolated PDF storage

-- =============================================================================
-- CREATE STORAGE BUCKET
-- =============================================================================

-- Create private bucket for report documents
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'report-documents',
  'report-documents',
  false,  -- Private bucket (requires authentication)
  104857600,  -- 100MB file size limit (100 * 1024 * 1024)
  ARRAY['application/pdf']::text[]  -- Only PDF files allowed
)
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- ROW LEVEL SECURITY POLICIES
-- =============================================================================

-- Enable RLS on storage.objects
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Policy: Users can upload files to their own folder
CREATE POLICY "Users can upload to own folder"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'report-documents' 
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can read files from their own folder
CREATE POLICY "Users can read own files"
ON storage.objects
FOR SELECT
TO authenticated
USING (
  bucket_id = 'report-documents' 
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can update files in their own folder
CREATE POLICY "Users can update own files"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
  bucket_id = 'report-documents' 
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can delete files from their own folder
CREATE POLICY "Users can delete own files"
ON storage.objects
FOR DELETE
TO authenticated
USING (
  bucket_id = 'report-documents' 
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- =============================================================================
-- CORS CONFIGURATION
-- =============================================================================

-- Note: CORS configuration must be set through Supabase Dashboard or API
-- Navigate to: Storage > report-documents > Configuration > CORS
-- Add allowed origins for your frontend domain(s)

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Verify bucket creation
-- SELECT * FROM storage.buckets WHERE id = 'report-documents';

-- Verify policies
-- SELECT * FROM pg_policies WHERE tablename = 'objects' AND schemaname = 'storage';

-- =============================================================================
-- NOTES
-- =============================================================================

-- Path Structure: {user_id}/{report_id}/{content_hash}.pdf
-- Example: 550e8400-e29b-41d4-a716-446655440000/abc123/a1b2c3d4...ef.pdf
--
-- Security Features:
-- 1. Private bucket (requires authentication)
-- 2. RLS policies enforce user isolation at path level
-- 3. Only PDF files allowed (MIME type restriction)
-- 4. 100MB file size limit
-- 5. Signed URLs with expiry for temporary access
--
-- Benefits:
-- 1. 90% cost reduction vs. BYTEA storage
-- 2. Infinite scalability with object storage
-- 3. Natural deduplication via content-hash naming
-- 4. CDN-ready for global distribution
