-- Migration 008: Email to Attenly Feature
-- Creates tables for email ingest endpoints, verified senders, and email jobs
-- Implements RLS policies for user isolation
-- Adds indexes for performance optimization

-- ============================================================================
-- TABLE: email_ingest_endpoints
-- Purpose: Store user's private email aliases for document submission
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_ingest_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,  -- matches users.id format (Supabase Auth UUID as text)
    local_part VARCHAR(255) NOT NULL,  -- e.g., "u_9b7c3ebdff4e4"
    domain VARCHAR(255) NOT NULL,      -- e.g., "in.attenly.ca"
    full_address VARCHAR(512) NOT NULL GENERATED ALWAYS AS (local_part || '@' || domain) STORED,
    is_active BOOLEAN NOT NULL DEFAULT true,
    default_agent_id TEXT,             -- null = use global default agent
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT unique_user_endpoint UNIQUE (user_id),
    CONSTRAINT unique_alias UNIQUE (local_part, domain)
);

-- Add index for fast alias lookups during webhook processing
CREATE INDEX IF NOT EXISTS idx_email_ingest_endpoints_full_address 
    ON email_ingest_endpoints(full_address) WHERE is_active = true;

-- Add index for user lookups
CREATE INDEX IF NOT EXISTS idx_email_ingest_endpoints_user_id 
    ON email_ingest_endpoints(user_id);

-- ============================================================================
-- TABLE: verified_senders
-- Purpose: Whitelist of verified sender email addresses per user
-- ============================================================================
CREATE TABLE IF NOT EXISTS verified_senders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'disabled')),
    verification_token VARCHAR(255),
    token_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT unique_user_email UNIQUE (user_id, email)
);

-- Add index for fast sender validation during webhook processing
CREATE INDEX IF NOT EXISTS idx_verified_senders_email_status 
    ON verified_senders(LOWER(email), status) WHERE status = 'verified';

-- Add index for user lookups
CREATE INDEX IF NOT EXISTS idx_verified_senders_user_id 
    ON verified_senders(user_id);

-- Add index for token lookup during verification
CREATE INDEX IF NOT EXISTS idx_verified_senders_token 
    ON verified_senders(verification_token) WHERE verification_token IS NOT NULL;

-- ============================================================================
-- TABLE: email_jobs
-- Purpose: Queue and track email processing jobs
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    ingest_endpoint_id UUID NOT NULL REFERENCES email_ingest_endpoints(id) ON DELETE CASCADE,
    from_email VARCHAR(255) NOT NULL,
    subject TEXT,
    instruction_text TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'discarded')),
    report_id UUID,  -- FK to saved_reports, null until completed
    provider_message_id VARCHAR(512) NOT NULL,  -- for idempotency
    raw_metadata JSONB,  -- provider webhook payload
    error_message TEXT,
    attachment_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    
    CONSTRAINT unique_provider_message UNIQUE (provider_message_id)
);

-- Add index for processing pending jobs (FIFO queue)
CREATE INDEX IF NOT EXISTS idx_email_jobs_pending 
    ON email_jobs(created_at) WHERE status = 'pending';

-- Add index for user job history lookups
CREATE INDEX IF NOT EXISTS idx_email_jobs_user_id 
    ON email_jobs(user_id, created_at DESC);

-- Add index for idempotency checks
CREATE INDEX IF NOT EXISTS idx_email_jobs_provider_message_id 
    ON email_jobs(provider_message_id);

-- Add index for rate limiting queries (jobs in last 24 hours)
CREATE INDEX IF NOT EXISTS idx_email_jobs_rate_limit 
    ON email_jobs(user_id, created_at) WHERE status != 'discarded';

-- ============================================================================
-- ROW LEVEL SECURITY POLICIES
-- Purpose: Enforce user isolation - users can only access their own data
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE email_ingest_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE verified_senders ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_jobs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- RLS Policies: email_ingest_endpoints
-- ============================================================================

-- Policy: Users can view their own endpoint
CREATE POLICY "Users can view own email endpoint"
    ON email_ingest_endpoints
    FOR SELECT
    USING (auth.uid()::text = user_id);

-- Policy: Users can insert their own endpoint
CREATE POLICY "Users can create own email endpoint"
    ON email_ingest_endpoints
    FOR INSERT
    WITH CHECK (auth.uid()::text = user_id);

-- Policy: Users can update their own endpoint
CREATE POLICY "Users can update own email endpoint"
    ON email_ingest_endpoints
    FOR UPDATE
    USING (auth.uid()::text = user_id)
    WITH CHECK (auth.uid()::text = user_id);

-- Policy: Users can delete their own endpoint
CREATE POLICY "Users can delete own email endpoint"
    ON email_ingest_endpoints
    FOR DELETE
    USING (auth.uid()::text = user_id);

-- ============================================================================
-- RLS Policies: verified_senders
-- ============================================================================

-- Policy: Users can view their own verified senders
CREATE POLICY "Users can view own verified senders"
    ON verified_senders
    FOR SELECT
    USING (auth.uid()::text = user_id);

