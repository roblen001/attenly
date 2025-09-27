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

export interface Quote {
  id: string;
  index: number;
  chunk_id: string;
  document_id: string;
  text: string;
  page_range: string;
  relevance_score: number;
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
