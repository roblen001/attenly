# Implementation Plan: Email Job Pipeline Report Generation

## Overview
Complete the email-to-Attenly pipeline by integrating report generation for email-submitted documents. Email jobs currently download attachments and process them through DocumentProcessor, but stop short of generating reports. This implementation adds the missing report generation, saving, and notification steps to match the existing file upload workflow.

## Current State Analysis

### What Works ✅
- Email webhook receives attachments and creates `email_jobs` records
- Cron job (`/internal/process-email-jobs`) triggers processing
- `EmailJobService.process_single_job()` downloads attachments from Supabase Storage
- Documents are processed through `DocumentProcessor` (identical to file uploads)
- Chunks are stored in user's vector store with same metadata
- Notification emails are sent (but without actual report URLs)

### What's Missing ❌
- No report generation via `report_service.generate_report()`
- No report saving to `saved_reports` table
- No `email_jobs.report_id` foreign key population
- Notification email lacks actual report URL
- No agent loading logic for background jobs

## Architecture Decisions

### Multi-Attachment Behavior
**Decision:** All attachments in one email → ONE combined report

This mirrors file upload behavior where multiple files are processed into a single report.

**Implementation:**
- Process all attachments into the same vector store
- Collect all `document_ids` from all attachments
- Pass all document IDs to `report_service.generate_report()`
- Result: One saved report containing data from all documents

### Agent Selection Strategy
**Decision:** Require `default_agent_id` - fail gracefully if not set

If `default_agent_id` is not configured:
1. Mark job as `failed` with user-friendly `error_message`
2. Send `send_job_failed_email()` with configuration instructions
3. Do NOT leave job in "processing" limbo state

### Report URL Pattern
**Format:** `{APP_URL}/report/saved/{report_id}`

Matches existing frontend route: `/report/saved/:reportId` (verified in `App.tsx`)

### Idempotency Guarantee
**Check before processing:**
```python
if job_data.get("report_id") is not None:
    # Already processed - verify terminal state
    if job_data.get("status") == "processing":
        # Fix inconsistent state
        update status to "completed"
    return True  # Skip duplicate processing
```

### Email Failure Handling
**Decision:** Email failure ≠ job failure

If report is generated successfully but notification email fails:
- Job status remains `completed`
- `report_id` is set
- Log email failure as warning (not error)
- Do NOT retry report generation on subsequent attempts

## Implementation Breakdown

### [Types]
Type definitions and data structures

**No new types required** - leveraging existing schemas:
- `Agent` from `schemas.py` - Agent configuration
- `ReportData` dictionary - Report structure from `report_service`
- Database fields already exist in `email_jobs` and `saved_reports` tables

### [Files]
File modifications and new files

#### New Files Created
1. **`backend/app/services/agent_loader.py`**
   - Purpose: Centralized agent loading logic for both web and background contexts
   - Exports: `load_agent_by_id(agent_id: str, user_id: Optional[str] = None) -> Agent`
   - Handles: Both prebuilt agents (JSON) and custom agents (database)
   - Layer: Service/domain layer (no HTTP dependencies)

2. **`backend/app/utils/urls.py`**
   - Purpose: URL construction helpers
   - Exports: `build_report_url(report_id: str) -> str`
   - Uses: `APP_URL` from `config.py`

#### Existing Files Modified
3. **`backend/app/services/email_job_service.py`**
   - Add report generation pipeline to `process_single_job()`
   - Import and use `agent_loader.load_agent_by_id()`
   - Call `report_service.generate_report()` with identical parameters to file upload flow
   - Call `supabase_service.save_report_for_system()` to persist report
   - Update `email_jobs.report_id` after successful save
   - Send notification with proper report URL via `build_report_url()`

4. **`backend/app/services/supabase_service.py`**
   - Add `save_report_for_system()` method (uses service role key)
   - Extract `_save_report_internal()` shared helper from existing `save_report()`
   - Both public methods become thin wrappers around shared logic

5. **`backend/app/routers/agents.py`**
   - Remove `_get_agent_by_id_internal()` function (lines ~1040-1090)
   - Replace with import from `agent_loader.load_agent_by_id()`
   - Update all call sites to use new import

### [Functions]
Function-level changes and signatures

#### New Functions

**`backend/app/services/agent_loader.py`:**
```python
def load_agent_by_id(agent_id: str, user_id: Optional[str] = None) -> Agent:
    """
    Load agent configuration by ID from prebuilt JSON or custom agents table.
    
    Args:
        agent_id: Agent identifier (slug for prebuilt, UUID for custom)
        user_id: Optional user ID for custom agent access verification
        
    Returns:
        Agent object with full configuration
        
    Raises:
        ValueError: If agent not found or user lacks access
    """
```

