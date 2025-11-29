# Implementation Plan: Email to Attenly Feature

## Overview

Implement an end-to-end "Email to Attenly" feature where users can forward email threads with attachments to a private email alias, which triggers automated document processing and report generation.

**Target Stack:**
- Backend: FastAPI (Koyeb)
- Frontend: React (Cloudflare Pages)
- Database: Supabase PostgreSQL
- Email: Resend with webhook support
- Storage: Supabase Storage for attachments

---

## [Types]

Define data structures for email ingest, sender verification, and job processing.

### Database Schema Types

```sql
-- Email ingest endpoint (user's private alias)
CREATE TABLE email_ingest_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    local_part VARCHAR(255) NOT NULL,  -- e.g., "u_9b7c3ebdff4e4"
    domain VARCHAR(255) NOT NULL,       -- e.g., "in.attently.ca"
    full_address VARCHAR(512) NOT NULL, -- cached: local_part@domain
    is_active BOOLEAN NOT NULL DEFAULT true,
    default_agent_id TEXT,              -- null = use global default
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT unique_user_endpoint UNIQUE (user_id),
    CONSTRAINT unique_alias UNIQUE (local_part, domain)
);

-- Verified sender addresses
CREATE TABLE verified_senders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'verified', 'disabled')),
    verification_token VARCHAR(255),
    token_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT unique_user_email UNIQUE (user_id, email)
);

-- Email processing jobs
CREATE TABLE email_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    ingest_endpoint_id UUID NOT NULL REFERENCES email_ingest_endpoints(id) ON DELETE CASCADE,
    from_email VARCHAR(255) NOT NULL,
    subject TEXT,
    instruction_text TEXT,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'discarded')),
    report_id UUID,  -- FK to saved_reports, null until completed
    provider_message_id VARCHAR(512) UNIQUE NOT NULL,  -- for idempotency
    raw_metadata JSONB,  -- provider webhook payload
    error_message TEXT,
    attachment_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
```

### Python Data Models

```python
# Pydantic schemas for API validation
class EmailIngestSettings(BaseModel):
    enabled: bool
    email_alias: Optional[str]
    default_agent_id: Optional[str]
    verified_senders_count: int

class VerifiedSender(BaseModel):
    id: str
    email: str
    status: str  # pending, verified, disabled
    created_at: datetime
    verified_at: Optional[datetime]

class EmailJob(BaseModel):
    id: str
    from_email: str
    subject: Optional[str]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    report_id: Optional[str]
```

---

## [Files]

Detailed breakdown of new and modified files.

### New Files

#### Backend Service Layer
- **`backend/app/services/email_service.py`**
  - Purpose: Resend SDK adapter for sending emails and webhook verification
  - Key functions:
    - `send_verification_email(to: str, token: str, user_alias: str) -> bool`
    - `send_report_ready_email(to: str, report_url: str, report_name: str) -> bool`
    - `verify_webhook_signature(payload: bytes, signature: str) -> bool`

- **`backend/app/services/email_ingest_service.py`**
  - Purpose: Business logic for email ingest endpoints and verified senders
  - Key functions:
    - `enable_email_ingest(user_id: str) -> EmailIngestEndpoint`
    - `disable_email_ingest(user_id: str) -> bool`
    - `add_verified_sender(user_id: str, email: str) -> VerifiedSender`
    - `verify_sender(token: str) -> bool`
    - `get_user_settings(user_id: str) -> EmailIngestSettings`

- **`backend/app/services/email_job_service.py`**
  - Purpose: Job processing orchestration (reusable by cron endpoint)
  - Key functions:
    - `process_pending_jobs(max_jobs: int = 10) -> ProcessingResults`
    - `process_single_job(job_id: str) -> JobResult`
    - `check_rate_limit(user_id: str) -> bool`

