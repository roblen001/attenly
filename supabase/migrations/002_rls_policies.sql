-- Row Level Security Policies for Existing Tables
-- This migration adds RLS policies to ensure proper user data isolation

-- Enable RLS on existing tables if not already enabled
ALTER TABLE saved_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_report_documents ENABLE ROW LEVEL SECURITY;

-- RLS policies for saved_reports table
-- Users can only access their own saved reports
CREATE POLICY "Users can view own saved reports" ON saved_reports
    FOR SELECT USING (auth.uid()::text = user_id);

CREATE POLICY "Users can insert own saved reports" ON saved_reports
    FOR INSERT WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can update own saved reports" ON saved_reports
    FOR UPDATE USING (auth.uid()::text = user_id);

CREATE POLICY "Users can delete own saved reports" ON saved_reports
    FOR DELETE USING (auth.uid()::text = user_id);

-- RLS policies for saved_report_documents table
-- Users can only access documents for their own reports
CREATE POLICY "Users can view own report documents" ON saved_report_documents
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM saved_reports 
            WHERE saved_reports.id = saved_report_documents.report_id 
            AND saved_reports.user_id = auth.uid()::text
        )
    );

CREATE POLICY "Users can insert own report documents" ON saved_report_documents
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM saved_reports 
            WHERE saved_reports.id = saved_report_documents.report_id 
            AND saved_reports.user_id = auth.uid()::text
        )
    );

CREATE POLICY "Users can update own report documents" ON saved_report_documents
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM saved_reports 
            WHERE saved_reports.id = saved_report_documents.report_id 
            AND saved_reports.user_id = auth.uid()::text
        )
    );

CREATE POLICY "Users can delete own report documents" ON saved_report_documents
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM saved_reports 
            WHERE saved_reports.id = saved_report_documents.report_id 
            AND saved_reports.user_id = auth.uid()::text
        )
    );

-- Create indexes for RLS policy performance
CREATE INDEX IF NOT EXISTS idx_saved_reports_user_id ON saved_reports(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_report_documents_report_id ON saved_report_documents(report_id);

-- Storage bucket policies (if using Supabase Storage)
-- These policies should be applied through the Supabase dashboard or CLI

-- Example policies for document storage bucket:
/*
-- Bucket: document-uploads
-- Policy: "Users can upload their own documents"
-- Expression: auth.uid()::text = (storage.foldername(name))[1]

-- Policy: "Users can view their own documents"
-- Expression: auth.uid()::text = (storage.foldername(name))[1]

-- Policy: "Users can delete their own documents"  
-- Expression: auth.uid()::text = (storage.foldername(name))[1]
*/

-- Add audit triggers for security monitoring (optional)
CREATE OR REPLACE FUNCTION audit_saved_reports()
RETURNS TRIGGER AS $$
BEGIN
    -- Log important operations for security monitoring
    IF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log (table_name, operation, user_id, record_id, timestamp)
        VALUES ('saved_reports', 'DELETE', OLD.user_id, OLD.id, NOW());
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log (table_name, operation, user_id, record_id, timestamp)
        VALUES ('saved_reports', 'UPDATE', NEW.user_id, NEW.id, NOW());
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log (table_name, operation, user_id, record_id, timestamp)
        VALUES ('saved_reports', 'INSERT', NEW.user_id, NEW.id, NOW());
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create audit log table (optional - for security monitoring)
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL,
    user_id TEXT,
    record_id UUID,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

-- Enable audit logging (optional)
-- CREATE TRIGGER audit_saved_reports_trigger
--     AFTER INSERT OR UPDATE OR DELETE ON saved_reports
--     FOR EACH ROW EXECUTE FUNCTION audit_saved_reports();

-- Grant necessary permissions
GRANT SELECT ON audit_log TO authenticated;

-- Add comments for documentation
COMMENT ON POLICY "Users can view own saved reports" ON saved_reports IS 'Users can only view their own saved reports';
COMMENT ON POLICY "Users can view own report documents" ON saved_report_documents IS 'Users can only view documents for their own reports';
COMMENT ON TABLE audit_log IS 'Security audit log for tracking data access and modifications';

-- Test RLS policies (these queries should only return user-specific data)
/*
-- Test queries to validate RLS policies:

-- Should only return current user's reports
SELECT * FROM saved_reports;

-- Should only return documents for current user's reports  
SELECT * FROM saved_report_documents;

-- Should only return current user's quota
SELECT * FROM user_quotas;
*/
