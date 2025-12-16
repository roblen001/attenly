-- Migration: Monthly Credit-Based Rate Limiting System
-- This migration adds cost-based credit tracking with monthly billing periods

-- =============================================================================
-- 1. CREATE OR MODIFY user_quotas TABLE FOR MONTHLY CREDITS
-- =============================================================================

-- Create user_quotas table if it doesn't exist (from 001_user_quotas.sql)
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

-- Enable RLS on user_quotas table (idempotent)
ALTER TABLE user_quotas ENABLE ROW LEVEL SECURITY;

-- Create RLS policies if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'user_quotas' AND policyname = 'Users can view own quota'
    ) THEN
        CREATE POLICY "Users can view own quota" ON user_quotas
            FOR SELECT USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'user_quotas' AND policyname = 'Users can update own quota'
    ) THEN
        CREATE POLICY "Users can update own quota" ON user_quotas
            FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

-- Add new columns for monthly cost-based tracking
ALTER TABLE user_quotas
  ADD COLUMN IF NOT EXISTS monthly_limit_cad DECIMAL(10,4) DEFAULT 50.00,
  ADD COLUMN IF NOT EXISTS cost_used_cad DECIMAL(10,4) DEFAULT 0.00,
  ADD COLUMN IF NOT EXISTS billing_period_start DATE DEFAULT DATE_TRUNC('month', NOW())::DATE,
  ADD COLUMN IF NOT EXISTS last_warning_level INTEGER DEFAULT 0;

-- Update existing records to have proper billing period start
UPDATE user_quotas
SET billing_period_start = DATE_TRUNC('month', NOW())::DATE
WHERE billing_period_start IS NULL;

-- =============================================================================
-- 2. CREATE usage_logs TABLE FOR DETAILED TRACKING
-- =============================================================================

CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    operation_type VARCHAR(50) NOT NULL,  -- 'llm_extraction', 'llm_template', 'embedding'
    model_name VARCHAR(100) NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_cad DECIMAL(10,6) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::JSONB
);

-- Enable RLS on usage_logs
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for usage_logs if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'usage_logs' AND policyname = 'Users can view own usage logs'
    ) THEN
        CREATE POLICY "Users can view own usage logs" ON usage_logs
            FOR SELECT USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'usage_logs' AND policyname = 'Service can insert usage logs'
    ) THEN
        CREATE POLICY "Service can insert usage logs" ON usage_logs
            FOR INSERT WITH CHECK (true);
    END IF;
END $$;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_usage_logs_user_id ON usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created_at ON usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_logs_user_created ON usage_logs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_logs_operation_type ON usage_logs(operation_type);

-- =============================================================================
-- 3. UPDATE consume_credits FUNCTION FOR COST-BASED TRACKING
-- =============================================================================

CREATE OR REPLACE FUNCTION consume_cost(
    p_user_id UUID,
    p_cost_cad DECIMAL(10,6)
) RETURNS TABLE(
    allowed BOOLEAN,
    credits_remaining DECIMAL(10,4),
    credits_limit DECIMAL(10,4),
    percentage_used DECIMAL(5,2),
    warning_level INTEGER
) AS $$
DECLARE
    v_current_cost DECIMAL(10,4);
    v_monthly_limit DECIMAL(10,4);
    v_billing_start DATE;
    v_new_cost DECIMAL(10,4);
    v_percentage DECIMAL(5,2);
    v_warning INTEGER;