**`backend/app/utils/urls.py`:**
```python
def build_report_url(report_id: str) -> str:
    """
    Construct frontend URL for viewing a saved report.
    
    Args:
        report_id: Report UUID from saved_reports table
        
    Returns:
        Full URL: {APP_URL}/report/saved/{report_id}
    """
```

**`backend/app/services/supabase_service.py`:**
```python
def save_report_for_system(
    self,
    user_id: str,
    agent_id: str,
    agent_name: str,
    report_name: str,
    report_data: dict,
    document_contents: dict,
    pdf_binaries: Optional[Dict[str, bytes]] = None,
    cached_ai_baseline: Optional[Dict[str, str]] = None
) -> str:
    """
    Save report using service role key for system operations (cron jobs).
    
    Args:
        user_id: User who owns the report
        agent_id: Agent used for extraction
        agent_name: Agent display name
        report_name: Generated report name
        report_data: Complete ReportData structure
        document_contents: Document metadata dict
        pdf_binaries: Optional PDF binaries for storage
        cached_ai_baseline: AI baseline for audit trail
        
    Returns:
        report_id: UUID of created saved_reports row
        
    Notes:
        - Uses service role client (bypasses RLS)
        - Sets correct user_id for report ownership
        - Reuses _save_report_internal() for consistency
    """
```

```python
def _save_report_internal(
    self,
    client: Client,  # User-scoped or service role client
    user_id: str,
    agent_id: str,
    agent_name: str,
    report_name: str,
    report_data: dict,
    document_contents: dict,
    pdf_binaries: Optional[Dict[str, bytes]] = None,
    refresh_token: str = "",
    cached_ai_baseline: Optional[Dict[str, str]] = None
) -> str:
    """
    Shared report saving logic used by both user-session and system saves.
    
    Args:
        client: Supabase client (user-scoped or service role)
        [other params same as save_report_for_system]
        
    Returns:
        report_id: UUID of created saved_reports row
    """
```

#### Modified Functions

**`backend/app/services/email_job_service.py` - `process_single_job()`:**

Current signature unchanged, internal logic expanded:

```python
async def process_single_job(self, job_id: str) -> bool:
    """
    Process a single email job through the complete pipeline.
    
    NEW BEHAVIOR:
    1. Download attachments from Storage (existing)
    2. Process through DocumentProcessor (existing)
    3. Load agent configuration (NEW)
    4. Generate report via report_service (NEW)
    5. Save report to saved_reports (NEW)
    6. Update email_jobs.report_id (NEW)
    7. Send notification with report URL (ENHANCED)
    
    Idempotency: Skips if job.report_id already set
    
    Failure modes:
    - Missing default_agent_id → fail with user guidance
    - Agent not found → fail with error message
    - Report generation failure → fail with error message
    - Supabase write failure → fail with error message
    
    Args:
        job_id: Email job UUID
        
    Returns:
        True if successful or already processed, False on failure
    """
```

**`backend/app/routers/agents.py` - Update call sites:**
```python
# OLD:
agent_dict = _get_agent_by_id_internal(agent_id, user_id, jwt_token)

# NEW:
from app.services.agent_loader import load_agent_by_id
agent = load_agent_by_id(agent_id, user_id)
```

### [Classes]
No new classes, modifications to existing service classes

**`EmailJobService` class** (`email_job_service.py`):
- Expanded `process_single_job()` method with report generation pipeline
- Enhanced logging with structured fields (job_id, user_id, report_id, status)

**`SupabaseService` class** (`supabase_service.py`):
- Added `save_report_for_system()` public method
- Added `_save_report_internal()` private helper
- Refactored existing `save_report()` to use shared helper

### [Dependencies]
No new external dependencies

All required imports are from existing modules:
- `app.services.agent_loader` (new)
- `app.services.report_service` (existing)
- `app.services.supabase_service` (existing)
- `app.services.email_service` (existing)
- `app.utils.urls` (new)
- `app.config` (existing)

### [Testing]
Test strategy and verification steps

#### Automated Tests

**1. Unit Test: Idempotency Behavior**
```python
# test_email_job_service.py
async def test_process_single_job_idempotency():
    """Verify job with report_id set is not reprocessed"""
    # Setup: Job with report_id already set
    # Execute: Call process_single_job()
    # Assert: Returns True without calling report_service
    # Assert: No new saved_reports row created
```

**2. Unit Test: Missing Default Agent**
```python
async def test_process_single_job_missing_agent():
    """Verify graceful failure when default_agent_id not set"""
    # Setup: Job without default_agent_id
    # Execute: Call process_single_job()
    # Assert: Job status = 'failed'
    # Assert: error_message contains user guidance
    # Assert: send_job_failed_email called
```

**3. Unit Test: Agent Not Found**
```python
async def test_process_single_job_invalid_agent():
    """Verify graceful failure when agent doesn't exist"""
    # Setup: Job with invalid default_agent_id
    # Execute: Call process_single_job()
    # Assert: Job status = 'failed'
    # Assert: error_message mentions agent not found
```