#### Backend Routers
- **`backend/app/routers/email_ingest.py`**
  - Purpose: User-facing email ingest settings API (JWT protected)
  - Endpoints:
    - `GET /email-ingest/settings` - Get current settings
    - `POST /email-ingest/enable` - Enable and generate alias
    - `POST /email-ingest/disable` - Disable email ingest
    - `GET /email-ingest/verified-senders` - List verified senders
    - `POST /email-ingest/verified-senders` - Add sender (triggers verification email)
    - `POST /email-ingest/verified-senders/{id}/resend` - Resend verification
    - `DELETE /email-ingest/verified-senders/{id}` - Remove sender
    - `PUT /email-ingest/default-agent` - Set default agent

- **`backend/app/routers/webhooks.py`**
  - Purpose: Public webhook handlers for email provider
  - Endpoints:
    - `POST /webhooks/email-inbound` - Resend inbound email webhook
  - Security: Signature verification, no JWT required

- **`backend/app/routers/internal.py`**
  - Purpose: Internal cron-triggered endpoints (secret auth)
  - Endpoints:
    - `POST /internal/process-email-jobs` - Process pending jobs

#### Frontend Components
- **`frontend/src/pages/EmailIngestSettings.tsx`**
  - Purpose: Main settings page for email ingest feature
  - Features: Enable/disable, display alias, manage senders, set default agent

- **`frontend/src/components/email-ingest/VerifiedSendersList.tsx`**
  - Purpose: Table showing verified senders with actions
  - Actions: Resend verification, remove sender

- **`frontend/src/components/email-ingest/AddSenderModal.tsx`**
  - Purpose: Modal dialog to add new verified sender
  - Fields: Email address input, validation

- **`frontend/src/components/email-ingest/UsageInstructions.tsx`**
  - Purpose: Static component with step-by-step usage guide

#### Database Migration
- **`supabase/migrations/008_email_ingest.sql`**
  - Purpose: Create email ingest tables with RLS policies and indexes
  - Content: Table definitions, RLS policies, indexes, verification queries

#### Configuration
- **`backend/app/config.py`** (modified)
  - Add email-specific configuration variables
  - Resend API key, webhook secret, domain settings, rate limits

### Modified Files

#### Backend Configuration
- **`backend/app/main.py`**
  - Include new routers: `email_ingest`, `webhooks`, `internal`
  - Update CORS to allow email settings page

- **`backend/requirements.txt`**
  - Add `resend>=0.7.0` dependency

- **`backend/.env.example`**
  - Add new environment variables with documentation

#### Backend Schemas
- **`backend/app/schemas.py`**
  - Add Pydantic models for email ingest, verified senders, email jobs

#### Frontend Routing
- **`frontend/src/App.tsx`**
  - Add route for `/settings/email-ingest` (protected)

- **`frontend/src/pages/Dashboard.tsx`**
  - Add navigation link to email settings (optional - can be in settings dropdown)

#### Frontend Types
- **`frontend/src/types/index.ts`**
  - Add TypeScript interfaces for email ingest types

---

## [Functions]

Detailed function specifications for core business logic.

### Email Service

**File:** `backend/app/services/email_service.py`

```python
class EmailService:
    def __init__(self):
        """Initialize Resend SDK with API key from config"""
        
    def send_verification_email(
        self, 
        to: str, 
        token: str, 
        user_alias: str
    ) -> bool:
        """
        Send verification email to new sender address.
        
        Template: Plain text with verification link
        Subject: "Verify your email for Attenly"
        Link: https://api.attenly.ca/verify-sender?token={token}
        
        Returns: True if sent successfully
        """
        
    def send_report_ready_email(
        self,
        to: str,
        report_url: str,
        report_name: str,
        subject_text: str
    ) -> bool:
        """
        Send notification email when report is ready.
        
        Template: Plain text with report link
        Subject: "Your Attenly report is ready: {subject_text}"
        Link: Direct to report view page
        
        Returns: True if sent successfully
        """
        
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify Resend webhook signature.
        
        Uses HMAC-SHA256 with RESEND_WEBHOOK_SECRET
        Returns: True if signature is valid
        """
```