BEGIN
    -- Lock the row to prevent race conditions
    SELECT cost_used_cad, monthly_limit_cad, billing_period_start
    INTO v_current_cost, v_monthly_limit, v_billing_start
    FROM user_quotas
    WHERE user_quotas.user_id = p_user_id
    FOR UPDATE;

    -- If no quota record exists, create one with defaults
    IF NOT FOUND THEN
        INSERT INTO user_quotas (user_id, monthly_limit_cad, cost_used_cad, billing_period_start, plan)
        VALUES (p_user_id, 50.00, p_cost_cad, DATE_TRUNC('month', NOW())::DATE, 'free')
        RETURNING cost_used_cad, monthly_limit_cad, billing_period_start
        INTO v_current_cost, v_monthly_limit, v_billing_start;

        v_new_cost := p_cost_cad;
        v_percentage := (v_new_cost / v_monthly_limit) * 100;
        v_warning := CASE
            WHEN v_percentage >= 100 THEN 3  -- blocked
            WHEN v_percentage >= 90 THEN 2   -- critical
            WHEN v_percentage >= 70 THEN 1   -- warning
            ELSE 0                            -- normal
        END;

        RETURN QUERY SELECT
            TRUE as allowed,
            (v_monthly_limit - v_new_cost) as credits_remaining,
            v_monthly_limit as credits_limit,
            v_percentage as percentage_used,
            v_warning as warning_level;
        RETURN;
    END IF;

    -- Check if we need to reset for new billing period (new month)
    IF DATE_TRUNC('month', NOW())::DATE > v_billing_start THEN
        -- Reset for new billing period
        UPDATE user_quotas
        SET cost_used_cad = p_cost_cad,
            billing_period_start = DATE_TRUNC('month', NOW())::DATE,
            last_warning_level = 0,
            updated_at = NOW()
        WHERE user_quotas.user_id = p_user_id;

        v_new_cost := p_cost_cad;
    ELSE
        -- Same billing period - add to existing cost
        v_new_cost := v_current_cost + p_cost_cad;

        -- Update the cost
        UPDATE user_quotas
        SET cost_used_cad = v_new_cost,
            updated_at = NOW()
        WHERE user_quotas.user_id = p_user_id;
    END IF;

    -- Calculate percentage and warning level
    v_percentage := (v_new_cost / v_monthly_limit) * 100;
    v_warning := CASE
        WHEN v_percentage >= 100 THEN 3  -- blocked
        WHEN v_percentage >= 90 THEN 2   -- critical
        WHEN v_percentage >= 70 THEN 1   -- warning
        ELSE 0                            -- normal
    END;

    -- Update warning level if it increased
    IF v_warning > (SELECT last_warning_level FROM user_quotas WHERE user_quotas.user_id = p_user_id) THEN
        UPDATE user_quotas
        SET last_warning_level = v_warning
        WHERE user_quotas.user_id = p_user_id;
    END IF;

    RETURN QUERY SELECT
        (v_percentage < 100) as allowed,
        (v_monthly_limit - v_new_cost) as credits_remaining,
        v_monthly_limit as credits_limit,
        v_percentage as percentage_used,
        v_warning as warning_level;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 4. CREATE get_user_credits FUNCTION
-- =============================================================================

CREATE OR REPLACE FUNCTION get_user_credits(p_user_id UUID)
RETURNS TABLE(
    user_id UUID,
    plan VARCHAR(50),
    cost_used_cad DECIMAL(10,4),
    monthly_limit_cad DECIMAL(10,4),
    credits_remaining DECIMAL(10,4),
    percentage_used DECIMAL(5,2),
    warning_level INTEGER,
    billing_period_start DATE,
    days_until_reset INTEGER
) AS $$
DECLARE
    v_billing_start DATE;
    v_next_reset DATE;
BEGIN
    -- Check if billing period needs to be reset
    SELECT uq.billing_period_start INTO v_billing_start
    FROM user_quotas uq
    WHERE uq.user_id = p_user_id;

    -- If billing period is in a past month, reset it
    IF v_billing_start IS NOT NULL AND DATE_TRUNC('month', NOW())::DATE > v_billing_start THEN
        UPDATE user_quotas
        SET cost_used_cad = 0,
            billing_period_start = DATE_TRUNC('month', NOW())::DATE,
            last_warning_level = 0,
            updated_at = NOW()
        WHERE user_quotas.user_id = p_user_id;
    END IF;

    RETURN QUERY
    SELECT
        uq.user_id,
        uq.plan,
        COALESCE(uq.cost_used_cad, 0) as cost_used_cad,
        COALESCE(uq.monthly_limit_cad, 50.00) as monthly_limit_cad,
        (COALESCE(uq.monthly_limit_cad, 50.00) - COALESCE(uq.cost_used_cad, 0)) as credits_remaining,
        CASE
            WHEN uq.monthly_limit_cad > 0 THEN
                ROUND((COALESCE(uq.cost_used_cad, 0) / uq.monthly_limit_cad) * 100, 2)
            ELSE 0
        END as percentage_used,
        CASE
            WHEN uq.monthly_limit_cad > 0 AND (uq.cost_used_cad / uq.monthly_limit_cad) >= 1 THEN 3
            WHEN uq.monthly_limit_cad > 0 AND (uq.cost_used_cad / uq.monthly_limit_cad) >= 0.9 THEN 2
            WHEN uq.monthly_limit_cad > 0 AND (uq.cost_used_cad / uq.monthly_limit_cad) >= 0.7 THEN 1
            ELSE 0
        END as warning_level,
        COALESCE(uq.billing_period_start, DATE_TRUNC('month', NOW())::DATE) as billing_period_start,
        (DATE_TRUNC('month', NOW() + INTERVAL '1 month')::DATE - CURRENT_DATE) as days_until_reset
    FROM user_quotas uq
    WHERE uq.user_id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 5. CREATE get_usage_summary FUNCTION
