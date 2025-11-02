# Implementation Plan: Fix Supabase Storage RLS Authentication Error

## [Overview]

Fix the "new row violates row-level security policy" error occurring when uploading PDFs to Supabase Storage by correcting how JWT tokens are passed to the storage3 client for proper RLS authentication.

The issue occurs because `auth.set_session()` properly authenticates PostgREST (database) operations but does not propagate authentication headers to the storage3 API client. The storage3 library requires explicit JWT token headers to enforce Row Level Security policies that check `auth.uid()` matches the storage path's user_id folder.

## [Types]

No new types are required for this fix.

The existing type system already supports the necessary parameters:
- `access_token: str` - User's JWT access token
- `refresh_token: str` - User's refresh token
- `user_id: str` - User identifier for path validation

## [Files]

Modify one existing file to fix the storage authentication issue.

### File to Modify:
- **`backend/app/services/supabase_storage_service.py`**
  - **Line 55-77**: Modify `_create_user_client()` method
  - Add explicit authentication headers to storage client after `set_session()`
  - The storage3 client needs the JWT token in its headers to make authenticated API calls

## [Functions]

Modify one function to add storage client authentication.

### Function to Modify:
- **`_create_user_client(self, access_token: str, refresh_token: str) -> Client`**
  - **Location**: `backend/app/services/supabase_storage_service.py` (lines 40-90)
  - **Current behavior**: Creates client without authentication headers, then calls `set_session()` which only authenticates PostgREST
  - **Required change**: Pass Authorization header through `ClientOptions` when creating the client
  - **Implementation**: 
    ```python
    from supabase.lib.client_options import ClientOptions
    options = ClientOptions(
        headers={"Authorization": f"Bearer {access_token}"}
    )
    client = create_client(url, key, options)
    client.auth.set_session(access_token, refresh_token)
    ```
  - **Reason**: storage3 library requires JWT in Authorization header for RLS enforcement, and headers must be passed at client creation time through ClientOptions

## [Classes]

No class modifications required.

The `SupabaseStorageService` class structure remains unchanged - only the internal implementation of `_create_user_client()` needs adjustment.

## [Dependencies]

No new dependencies required.

Existing dependencies already support the fix:
- **storage3==0.12.1**: Already installed, supports header-based authentication
- **supabase**: Already installed, provides the client infrastructure

## [Testing]

Test the fix to ensure RLS policies work correctly.

### Test Strategy:
1. **Unit Test**: Verify `_create_user_client()` properly sets storage authentication headers
2. **Integration Test**: Confirm `upload_document()` successfully uploads PDFs without RLS errors
3. **Manual Test**: Use the save report feature in the UI to verify end-to-end functionality
4. **RLS Validation**: Verify that users can only access their own storage paths

### Test Scenarios:
- Upload PDF to Supabase Storage (should succeed with status 200/201)
- Verify storage path follows pattern: `{user_id}/{report_id}/{content_hash}.pdf`
- Confirm RLS policies allow access only to authenticated user's paths
- Test with multiple users to ensure path isolation

## [Implementation Order]

Implement the fix in a single focused step.

### Step 1: Update Storage Client Authentication
1. Locate `_create_user_client()` method in `supabase_storage_service.py`
2. After the `client.auth.set_session()` call, add storage client authentication
3. Set the Authorization header on the storage client's session
4. Verify the token is properly formatted with "Bearer " prefix
5. Keep existing error handling and logging

### Step 2: Test the Fix
1. Start the backend server
2. Trigger a report save operation from the UI
3. Monitor logs for successful PDF upload to Storage
4. Verify no RLS policy violation errors occur
5. Check Supabase Storage dashboard to confirm file appears in correct path

### Step 3: Validation
1. Confirm logs show: "✓ Session verification: user={user_id}"
2. Confirm logs show: "📤 Upload response type:" without errors
3. Verify file appears at path: `{user_id}/{report_id}/{hash}.pdf`
4. Test downloading the saved report to ensure retrieval works

## [Implementation Notes]

### Critical Context:
- The RLS policies in `supabase/storage_setup.sql` check: `(storage.foldername(name))[1] = auth.uid()::text`
- This means the storage API must have an authenticated session where `auth.uid()` returns the user's ID
- The `set_session()` method authenticates the auth module but storage3 needs the JWT in HTTP headers

### Storage3 Library Specifics:
- Storage3 is a separate client library for Supabase Storage
- It makes HTTP requests to the Storage API endpoints
- RLS enforcement happens at the API level, not the client level
- The API checks the JWT token in the Authorization header to determine `auth.uid()`

### Debugging Information:
- The code already has extensive logging showing token presence and session verification
- If the fix works, we should see successful uploads without "violates row-level security policy" errors
- The upload response should include the file path and metadata

### Why set_session() Alone Doesn't Work:
- `set_session()` is designed for supabase-py's auth and postgrest clients
- The storage client (`client.storage`) is a separate storage3 instance
- storage3 needs explicit authentication configuration via headers or token parameters
- The supabase-py client doesn't automatically propagate auth state to storage3