### Email Ingest Service

**File:** `backend/app/services/email_ingest_service.py`

```python
class EmailIngestService:
    def enable_email_ingest(self, user_jwt: str, user_id: str) -> Dict:
        """
        Enable email ingest for user and generate unique alias.
        
        Steps:
        1. Check if user already has endpoint
        2. Generate unique local_part (e.g., u_{uuid})
        3. Create email_ingest_endpoints record
        4. Return full alias and settings
        
        Raises: ValueError if alias generation fails
        """
        
    def disable_email_ingest(self, user_jwt: str, user_id: str) -> bool:
        """
        Disable email ingest by setting is_active=false.
        
        Note: Doesn't delete endpoint to preserve alias history
        Returns: True if successful
        """
        
    def add_verified_sender(
        self,
        user_jwt: str,
        user_id: str,
        email: str
    ) -> Dict:
        """
        Add new sender and send verification email.
        
        Steps:
        1. Validate email format
        2. Check for duplicates (case-insensitive)
        3. Generate verification token (UUID)
        4. Set expiry (24 hours)
        5. Create verified_senders record (status=pending)
        6. Send verification email via email_service
        
        Returns: Sender record with id and status
        """
        
    def verify_sender(self, token: str) -> Tuple[bool, str]:
        """
        Verify sender using token from email link.
        
        Steps:
        1. Look up token (case-sensitive)
        2. Check expiry
        3. Check if already used (status != pending)
        4. Update status=verified, clear token
        5. Set verified_at timestamp
        
        Returns: (success: bool, message: str)
        """
        
    def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if user is within rate limits for job creation.
        
        Logic:
        - Count jobs created in last 24 hours for user
        - Limit: 20 jobs per 24 hours (configurable)
        
        Returns: (allowed: bool, error_message: Optional[str])
        """
```

### Email Job Service

**File:** `backend/app/services/email_job_service.py`

```python
class EmailJobService:
    def process_pending_jobs(self, max_jobs: int = 10) -> Dict:
        """
        Process up to max_jobs pending email jobs.
        
        Steps:
        1. Query email_jobs with status=pending, ordered by created_at
        2. Limit to max_jobs
        3. For each job, call process_single_job
        4. Collect results and return summary
        
        Returns: {processed: int, completed: int, failed: int}
        """
        
    def process_single_job(self, job_id: str) -> Dict:
        """
        Process a single email job end-to-end.
        
        Steps:
        1. Mark job as processing
        2. Get user's default agent (or fallback)
        3. Download attachments from storage
        4. Validate attachment types and sizes
        5. Process through document pipeline (reuse DocumentProcessor)
        6. Generate report using report_service
        7. Save report to saved_reports
        8. Link report_id to job
        9. Send notification email
        10. Mark as completed or failed
        
        Returns: {success: bool, report_id: Optional[str], error: Optional[str]}
        """
        
    def extract_instructions(self, email_body: str) -> str:
        """
        Extract instruction text from forwarded email.
        
        Logic:
        - Look for common forward markers:
          - "---------- Forwarded message ---------"
          - "On [date] ... wrote:"
          - "> " (quote markers)
        - Content before first marker = instructions
        - Strip whitespace, return cleaned text
        
        Returns: Instruction text (may be empty)
        """
```

### Webhook Handler

**File:** `backend/app/routers/webhooks.py`

```python
@router.post("/email-inbound")
async def handle_inbound_email(
    request: Request,
    x_resend_signature: str = Header(...)
) -> JSONResponse:
    """
    Handle Resend inbound email webhook with idempotency.
    
    Steps:
    1. Read raw request body
    2. Verify signature using email_service
    3. Parse JSON payload
    4. Extract provider_message_id
    5. Check for duplicate (query email_jobs by provider_message_id)
    6. If duplicate, return 200 immediately
    7. Extract recipient (to field) and validate alias
    8. Extract sender (from field) and validate verification
    9. Apply rate limiting check
    10. Extract instructions from body
    11. Download and validate attachments
    12. Upload attachments to Supabase Storage
    13. Create email_jobs record
    14. Return 200
    
    Error handling:
    - Invalid signature: return 401
    - Unknown alias: log, return 200 (don't create job)
    - Unverified sender: log, return 200 (don't create job)
    - Rate limit: create job with status=discarded
    - Oversized attachments: create job with status=discarded
    
    Returns: 200 in all cases to prevent provider retries
    """
```

