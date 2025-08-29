export interface Question {
  id: string;
  placeholder: string; // tag that will be replaced with the LLM answer
  prompt: string;
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
