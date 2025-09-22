-- Supabase Schema for Saved Reports
-- Run this in your Supabase SQL editor to create the required tables

-- Main table for saved reports
CREATE TABLE saved_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    report_name TEXT NOT NULL,
    
    -- Complete report data (everything needed for preview)
    report_data JSONB NOT NULL,  -- Full ReportData structure with quotes
    
    generated_at TIMESTAMPTZ NOT NULL,
    saved_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Index for efficient querying
    CONSTRAINT saved_reports_user_idx UNIQUE (user_id, saved_at DESC)
);

-- Critical table for document content (needed for quote viewing)
CREATE TABLE saved_report_documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id UUID REFERENCES saved_reports(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,  -- Original document ID from processing
    filename TEXT NOT NULL,
    
    -- Full document content (needed for DocumentViewer)
    full_text TEXT NOT NULL,           -- Complete document text with page markers
    pages_info JSONB NOT NULL,         -- PageInfo[] for navigation
    total_pages INTEGER NOT NULL,
    total_characters INTEGER NOT NULL,
    metadata JSONB NOT NULL,           -- File size, type, processing stats
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Ensure one record per document per report
    CONSTRAINT unique_document_per_report UNIQUE (report_id, document_id)
);

-- Enable Row Level Security
ALTER TABLE saved_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_report_documents ENABLE ROW LEVEL SECURITY;

-- RLS Policies for security
CREATE POLICY "Users can only access their own saved reports" ON saved_reports
    FOR ALL USING (auth.uid()::text = user_id);

CREATE POLICY "Users can only access documents from their own reports" ON saved_report_documents
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM saved_reports 
            WHERE saved_reports.id = saved_report_documents.report_id 
            AND saved_reports.user_id = auth.uid()::text
        )
    );

-- Create indexes for better performance
CREATE INDEX idx_saved_reports_user_date ON saved_reports(user_id, saved_at DESC);
CREATE INDEX idx_saved_report_documents_report ON saved_report_documents(report_id);
CREATE INDEX idx_saved_report_documents_doc_id ON saved_report_documents(document_id);