---

## [Classes]

Major class structures and their responsibilities.

### EmailService
**File:** `backend/app/services/email_service.py`

**Purpose:** Wrapper around Resend SDK with adapter pattern for easy provider swapping

**Attributes:**
- `resend_api_key: str` - API key from config
- `webhook_secret: str` - Webhook signing secret
- `from_address: str` - Default from address

**Methods:** See Functions section above

### EmailIngestService
**File:** `backend/app/services/email_ingest_service.py`

**Purpose:** Business logic for managing email ingest configuration

**Dependencies:**
- `supabase_service` - For database operations with RLS
- `email_service` - For sending verification emails

**Methods:** See Functions section above

### EmailJobService
**File:** `backend/app/services/email_job_service.py`

**Purpose:** Orchestrate email job processing end-to-end

**Dependencies:**
- `document_processor` - Reuse existing document processing pipeline
- `report_service` - Reuse existing report generation
- `supabase_service` - For database and storage operations
- `email_service` - For sending notification emails

**Methods:** See Functions section above

---

## [Dependencies]

New external dependencies and version requirements.

### Python Packages (backend/requirements.txt)
```
resend>=0.7.0           # Resend SDK for email sending and webhook verification
```

### Environment Variables (backend/.env.example)
```bash
# Email Provider Configuration (Required for Email to Attenly)
RESEND_API_KEY=your_resend_api_key_here
RESEND_WEBHOOK_SECRET=your_webhook_signing_secret_here

# Internal Authentication (Required for cron endpoints)
INTERNAL_CRON_SECRET=generate_a_strong_random_secret

# Email Domains (Required)
EMAIL_INGEST_DOMAIN=in.attently.ca
EMAIL_FROM_DOMAIN=mail.attenly.ca
EMAIL_FROM_ADDRESS=noreply@mail.attenly.ca

# Application URL (Required for links in emails)
APP_URL=https://app.attently.ca

# Email Feature Configuration (Optional - has defaults)
EMAIL_RATE_LIMIT_JOBS_PER_DAY=20
EMAIL_MAX_ATTACHMENT_SIZE_MB=25
EMAIL_MAX_TOTAL_SIZE_MB=50
EMAIL_ALLOWED_TYPES=pdf,docx,txt,png,jpg,jpeg,gif,webp
EMAIL_VERIFICATION_EXPIRY_HOURS=24
```

### External Services Configuration

**Resend Dashboard Tasks:**
1. Add and verify sending domain (mail.attenly.ca)
   - Add SPF record
   - Add DKIM record
   - Verify domain

2. Add and verify receiving domain (in.attently.ca)
   - Add MX record
   - Configure catch-all inbound route

3. Create inbound webhook
   - URL: `https://api.attenly.ca/webhooks/email-inbound`
   - Enable webhook signing
   - Note the signing secret

**Cloudflare DNS Tasks:**
Add records as specified by Resend dashboard

**Koyeb Configuration:**
1. Add environment variables to deployment
2. Set up cron trigger (Koyeb Cron or external):
   - URL: `https://api.attently.ca/internal/process-email-jobs`
   - Method: POST
   - Header: `X-Cron-Secret: {INTERNAL_CRON_SECRET}`
   - Schedule: Every 1-2 minutes

---

## [Testing]

Comprehensive test coverage for the email ingest feature.

### Unit Tests

**test_email_service.py:**
- Test verification email sending
- Test report ready email sending
- Test webhook signature verification (valid and invalid)

