-- Migration: Add report_template_css column to agents table
-- Description: Adds support for storing separate CSS styling for agent report templates
--              Nullable for backward compatibility with existing agents
-- Date: 2025-12-07

-- Add the new column for storing CSS rules
ALTER TABLE agents ADD COLUMN IF NOT EXISTS report_template_css TEXT;

-- Add comment for documentation
COMMENT ON COLUMN agents.report_template_css IS 'CSS rules for styling the report template. Used in TinyMCE content_style and PDF generation. Nullable for backward compatibility.';