**4. Integration Test: Happy Path**
```python
async def test_process_single_job_success():
    """Verify complete pipeline from documents to report"""
    # Setup: Valid job with default_agent_id
    # Execute: Call process_single_job()
    # Assert: saved_reports row exists
    # Assert: email_jobs.report_id populated
    # Assert: send_report_ready_email called with correct URL
```

#### Manual Verification Steps

**Happy Path Test:**
1. Create email job in database with attachments metadata
2. Set `default_agent_id` on user's `email_ingest_endpoints` row
3. Call `/internal/process-email-jobs` endpoint (via curl with cron secret)
4. Verify in database:
   - `saved_reports` has new row with correct `user_id`
   - `email_jobs.report_id` references saved report
   - `email_jobs.status = 'completed'`
5. Check vector store: Verify chunks exist for documents
6. Check email logs: Verify "Report ready" email sent with URL format `{APP_URL}/report/saved/{report_id}`
7. Open URL in browser: Verify report loads correctly

**Configuration Error Test:**
1. Create email job without `default_agent_id` on endpoint
2. Process job via cron endpoint
3. Verify in database:
   - `email_jobs.status = 'failed'`
   - `email_jobs.error_message` contains "No default agent configured"
4. Check email logs: Verify "Job failed" email with configuration instructions

**Idempotency Test:**
1. Process job successfully → `report_id` set
2. Call processing endpoint again for same job
3. Verify: No new `saved_reports` row created
4. Verify: Job remains in `completed` status
5. Check logs: "Skipping - already has report_id"

### [Implementation Order]
Sequential implementation steps

1. **Create URL helper** (`backend/app/utils/urls.py`)
   - Simple, no dependencies
   - Can be tested immediately

2. **Create agent loader** (`backend/app/services/agent_loader.py`)
   - Extract logic from `agents.py`
   - Add unit tests for prebuilt and custom agent loading
   - Verify no circular imports

3. **Refactor `agents.py`**
   - Replace `_get_agent_by_id_internal()` with `agent_loader` import
   - Update all call sites
   - Run existing tests to ensure no regression

4. **Extend `supabase_service.py`**
   - Extract `_save_report_internal()` from existing `save_report()`
   - Refactor `save_report()` to use shared helper
   - Add `save_report_for_system()` method
   - Test both save methods ensure equivalent behavior

5. **Enhance `email_job_service.py`**
   - Add idempotency check at start of `process_single_job()`
   - Add agent loading with error handling
   - Integrate `report_service.generate_report()` call
   - Add report saving via `save_report_for_system()`
   - Update `email_jobs.report_id` in database
   - Enhance notification email with report URL
   - Add comprehensive logging throughout

6. **Write automated tests**
   - Idempotency test
   - Missing agent test
   - Invalid agent test
   - Happy path integration test (if feasible)

7. **Manual verification**
   - Run through all three verification scenarios
   - Document results in implementation summary

## Detailed Implementation Guidance

### Agent Loading Logic

**Consolidated behavior** (in `agent_loader.py`):

```python
def load_agent_by_id(agent_id: str, user_id: Optional[str] = None) -> Agent:
    # 1. Try prebuilt agents from JSON
    prebuilt_path = Path(__file__).parent.parent / "seeds" / "prebuilt_agents.json"
    if prebuilt_path.exists():
        agents = json.loads(prebuilt_path.read_text())
        for agent_data in agents:
            if agent_data["slug"] == agent_id:
                return Agent(**transform_to_schema(agent_data))
    
    # 2. Try custom agents from database (requires user_id)
    if user_id:
        # Use service role client for background job access
        from app.services.supabase_service import supabase_service
        agent_data = supabase_service.get_agent_by_id_system(agent_id, user_id)
        if agent_data:
            return Agent(**transform_to_schema(agent_data))
    
    # 3. Not found
    raise ValueError(f"Agent '{agent_id}' not found")
```

### Report Name Generation

For email-submitted reports, generate name from email metadata:

```python
def generate_report_name(job_data: dict) -> str:
    """Generate report name from email metadata"""
    subject = job_data.get("subject", "").strip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if subject:
        # Use email subject (truncate if too long)
        clean_subject = subject[:50]
        return f"Email Report: {clean_subject} - {timestamp}"
    else:
        return f"Email Report - {timestamp}"
```

### Structured Logging Pattern

**LOG FIELDS:** Always include: `job_id`, `user_id`, `status`, `report_id` (when available)

```python
logger.info(
    f"Starting email job processing",
    extra={"job_id": job_id, "user_id": user_id, "attachment_count": len(attachments)}
)

logger.info(
    f"Generated report successfully",
    extra={"job_id": job_id, "user_id": user_id, "report_id": report_id, "agent_id": agent_id}
)

logger.error(
    f"Job processing failed",
    extra={"job_id": job_id, "user_id": user_id, "status": "failed", "error": error_message}
)
```