**test_email_ingest_service.py:**
- Test enable email ingest (new user)
- Test enable email ingest (already enabled)
- Test disable email ingest
- Test add verified sender (valid email)
- Test add verified sender (duplicate)
- Test verify sender (valid token)
- Test verify sender (expired token)
- Test verify sender (already used token)
- Test rate limiting logic

**test_email_job_service.py:**
- Test instruction extraction (various forward markers)
- Test process single job (happy path)
- Test process single job (attachment download failure)
- Test process single job (document processing failure)
- Test attachment type filtering
- Test attachment size validation

### Integration Tests

**test_webhook_handler.py:**
1. **Happy path**: Verified sender → valid alias → valid attachments → job created
2. **Unknown alias**: Email to non-existent alias → 200, no job
3. **Unverified sender**: Email from unverified address → 200, no job
4. **Duplicate webhook**: Same provider_message_id → 200, no duplicate job
5. **Rate limit exceeded**: 21st email in 24h → job with status=discarded
6. **No instructions**: Email with only attachments → job created with empty instructions
7. **Oversized attachments**: Attachment > 25MB → job with status=discarded
8. **Invalid file types**: .exe file → filtered out, valid types processed
9. **Invalid signature**: Webhook with bad signature → 401

**test_job_processing.py:**
1. **Complete workflow**: Pending job → process → report created → email sent → completed
2. **Processing failure**: Document processing fails → job marked failed
3. **Missing default agent**: Agent deleted → fallback to global default
4. **Multiple attachments**: Multiple PDFs → all processed into single report

### API Endpoint Tests

**test_email_ingest_api.py:**
- Test GET /email-ingest/settings (unauthorized)
- Test GET /email-ingest/settings (authorized)
- Test POST /email-ingest/enable (success)
- Test POST /email-ingest/enable (already enabled)
- Test POST /email-ingest/disable
- Test GET /email-ingest/verified-senders
- Test POST /email-ingest/verified-senders (valid email)
- Test POST /email-ingest/verified-senders (invalid email format)
- Test DELETE /email-ingest/verified-senders/{id}
- Test PUT /email-ingest/default-agent

**test_internal_cron.py:**
- Test POST /internal/process-email-jobs (valid secret)
- Test POST /internal/process-email-jobs (invalid secret) → 401

### Frontend Tests

**EmailIngestSettings.test.tsx:**
- Test settings page renders correctly
- Test enable button triggers API call
- Test disable button triggers API call
- Test alias copy to clipboard
- Test add sender modal opens and submits
- Test remove sender confirmation

**VerifiedSendersList.test.tsx:**
- Test renders sender list correctly
- Test status badges display correctly
- Test resend verification button works
- Test remove sender button works

---

## [Implementation Order]

Phased implementation approach with dependencies clearly marked.

### Phase 1: Database Schema (Day 1)
**Prerequisites:** None

**Tasks:**
1. Create `supabase/migrations/008_email_ingest.sql`
   - Define 3 tables with all constraints
   - Add RLS policies (explicit policies for all operations)
   - Create indexes for performance
   - Include verification queries

2. Run migration on Supabase
3. Verify tables and policies created correctly

**Deliverable:** Database schema ready with RLS enforcement

---

### Phase 2: Backend Configuration (Day 1)
**Prerequisites:** Phase 1 complete

**Tasks:**
1. Add Resend SDK to `requirements.txt`
2. Update `backend/app/config.py`:
   - Add email configuration section
   - Add validation for required email variables
   - Add default values for optional variables
3. Update `backend/.env.example` with documentation
4. Create local `.env` with test values

**Deliverable:** Backend configured for email services

---

### Phase 3: Email Service Adapter (Day 2)
**Prerequisites:** Phase 2 complete

**Tasks:**
1. Create `backend/app/services/email_service.py`
   - Implement Resend SDK wrapper
   - Implement verification email template
   - Implement report ready email template
   - Implement webhook signature verification
