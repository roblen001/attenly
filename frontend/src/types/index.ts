export interface Question {
  id: string;
  placeholder: string; // tag that will be replaced with the LLM answer
  prompt: string;
  exampleAnswer?: string; // Example answer from testing
  exampleQuotes?: Quote[]; // Example quotes from testing
}

export interface Agent {
  id: string;
  name: string;
  description?: string;
  reportTemplate: string; // mandatory for all agents
  questions: Question[];
}

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  status: 'queued' | 'uploading' | 'uploaded' | 'failed' | 'duplicate';
  error?: string;
  progress?: number; // Upload progress percentage (0-100)
  abortController?: AbortController; // For cancelling uploads
  queuePosition?: number; // Position in upload queue
}

export interface Template {
  html: string;
  name: string;
}

export interface WordSpan {
  text: string;
  bbox: [number, number, number, number]; // [x0, y0, x1, y1] normalized [0,1]
  page: number;
  confidence: number;
  line_index?: number;
  word_index?: number;
}

export interface Quote {
  id: string;
  index: number;
  chunk_id: string;
  document_id: string;
  text: string;
  page_range: string;
  relevance_score: number;
  has_bounding_boxes?: boolean;
  word_spans?: WordSpan[];
}

export interface ReportAnswer {
  id: string;
  placeholder: string;
  question: string;
  answer: string;
  quotes: Quote[];
  word_count: number;
  error?: string;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  pages: number[];
  chunk_count: number;
  storage_path?: string;  // Supabase Storage path
  content_hash?: string;  // SHA-256 hash for verification
}

export interface DocumentContext {
  document_ids: string[];
  documents: { [id: string]: DocumentInfo };
  total_documents: number;
  total_pages: number;
  total_chunks: number;
}

export interface ReportData {
  template: Template;
  answers: { [placeholder: string]: ReportAnswer };
  quotes: Quote[];
  document_context: DocumentContext;
  generated_at: string;
}

export interface PageInfo {
  page_number: number;
  start_position: number;
  end_position: number;
  content_length: number;
}

export interface DocumentContent {
  document_id: string;
  filename: string;
  full_text: string;
  pages: PageInfo[];
  total_pages: number;
  total_characters: number;
  metadata: {
    size: number;
    type: string;
    processing_stats: Record<string, unknown>;
  };
}

// Audit Trail Types
export interface AuditChange {
  id: string;
  change_type: 'insert' | 'delete';
  text_content: string;
  start_offset: number;
  end_offset: number;
  user_name: string;
  created_at: string;
  answer_placeholder: string;
}

export interface ReportWithAudit {
  report_id: string;
  report_name: string;
  agent_name: string;
  report_data: ReportData;
  changes: Record<string, AuditChange[]>;  // keyed by answer placeholder
  has_changes: boolean;
}

export type ReportViewMode = 'normal' | 'audit';

export interface DocumentBoundingBoxes {
  document_id: string;
  filename: string;
  bounding_boxes: {
    pages: {
      [pageNumber: string]: {
        page_number: number;
        width: number;
        height: number;
        words: Array<{
          text: string;
          bbox: [number, number, number, number];
          confidence: number;
          line_index: number;
          word_index: number;
        }>;
      };
    };
  };
}

// Email Ingest Types
export interface EmailIngestEndpoint {
  id: string;
  full_address: string;  // e.g., "u_abc123@in.attenly.ca"
  is_active: boolean;
  default_agent_id?: string;
}

export interface VerifiedSender {
  id: string;
  email: string;
  is_verified: boolean;
  created_at: string;
}

export interface EmailIngestSettings {
  endpoint: EmailIngestEndpoint | null;
  verified_senders: VerifiedSender[];
  usage_summary: {
    jobs_last_24h: number;
    rate_limit: number;
  };
}
