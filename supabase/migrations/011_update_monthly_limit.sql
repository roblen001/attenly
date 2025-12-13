-- Migration: Update default monthly limit from $50 CAD to $15 CAD
-- This updates the default limit for new users and existing records

-- =============================================================================
-- 1. UPDATE EXISTING USER RECORDS
-- =============================================================================

UPDATE user_quotas
SET monthly_limit_cad = 15.00
WHERE monthly_limit_cad = 50.00;

-- =============================================================================
-- 2. UPDATE COLUMN DEFAULT
-- =============================================================================

ALTER TABLE user_quotas
ALTER COLUMN monthly_limit_cad SET DEFAULT 15.00;

-- =============================================================================
-- 3. UPDATE consume_cost FUNCTION (fix hardcoded 50.00)
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
        VALUES (p_user_id, 15.00, p_cost_cad, DATE_TRUNC('month', NOW())::DATE, 'free')
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
-- 4. UPDATE get_user_credits FUNCTION (fix hardcoded 50.00 fallback)
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
        COALESCE(uq.monthly_limit_cad, 15.00) as monthly_limit_cad,
        (COALESCE(uq.monthly_limit_cad, 15.00) - COALESCE(uq.cost_used_cad, 0)) as credits_remaining,
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
-- 5. UPDATE TRIGGER FUNCTION FOR NEW USERS
-- =============================================================================

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
        15.00,
        0.00,
        DATE_TRUNC('month', NOW())::DATE
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