2. Write unit tests for email service
3. Test with Resend API in development

**Deliverable:** Email sending and webhook verification working

---

### Phase 4: Email Ingest Service (Day 2-3)
**Prerequisites:** Phase 3 complete

**Tasks:**
1. Create `backend/app/services/email_ingest_service.py`
   - Implement alias generation logic
   - Implement sender verification flow
   - Implement rate limiting logic
   - Use supabase_service for RLS-compliant DB operations
2. Write unit tests for ingest service
3. Integration test with database

**Deliverable:** Business logic for email ingest management

---

### Phase 5: Email Settings API (Day 3-4)
**Prerequisites:** Phase 4 complete

**Tasks:**
1. Create `backend/app/routers/email_ingest.py`
   - Implement all 8 user-facing endpoints
   - Add JWT authentication via get_current_user dependency
   - Add input validation with Pydantic schemas
2. Update `backend/app/schemas.py` with email types
3. Include router in `backend/app/main.py`
4. Write API endpoint tests
5. Test with Postman/curl

**Deliverable:** User-facing email settings API fully functional

---

### Phase 6: Webhook Handler (Day 4-5)
**Prerequisites:** Phase 5 complete

**Tasks:**
1. Create `backend/app/routers/webhooks.py`
   - Implement webhook signature verification
   - Implement idempotency logic
   - Implement alias and sender validation
   - Implement attachment handling (download, validate, upload to Storage)
   - Implement rate limiting check
   - Create email_jobs records
   - Add comprehensive logging
2. Update CORS in `main.py` if needed
3. Write webhook integration tests
4. Test with Resend webhook tester

**Deliverable:** Webhook receiving and validating inbound emails

---

### Phase 7: Job Processing Service (Day 5-6)
**Prerequisites:** Phase 6 complete

**Tasks:**
1. Create `backend/app/services/email_job_service.py`
   - Implement instruction extraction
   - Implement single job processing
   - Integrate with existing DocumentProcessor
   - Integrate with existing report_service
   - Implement notification email sending
   - Add error handling and logging
2. Write unit tests for job service
3. Test end-to-end with sample jobs

**Deliverable:** Job processing logic complete and tested

---

### Phase 8: Internal Cron Endpoint (Day 6)
**Prerequisites:** Phase 7 complete

**Tasks:**
1. Create `backend/app/routers/internal.py`
   - Implement cron endpoint with secret authentication
   - Call job processing service
   - Return processing summary
2. Add rate limiting to prevent overlapping runs
3. Write endpoint tests
4. Document cron setup for deployment

**Deliverable:** Cron endpoint ready for scheduling

---

### Phase 9: Frontend Settings Page (Day 7-8)
**Prerequisites:** Phase 5 complete (API available)

**Tasks:**
1. Update `frontend/src/types/index.ts` with email types
2. Create `frontend/src/pages/EmailIngestSettings.tsx`
   - Implement settings display
   - Implement enable/disable toggle
   - Implement alias display with copy button
   - Integrate with backend API
3. Create `frontend/src/components/email-ingest/VerifiedSendersList.tsx`
   - Implement sender table
   - Add status badges
   - Add action buttons
4. Create `frontend/src/components/email-ingest/AddSenderModal.tsx`
   - Implement modal form
   - Add email validation
5. Create `frontend/src/components/email-ingest/UsageInstructions.tsx`
   - Add step-by-step guide
6. Update `frontend/src/App.tsx` with new route
7. Add CSS styling
8. Write component tests

**Deliverable:** Fully functional settings UI

---

### Phase 10: Integration Testing & Deployment (Day 9-10)
**Prerequisites:** All phases complete

**Tasks:**
1. Run full test suite (unit + integration)
2. Configure Resend dashboard:
   - Add domains
   - Configure inbound route
   - Set up webhook
