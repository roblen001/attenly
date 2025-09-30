-- User Quota System for Credit Management
-- This migration creates the quota system for controlling user access to LLM operations

-- Create user_quotas table for tracking user credits and limits
CREATE TABLE IF NOT EXISTS user_quotas (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    period_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    credits_remaining INTEGER NOT NULL DEFAULT 100,
    requests_per_hour INTEGER NOT NULL DEFAULT 100,
    llm_credits_per_hour INTEGER NOT NULL DEFAULT 10,
    upload_limit_per_hour INTEGER NOT NULL DEFAULT 20,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS on user_quotas table
ALTER TABLE user_quotas ENABLE ROW LEVEL SECURITY;

-- RLS policy: Users can only see their own quota
CREATE POLICY "Users can view own quota" ON user_quotas
    FOR SELECT USING (auth.uid() = user_id);

-- RLS policy: Users can update their own quota (for consumption tracking)
CREATE POLICY "Users can update own quota" ON user_quotas
    FOR UPDATE USING (auth.uid() = user_id);

-- Create function to consume credits atomically
CREATE OR REPLACE FUNCTION consume_credits(
    p_user_id UUID,
    p_cost INTEGER DEFAULT 1
) RETURNS BOOLEAN AS $$
DECLARE
    current_credits INTEGER;
    current_period TIMESTAMP WITH TIME ZONE;
    period_duration INTERVAL := '1 hour';
BEGIN
    -- Use FOR UPDATE to prevent race conditions
    SELECT credits_remaining, period_start 
    INTO current_credits, current_period
    FROM user_quotas 
    WHERE user_id = p_user_id
    FOR UPDATE;
    
    -- If no quota record exists, create one
    IF NOT FOUND THEN
        INSERT INTO user_quotas (user_id, credits_remaining, period_start)
        VALUES (p_user_id, 100 - p_cost, NOW());
        RETURN TRUE;
    END IF;
    
    -- Check if we need to reset the period (new hour)
    IF NOW() - current_period > period_duration THEN
        -- Reset credits for new period
        UPDATE user_quotas 
        SET credits_remaining = 100 - p_cost,
            period_start = NOW(),
            updated_at = NOW()
        WHERE user_id = p_user_id;
        RETURN TRUE;
    END IF;
    
    -- Check if user has enough credits
    IF current_credits >= p_cost THEN
        -- Consume credits
        UPDATE user_quotas 
        SET credits_remaining = credits_remaining - p_cost,
            updated_at = NOW()
        WHERE user_id = p_user_id;
        RETURN TRUE;
    ELSE
        -- Insufficient credits
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to get user quota status
CREATE OR REPLACE FUNCTION get_user_quota(p_user_id UUID)
RETURNS TABLE(
    user_id UUID,
    plan VARCHAR(50),
    credits_remaining INTEGER,
    credits_limit INTEGER,
    period_start TIMESTAMP WITH TIME ZONE,
    time_until_reset INTERVAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        uq.user_id,
        uq.plan,
        uq.credits_remaining,
        CASE uq.plan 
            WHEN 'premium' THEN 500
            WHEN 'pro' THEN 200
            ELSE 100
        END as credits_limit,
        uq.period_start,
        (uq.period_start + INTERVAL '1 hour' - NOW()) as time_until_reset
    FROM user_quotas uq
    WHERE uq.user_id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_quotas_user_id ON user_quotas(user_id);
CREATE INDEX IF NOT EXISTS idx_user_quotas_period_start ON user_quotas(period_start);

-- Grant appropriate permissions
GRANT SELECT, UPDATE ON user_quotas TO authenticated;
GRANT EXECUTE ON FUNCTION consume_credits(UUID, INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_quota(UUID) TO authenticated;

-- Create trigger to automatically create quota record for new users
CREATE OR REPLACE FUNCTION create_user_quota_on_signup()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_quotas (user_id, plan, credits_remaining)
    VALUES (NEW.id, 'free', 100);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION create_user_quota_on_signup();

-- Add comments for documentation
COMMENT ON TABLE user_quotas IS 'User quota tracking for rate limiting and credit management';
COMMENT ON FUNCTION consume_credits(UUID, INTEGER) IS 'Atomically consume user credits with race condition protection';
COMMENT ON FUNCTION get_user_quota(UUID) IS 'Get current quota status for a user';
