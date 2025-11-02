# Supabase Storage Migration - Deployment Guide

## Overview

This guide covers the deployment of PDF storage migration from PostgreSQL BYTEA to Supabase Storage, achieving **90% cost reduction** on document storage.

## Migration Architecture

### Before (BYTEA Storage)
- PDFs stored as base64-encoded BYTEA in `saved_report_documents.pdf_binary`
- ~10MB PDF = ~13-14MB in database
- Cost: ~$0.25/GB/month

### After (Supabase Storage)
- PDFs stored in Supabase Storage private bucket
- Only metadata in PostgreSQL
- Cost: ~$0.02/GB/month
- **90% cost savings**

### Key Features
✅ Content-addressed storage (SHA-256 deduplication)
✅ Signed URLs with 1-hour expiry for security
✅ User-isolated RLS policies
✅ No backward compatibility concerns (no existing users)
✅ Clean Storage-only implementation

## Deployment Steps

### 1. Database Migration

Run the database migration to add Storage columns:

```bash
# Connect to your Supabase project and run:
supabase/migrations/004_migrate_to_supabase_storage.sql
```

This adds:
- `storage_path` - Path to PDF in Storage
- `content_hash` - SHA-256 hash for verification
- `storage_bucket` - Bucket name (default: 'report-documents')
- `stored_at` - Upload timestamp

### 2. Create Storage Bucket

Run the Storage setup script in your Supabase SQL editor:

```bash
supabase/storage_setup.sql
```

This creates:
- Private `report-documents` bucket
- RLS policies for user isolation
- 100MB file size limit
- PDF-only file type restriction

**Verify bucket creation:**
```sql
SELECT * FROM storage.buckets WHERE id = 'report-documents';
```

### 3. Configure Environment Variables

Update your `.env` file with Storage configuration:

```bash
# Supabase Storage Configuration
STORAGE_BUCKET_NAME=report-documents
STORAGE_SIGNED_URL_EXPIRY_SECONDS=3600  # 1 hour
STORAGE_MAX_FILE_SIZE_MB=100
```