3. Configure Cloudflare DNS records
4. Deploy backend to Koyeb with env vars
5. Deploy frontend to Cloudflare Pages
6. Set up cron trigger
7. End-to-end smoke test:
   - Enable email ingest
   - Add verified sender
   - Verify sender via email
   - Send test email with attachment
   - Verify job processing
   - Verify report creation
   - Verify notification email
8. Monitor logs for errors
9. Document any issues and resolutions

**Deliverable:** Feature deployed and operational in production

---

## Key Design Decisions

### 1. Webhook Idempotency
- **Decision:** Use `provider_message_id` with unique constraint
- **Rationale:** Email providers retry webhooks, duplicate jobs would waste resources
- **Implementation:** Check for existing message_id before creating job, return 200 either way

### 2. Rate Limiting
- **Decision:** Database-level rate limiting (no Redis dependency)
- **Limit:** 20 jobs per user per 24 hours
- **Exceeded behavior:** Create job with `status=discarded`, no notification
- **Rationale:** Simple, works without additional infrastructure, prevents abuse

### 3. Attachment Handling
- **Allowed types:** PDF, DOCX, TXT, PNG, JPG, JPEG, GIF, WEBP
- **Max per attachment:** 25MB (configurable)
- **Max total per email:** 50MB (configurable)
- **Exceeded behavior:** Job created with `status=discarded` + error message
- **Storage:** Supabase Storage using existing patterns

### 4. Sender Verification
- **Token expiry:** 24 hours
- **Single-use:** Token cleared on successful verification
- **Case-insensitive:** Email comparison uses `LOWER()`
- **Invalid/expired UX:** Simple error message page

### 5. Default Agent Selection
- **Priority:** User's `default_agent_id` → Global fallback (first prebuilt agent)
- **Validation:** Settings API only shows agents user can access
- **Job processor:** Validates agent exists, uses fallback if deleted

### 6. Job Processing Architecture
- **Worker type:** Cron-triggered endpoint (no background process)
- **Batch size:** 10 jobs per cron run
- **Frequency:** Every 1-2 minutes
- **Authentication:** Shared secret in header
- **Rationale:** Simple, stateless, works on Koyeb free tier

### 7. Security Model
- **RLS enforcement:** All user data access via supabase_service with user JWT
- **Webhook security:** Signature verification, no sensitive data in logs
- **Cron security:** Secret header authentication
- **Token security:** UUID tokens, single-use, expiry enforced

---

## Observability & Monitoring

### Key Metrics to Track
1. `email.webhook.received` - Total webhooks received
2. `email.webhook.invalid_signature` - Signature verification failures
3. `email.webhook.duplicate_ignored` - Idempotency hits
4. `email.alias.not_found` - Unknown alias attempts (possible abuse)
5. `email.sender.not_verified` - Unauthorized sender attempts
6. `email.rate_limit.exceeded` - Rate limit hits per user
7. `email.job.created` - Successful job creations
8. `email.job.processing` - Job processing started
9. `email.job.completed` - Jobs completed with report_id
10. `email.job.failed` - Job failures with error types
11. `email.attachment.oversized` - Oversized attachment attempts
12. `email.attachment.invalid_type` - Invalid file type attempts

### Logging Standards
- **Webhook events:** Log at INFO level with correlation ID
- **Security events:** Log at WARNING level (signature failures, auth failures)
- **Job processing:** Log at INFO level with job_id and user_id
- **Errors:** Log at ERROR level with full context (no PII in logs)
- **No logging:** Raw email content, attachment binary data

### Error Handling Patterns
- **Webhook:** Always return 200 to prevent retries, log issues internally
- **API endpoints:** Return appropriate HTTP codes with user-friendly messages
- **Job processing:** Mark job as failed, store error_message, continue with next job
- **Email sending:** Log failures, don't fail job (report is still created)

---

## Security Considerations

### Data Protection
1. **Email content:** Never log full email bodies or attachment contents
2. **Tokens:** Store hashed if possible, clear after use
3. **User isolation:** All DB queries use RLS with user JWT
4. **File validation:** Strict type and size checks before processing
