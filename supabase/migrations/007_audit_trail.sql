-- Migration 007: Audit Trail for Saved Reports
-- Purpose: Add AI baseline tracking and change history for saved reports
-- This enables "track changes" style visualization showing what users changed
-- from the original AI-generated content to the final saved version.

-- ============================================================================
-- STEP 1: Add AI Baseline Column to saved_reports
-- ============================================================================
-- Store the original AI-generated answers for comparison
-- This is captured on first save and never changes
ALTER TABLE saved_reports
ADD COLUMN IF NOT EXISTS ai_baseline_answers JSONB;

-- Add comment for documentation
COMMENT ON COLUMN saved_reports.ai_baseline_answers IS 
'Original AI-generated answers stored on first save. Used as baseline for computing diffs. Structure: {"placeholder": "ai_text", ...}';

-- ============================================================================
-- STEP 2: Create report_revisions Table (Optional Metadata)
-- ============================================================================
-- Tracks each save event for a report
-- Lightweight table for metadata about when edits were made
CREATE TABLE IF NOT EXISTS report_revisions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES saved_reports(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    revision_number INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(report_id, revision_number)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_report_revisions_report_id ON report_revisions(report_id);
CREATE INDEX IF NOT EXISTS idx_report_revisions_user_id ON report_revisions(user_id);
CREATE INDEX IF NOT EXISTS idx_report_revisions_created_at ON report_revisions(created_at DESC);

-- Add comments for documentation
COMMENT ON TABLE report_revisions IS 
'Tracks each save event for a report. Provides history of when edits were made.';
COMMENT ON COLUMN report_revisions.revision_number IS 
'Sequential revision number starting from 1. Auto-incremented on each save.';

-- ============================================================================
-- STEP 3: Create report_changes Table (Current Diff State)
-- ============================================================================
-- Stores the current diff between AI baseline and latest saved version
-- REPLACED (not accumulated) on each save to keep it lean
CREATE TABLE IF NOT EXISTS report_changes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES saved_reports(id) ON DELETE CASCADE,
    answer_placeholder VARCHAR(255) NOT NULL,
    change_type VARCHAR(10) NOT NULL CHECK (change_type IN ('insert', 'delete')),
    text_content TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    user_id UUID NOT NULL,
    user_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CHECK (start_offset >= 0),
    CHECK (end_offset >= start_offset)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_report_changes_report_id ON report_changes(report_id);
CREATE INDEX IF NOT EXISTS idx_report_changes_answer_placeholder ON report_changes(answer_placeholder);
CREATE INDEX IF NOT EXISTS idx_report_changes_user_id ON report_changes(user_id);

-- Add comments for documentation
COMMENT ON TABLE report_changes IS 
'Stores current diff between AI baseline and latest saved version. Replaced (not accumulated) on each save.';
COMMENT ON COLUMN report_changes.change_type IS 
'Type of change: "insert" (green highlight) or "delete" (red strikethrough)';
COMMENT ON COLUMN report_changes.text_content IS 
'The actual text that was inserted or deleted';
COMMENT ON COLUMN report_changes.start_offset IS 
'Character offset where change begins in the final text';
COMMENT ON COLUMN report_changes.end_offset IS 
'Character offset where change ends in the final text';
COMMENT ON COLUMN report_changes.answer_placeholder IS 
'The question placeholder this change belongs to (e.g., "loss_description")';

-- ============================================================================
-- STEP 4: Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS on new tables
ALTER TABLE report_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_changes ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- RLS Policies for report_revisions
-- ============================================================================

-- Allow users to view their own report revisions
CREATE POLICY "Users can view their own report revisions" ON report_revisions
    FOR SELECT
    USING (user_id = auth.uid());

-- Allow users to insert revisions for their own reports
CREATE POLICY "Users can create revisions for their own reports" ON report_revisions
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- No UPDATE or DELETE policies - revisions are immutable audit records

-- ============================================================================
-- RLS Policies for report_changes
-- ============================================================================

-- Allow users to view changes for their own reports
CREATE POLICY "Users can view changes for their own reports" ON report_changes
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM saved_reports
            WHERE saved_reports.id = report_changes.report_id
            AND saved_reports.user_id = auth.uid()
        )
    );

-- Allow users to insert changes for their own reports
CREATE POLICY "Users can create changes for their own reports" ON report_changes
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM saved_reports
            WHERE saved_reports.id = report_changes.report_id
            AND saved_reports.user_id = auth.uid()
        )
    );

-- Allow users to delete changes for their own reports (for replacement on save)
CREATE POLICY "Users can delete changes for their own reports" ON report_changes
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM saved_reports
            WHERE saved_reports.id = report_changes.report_id
            AND saved_reports.user_id = auth.uid()
        )
    );

-- ============================================================================
-- STEP 5: Verification Queries
-- ============================================================================

-- Verify tables exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'saved_reports' 
                   AND column_name = 'ai_baseline_answers') THEN
        RAISE EXCEPTION 'Column ai_baseline_answers not added to saved_reports';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_name = 'report_revisions') THEN
        RAISE EXCEPTION 'Table report_revisions not created';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_name = 'report_changes') THEN
        RAISE EXCEPTION 'Table report_changes not created';
    END IF;
    
    RAISE NOTICE 'Migration 007: Audit Trail schema created successfully';
END $$;