-- =============================================================================

CREATE OR REPLACE FUNCTION get_usage_summary(
    p_user_id UUID,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE(
    operation_type VARCHAR(50),
    total_cost_cad DECIMAL(10,4),
    total_input_tokens BIGINT,
    total_output_tokens BIGINT,
    request_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ul.operation_type,
        SUM(ul.cost_cad)::DECIMAL(10,4) as total_cost_cad,
        SUM(ul.input_tokens)::BIGINT as total_input_tokens,
        SUM(ul.output_tokens)::BIGINT as total_output_tokens,
        COUNT(*)::BIGINT as request_count
    FROM usage_logs ul
    WHERE ul.user_id = p_user_id
      AND ul.created_at >= NOW() - (p_days || ' days')::INTERVAL
    GROUP BY ul.operation_type
    ORDER BY total_cost_cad DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 6. CREATE get_usage_history FUNCTION
-- =============================================================================

CREATE OR REPLACE FUNCTION get_usage_history(
    p_user_id UUID,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE(
    date DATE,
    total_cost_cad DECIMAL(10,4),
    request_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        DATE(ul.created_at) as date,
        SUM(ul.cost_cad)::DECIMAL(10,4) as total_cost_cad,
        COUNT(*)::BIGINT as request_count
    FROM usage_logs ul
    WHERE ul.user_id = p_user_id
      AND ul.created_at >= NOW() - (p_days || ' days')::INTERVAL
    GROUP BY DATE(ul.created_at)
    ORDER BY date DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 7. UPDATE TRIGGER FOR NEW USERS
-- =============================================================================

-- Update the trigger function to include new columns
CREATE OR REPLACE FUNCTION create_user_quota_on_signup()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_quotas (
        user_id,
        plan,
        credits_remaining,
        monthly_limit_cad,
        cost_used_cad,
        billing_period_start
    )
    VALUES (
        NEW.id,
        'free',
        100,  -- legacy field
        50.00,
        0.00,
        DATE_TRUNC('month', NOW())::DATE
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'on_auth_user_created'
    ) THEN
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION create_user_quota_on_signup();
    END IF;
END $$;

-- =============================================================================
-- 8. GRANT PERMISSIONS
-- =============================================================================

GRANT SELECT ON usage_logs TO authenticated;
GRANT EXECUTE ON FUNCTION consume_cost(UUID, DECIMAL) TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_credits(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_usage_summary(UUID, INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION get_usage_history(UUID, INTEGER) TO authenticated;

-- Grant service role full access for inserting usage logs
GRANT INSERT ON usage_logs TO service_role;
GRANT ALL ON usage_logs TO service_role;

-- =============================================================================
-- 9. ADD COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE usage_logs IS 'Detailed usage tracking for cost-based rate limiting';
COMMENT ON COLUMN user_quotas.monthly_limit_cad IS 'Monthly spending limit in CAD';
COMMENT ON COLUMN user_quotas.cost_used_cad IS 'Total cost spent in current billing period (CAD)';
COMMENT ON COLUMN user_quotas.billing_period_start IS 'Start date of current billing period';
COMMENT ON COLUMN user_quotas.last_warning_level IS '0=normal, 1=warning(70%), 2=critical(90%), 3=blocked(100%)';
COMMENT ON FUNCTION consume_cost(UUID, DECIMAL) IS 'Atomically consume credits and return updated status';
COMMENT ON FUNCTION get_user_credits(UUID) IS 'Get current credit status for a user';
COMMENT ON FUNCTION get_usage_summary(UUID, INTEGER) IS 'Get usage breakdown by operation type';
COMMENT ON FUNCTION get_usage_history(UUID, INTEGER) IS 'Get daily usage history';
