-- ============================================================================
-- Email Poll State
-- Purpose: Persist cursor/checkpoint data for polling inbound email providers.
-- ============================================================================

CREATE TABLE IF NOT EXISTS email_poll_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider VARCHAR(80) NOT NULL,
    mailbox VARCHAR(255) NOT NULL,
    state_key VARCHAR(255) NOT NULL DEFAULT 'default',
    delta_link TEXT,
    last_message_id VARCHAR(512),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_polled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_email_poll_state UNIQUE (provider, mailbox, state_key)
);

CREATE INDEX IF NOT EXISTS idx_email_poll_state_provider_mailbox
    ON email_poll_state(provider, mailbox);

ALTER TABLE email_poll_state ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role can manage email poll state" ON email_poll_state;
CREATE POLICY "Service role can manage email poll state"
    ON email_poll_state
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
