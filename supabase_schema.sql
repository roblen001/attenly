-- Enable extension for gen_random_uuid (safe if already enabled)
create extension if not exists pgcrypto;

-- Main table for saved reports
create table if not exists saved_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,                  -- match auth.uid() type
  agent_id text not null,
  agent_name text not null,
  report_name text not null,

  -- Complete report data (everything needed for preview)
  report_data jsonb not null,             -- Full ReportData structure with quotes

  generated_at timestamptz not null default now(),
  saved_at timestamptz not null default now()
);

-- Critical table for document content (needed for quote viewing)
create table if not exists saved_report_documents (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references saved_reports(id) on delete cascade,
  document_id text not null,              -- Original document ID from processing
  filename text not null,

  -- Full document content (needed for DocumentViewer)
  full_text text not null,                -- Complete document text with page markers
  pages_info jsonb not null,              -- PageInfo[] for navigation
  total_pages integer not null,
  total_characters integer not null,
  metadata jsonb not null,                -- File size, type, processing stats

  created_at timestamptz not null default now(),

  -- Ensure one record per document per report
  constraint unique_document_per_report unique (report_id, document_id)
);

-- Enable Row Level Security
alter table saved_reports enable row level security;
alter table saved_report_documents enable row level security;

-- RLS: saved_reports (separate policies for clarity)
drop policy if exists "sr_select_own" on saved_reports;
create policy "sr_select_own" on saved_reports
  for select using (user_id = auth.uid());

drop policy if exists "sr_insert_own" on saved_reports;
create policy "sr_insert_own" on saved_reports
  for insert with check (user_id = auth.uid());

drop policy if exists "sr_update_own" on saved_reports;
create policy "sr_update_own" on saved_reports
  for update using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "sr_delete_own" on saved_reports;
create policy "sr_delete_own" on saved_reports
  for delete using (user_id = auth.uid());

-- RLS: saved_report_documents
drop policy if exists "srd_select_own" on saved_report_documents;
create policy "srd_select_own" on saved_report_documents
  for select using (
    exists (
      select 1 from saved_reports r
      where r.id = saved_report_documents.report_id
        and r.user_id = auth.uid()
    )
  );

drop policy if exists "srd_insert_own" on saved_report_documents;
create policy "srd_insert_own" on saved_report_documents
  for insert with check (
    exists (
      select 1 from saved_reports r
      where r.id = report_id
        and r.user_id = auth.uid()
    )
  );

drop policy if exists "srd_update_own" on saved_report_documents;
create policy "srd_update_own" on saved_report_documents
  for update using (
    exists (
      select 1 from saved_reports r
      where r.id = saved_report_documents.report_id
        and r.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from saved_reports r
      where r.id = report_id
        and r.user_id = auth.uid()
    )
  );

drop policy if exists "srd_delete_own" on saved_report_documents;
create policy "srd_delete_own" on saved_report_documents
  for delete using (
    exists (
      select 1 from saved_reports r
      where r.id = saved_report_documents.report_id
        and r.user_id = auth.uid()
    )
  );

-- Indexes (ordered for common queries)
create index if not exists idx_saved_reports_user_date
  on saved_reports(user_id, saved_at desc);

create index if not exists idx_saved_report_documents_report
  on saved_report_documents(report_id);

create index if not exists idx_saved_report_documents_doc_id
  on saved_report_documents(document_id);

-- Optional: if you plan to filter inside report_data or metadata often
-- create index if not exists idx_saved_reports_report_data_gin on saved_reports using gin (report_data);
-- create index if not exists idx_saved_report_documents_metadata_gin on saved_report_documents using gin (metadata);