-- Policy: Users can add their own verified senders
CREATE POLICY "Users can create own verified senders"
    ON verified_senders
    FOR INSERT
    WITH CHECK (auth.uid()::text = user_id);

-- Policy: Users can update their own verified senders
CREATE POLICY "Users can update own verified senders"
    ON verified_senders
    FOR UPDATE
    USING (auth.uid()::text = user_id)
    WITH CHECK (auth.uid()::text = user_id);

-- Policy: Users can delete their own verified senders
CREATE POLICY "Users can delete own verified senders"
    ON verified_senders
    FOR DELETE
    USING (auth.uid()::text = user_id);

-- ============================================================================
-- RLS Policies: email_jobs
-- ============================================================================

-- Policy: Users can view their own jobs
CREATE POLICY "Users can view own email jobs"
    ON email_jobs
    FOR SELECT
    USING (auth.uid()::text = user_id);

-- Policy: System can insert/update jobs (bypasses RLS when using service role)
-- Note: This will be handled by the backend using service role key
-- Users themselves should not be able to create jobs directly

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function: Check if user has reached rate limit
CREATE OR REPLACE FUNCTION check_email_rate_limit(
    p_user_id TEXT,
    p_limit INTEGER DEFAULT 20,
    p_window_hours INTEGER DEFAULT 24
) RETURNS BOOLEAN AS $$
DECLARE
    job_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO job_count
    FROM email_jobs
    WHERE user_id = p_user_id
        AND created_at > NOW() - (p_window_hours || ' hours')::INTERVAL
        AND status != 'discarded';
    
    RETURN job_count < p_limit;
END;
$$ LANGUAGE plpgsql;

-- Function: Get user's email ingest settings summary
CREATE OR REPLACE FUNCTION get_email_ingest_summary(p_user_id TEXT)
RETURNS TABLE(
    enabled BOOLEAN,
    email_alias TEXT,
    default_agent_id TEXT,
    verified_senders_count BIGINT,
    pending_jobs_count BIGINT,
    completed_jobs_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(e.is_active, false) as enabled,
        e.full_address as email_alias,
        e.default_agent_id,
        COALESCE((SELECT COUNT(*) FROM verified_senders WHERE user_id = p_user_id AND status = 'verified'), 0) as verified_senders_count,
        COALESCE((SELECT COUNT(*) FROM email_jobs WHERE user_id = p_user_id AND status = 'pending'), 0) as pending_jobs_count,
        COALESCE((SELECT COUNT(*) FROM email_jobs WHERE user_id = p_user_id AND status = 'completed'), 0) as completed_jobs_count
    FROM email_ingest_endpoints e
    WHERE e.user_id = p_user_id;
    
    -- If no endpoint exists, return defaults
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, NULL::TEXT, NULL::TEXT, 0::BIGINT, 0::BIGINT, 0::BIGINT;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VERIFICATION QUERIES
-- Purpose: Validate schema and policies are correctly created
-- ============================================================================

-- Verify tables exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'email_ingest_endpoints') THEN
        RAISE EXCEPTION 'Table email_ingest_endpoints was not created';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'verified_senders') THEN
        RAISE EXCEPTION 'Table verified_senders was not created';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'email_jobs') THEN
        RAISE EXCEPTION 'Table email_jobs was not created';
    END IF;
    
    RAISE NOTICE 'Migration 008: All tables created successfully';
END $$;

-- Verify RLS is enabled
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables 
        WHERE tablename = 'email_ingest_endpoints' 
        AND rowsecurity = true
    ) THEN
        RAISE EXCEPTION 'RLS not enabled on email_ingest_endpoints';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables 
        WHERE tablename = 'verified_senders' 
        AND rowsecurity = true
    ) THEN
        RAISE EXCEPTION 'RLS not enabled on verified_senders';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables 
        WHERE tablename = 'email_jobs' 
        AND rowsecurity = true
    ) THEN
        RAISE EXCEPTION 'RLS not enabled on email_jobs';
    END IF;
    
    RAISE NOTICE 'Migration 008: RLS enabled on all tables';
END $$;

-- Verify indexes exist
DO $$
DECLARE
    index_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE tablename IN ('email_ingest_endpoints', 'verified_senders', 'email_jobs')
    AND indexname LIKE 'idx_%';
    
    IF index_count < 8 THEN
        RAISE WARNING 'Expected at least 8 indexes, found %', index_count;
    ELSE
        RAISE NOTICE 'Migration 008: % indexes created successfully', index_count;
    END IF;
END $$;

-- Verify helper functions exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc 
        WHERE proname = 'check_email_rate_limit'
    ) THEN
        RAISE EXCEPTION 'Function check_email_rate_limit was not created';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc 
        WHERE proname = 'get_email_ingest_summary'
    ) THEN
        RAISE EXCEPTION 'Function get_email_ingest_summary was not created';
    END IF;
    
    RAISE NOTICE 'Migration 008: Helper functions created successfully';
END $$;

-- Final success message
DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 008: Email Ingest Feature';
    RAISE NOTICE 'Status: COMPLETED SUCCESSFULLY';
    RAISE NOTICE '========================================';
END $$;