### Error Handling Matrix

| Error Scenario | Job Status | Error Message | Email Notification |
|---|---|---|---|
| `default_agent_id` not set | `failed` | "No default agent configured. Please configure a default agent in Settings → Email Ingest." | `send_job_failed_email()` |
| Agent not found | `failed` | "Configured agent '{agent_id}' not found or deleted." | `send_job_failed_email()` |
| Report generation failed | `failed` | "Report generation failed: {error_details}" | `send_job_failed_email()` |
| Supabase write failed | `failed` | "Database error while saving report: {error_summary}" | `send_job_failed_email()` |
| Email send failed | `completed` | (None - log warning only) | (None - report still accessible) |

### Failure Recovery Strategy

**All failures follow this pattern:**

```python
try:
    # Processing logic
    pass
except Exception as e:
    logger.error(f"Job {job_id} failed: {e}", extra={"job_id": job_id, "error": str(e)})
    
    # Mark job as failed
    db_client.table("email_jobs").update({
        "status": "failed",
        "error_message": user_friendly_error_message,
        "completed_at": datetime.utcnow().isoformat()
    }).eq("id", job_id).execute()
    
    # Send notification (except for email send failures)
    if not isinstance(e, EmailSendError):
        await email_service.send_job_failed_email(
            to=job_data["from_email"],
            job_id=job_id,
            error=user_friendly_error_message
        )
    
    return False
```

## Success Criteria

### Functional Requirements ✅
- [ ] Email jobs with attachments generate reports via `report_service`
- [ ] Reports are saved to `saved_reports` table with correct `user_id`
- [ ] `email_jobs.report_id` foreign key is populated
- [ ] Notification emails contain actual report URLs (not placeholder)
- [ ] Report URLs follow pattern: `{APP_URL}/report/saved/{report_id}`
- [ ] Idempotency: Reprocessing doesn't create duplicate reports
- [ ] Missing agent: Job marked failed with helpful error message

### Non-Functional Requirements ✅
- [ ] No code duplication between web and email flows
- [ ] Clean service layer separation (no HTTP in agent_loader)
- [ ] Comprehensive structured logging with machine-parsable fields
- [ ] Graceful failure handling for all error scenarios
- [ ] Automated tests verify key behaviors (idempotency, missing agent)

## Implementation Notes

### Async Consistency
Ensure async/await is used consistently:
- `report_service.generate_report()` is async
- `process_single_job()` is async
- All database operations should await if using async client

### Transaction Safety
While full ACID transactions aren't implemented:
1. Generate report first (no side effects)
2. Save to saved_reports (get report_id)
3. Update email_jobs.report_id (references saved report)

On failure at step 3, worst case: Orphaned report exists but job can be retried with idempotency check.

### Backwards Compatibility
No breaking changes:
- Existing `save_report()` signature unchanged
- Existing agent loading call sites unchanged (just import path changes)
- Database schema unchanged (tables already exist)

## Verification Checklist

Before marking complete:
- [ ] All automated tests pass
- [ ] Manual happy path test successful
- [ ] Manual configuration error test successful
- [ ] Manual idempotency test successful
- [ ] No regression in existing file upload flow
- [ ] Code review completed
- [ ] Structured logging verified in test environment
- [ ] Documentation updated in implementation summary

---

## Implementation Summary Template

```markdown
# Implementation Summary: Email Job Report Generation

## Changes Made

### Files Created
- `backend/app/services/agent_loader.py` - Centralized agent loading
- `backend/app/utils/urls.py` - URL construction helpers

### Files Modified
- `backend/app/services/email_job_service.py` - Added report generation pipeline
- `backend/app/services/supabase_service.py` - Added system-level save method
- `backend/app/routers/agents.py` - Refactored to use agent_loader

## Key Behaviors Implemented

1. **Report Generation**: Email jobs now generate reports identical to file upload flow
2. **Agent Loading**: Consolidated logic handles both prebuilt and custom agents
3. **Idempotency**: Jobs with report_id set are not reprocessed
4. **Error Handling**: Missing/invalid agents fail gracefully with user guidance
5. **Notification**: Emails include actual report URLs: `{APP_URL}/report/saved/{report_id}`

## Testing Performed

### Automated Tests
- ✅ Idempotency test passes
- ✅ Missing agent test passes
- ✅ Invalid agent test passes

### Manual Verification
- ✅ Happy path: Report generated and accessible
- ✅ Config error: Job failed with helpful message
- ✅ Idempotency: Retry doesn't duplicate report

## No Regressions
- ✅ Existing file upload flow unchanged
- ✅ All existing tests pass