**Required environment variables:**
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_KEY` - Service role key (for admin operations)
- `SUPABASE_ANON_KEY` - Anon key (for user operations)

### 4. Deploy Backend Changes

The following files have been modified/created:

**New Files:**
- `backend/app/services/supabase_storage_service.py` - Storage operations
- `supabase/migrations/004_migrate_to_supabase_storage.sql` - DB schema
- `supabase/storage_setup.sql` - Bucket & RLS configuration

**Modified Files:**
- `backend/app/config.py` - Storage configuration
- `backend/app/services/supabase_service.py` - Storage upload/download
- `backend/app/routers/agents.py` - Signed URL redirects
- `backend/.env.example` - Documentation

Deploy these changes to your backend service.

### 5. Deploy Frontend Changes

**Modified Files:**
- `frontend/src/types/index.ts` - Added storage metadata types

Deploy frontend changes (no code changes needed in DocumentViewer - it handles 307 redirects automatically).

### 6. Verify Deployment

**Test Upload Flow:**
1. Upload a PDF document
2. Generate a report
3. Save the report
4. Verify in Supabase Storage dashboard that PDF appears in bucket

**Test Download Flow:**
1. Open a saved report
2. Click a quote to view document
3. Verify PDF loads correctly
4. Check browser network tab for 307 redirect to signed URL

**Verify Database:**
```sql
SELECT document_id, storage_path, content_hash, stored_at 
FROM saved_report_documents 
WHERE storage_path IS NOT NULL
LIMIT 5;
```

## Security Verification

### RLS Policy Testing

Test that users can only access their own documents:

```sql
-- This should work (user's own document)
SELECT * FROM storage.objects 
WHERE bucket_id = 'report-documents' 
AND name LIKE 'user-id-here/%';

-- This should return empty (another user's document)
SELECT * FROM storage.objects 
WHERE bucket_id = 'report-documents' 
AND name LIKE 'other-user-id/%';
```

### Signed URL Security

Signed URLs should:
- ✅ Expire after 1 hour (configurable)
- ✅ Only work for documents owned by the user
- ✅ Return 403 for unauthorized access
- ✅ Require regeneration after expiry

## Monitoring

### Storage Usage

Monitor Storage usage in Supabase dashboard:
```
Settings > Storage > report-documents > Usage
```

### Cost Tracking

Expected costs (assuming 10MB average PDF):
- **1000 saved reports** = ~10GB = ~$0.20/month (vs. $2.50 with BYTEA)
- **10000 saved reports** = ~100GB = ~$2.00/month (vs. $25.00 with BYTEA)

### Performance Metrics

Monitor these key metrics:
- Storage upload time (target: <2 seconds for 10MB PDF)
- Signed URL generation (target: <100ms)
- PDF load time (target: <3 seconds)

## Troubleshooting

### Issue: "Storage upload failed"

**Possible causes:**
1. Service role key not configured
2. Storage bucket doesn't exist
3. RLS policies blocking upload

**Solution:**
```python
# Check logs for detailed error
# Verify SUPABASE_KEY is set correctly
# Verify bucket exists in Supabase dashboard
```

### Issue: "PDF not available"

**Possible causes:**
1. Document has no storage_path (OCR document)
2. Storage path invalid
3. Signed URL expired

**Solution:**
- Check if document was uploaded as OCR (no original PDF)
- Verify storage_path in database
- Regenerate signed URL

### Issue: "403 Forbidden" when accessing PDF

**Possible causes:**
1. RLS policies blocking access
2. User doesn't own document
3. Signed URL expired

**Solution:**
```sql
-- Verify RLS policies are active
SELECT * FROM pg_policies 
WHERE tablename = 'objects' 
AND schemaname = 'storage';

-- Check document ownership
SELECT storage_path FROM saved_report_documents 
WHERE document_id = 'xxx' AND report_id = 'yyy';
```

## Rollback Plan

If critical issues arise, the system gracefully handles missing Storage paths:

1. Documents without `storage_path` will show as "PDF not available"
2. OCR documents continue to work (text-based viewer)
3. No data loss (document text content always available)

**Emergency rollback:**
Since there are no existing users, simply fix the issue and redeploy. No data migration needed.

## Performance Expectations

### Storage Upload
- 10MB PDF: ~1-2 seconds
- 50MB PDF: ~5-8 seconds
- Includes SHA-256 hash calculation

### Storage Download
- First request: 307 redirect (~100ms) + download from Storage
- Subsequent requests: Browser cache (if within 1 hour)
- PDF.js handles Range requests automatically

### Deduplication
- Identical PDFs share single Storage object
- Detected via SHA-256 content hash
- Automatic on upload

## Cost Savings Calculator

```python
# Example calculation (1000 saved reports, 10MB average each)

# BYTEA Storage (old)
size_gb = (1000 * 10 * 1.33) / 1024  # 13GB (base64 overhead)
cost_bytea = size_gb * 0.25  # $3.25/month

# Supabase Storage (new)
size_gb_storage = (1000 * 10) / 1024  # 10GB (no overhead)
cost_storage = size_gb_storage * 0.02  # $0.20/month

# Savings
savings = cost_bytea - cost_storage  # $3.05/month
savings_pct = (savings / cost_bytea) * 100  # 93.8% reduction
```

## Success Criteria

The migration is successful when:

✅ New reports save PDFs to Storage
✅ `storage_path` populated in database
✅ PDFs load correctly in DocumentViewer
✅ Signed URLs work with proper expiry
✅ RLS policies enforce user isolation
✅ Cost reduction verified in billing
✅ No user-reported issues

## Support

For issues or questions:
1. Check this guide's Troubleshooting section
2. Review backend logs for detailed errors
3. Verify Storage bucket configuration in Supabase dashboard
4. Test RLS policies with SQL queries above

---

**Implementation completed:** November 1, 2025
**Storage-only approach:** Clean implementation, no backward compatibility complexity
**Cost savings:** 90% reduction in document storage costs
