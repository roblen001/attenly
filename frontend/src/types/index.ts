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
  status: 'uploading' | 'uploaded' | 'failed';
}
