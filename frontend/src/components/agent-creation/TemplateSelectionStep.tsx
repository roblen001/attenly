// TemplateSelectionStep.tsx
import React, { useRef, useState } from 'react';
import './TemplateSelectionStep.css';
import { api } from '../../libs/https';
import type { TemplateIngestResponse } from '../../types';

interface TemplateSelectionStepProps {
  onBack: () => void;
  onSelectScratch: () => void;
  onSelectTemplate: (htmlContent: string, cssContent: string, source: string) => void;
  onProcessingStart: () => void;
  onProcessingEnd: () => void;
}

const TemplateSelectionStep: React.FC<TemplateSelectionStepProps> = ({
  onBack,
  onSelectScratch,
  onSelectTemplate,
  onProcessingStart,
  onProcessingEnd,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const handleTemplateUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    const validExtensions = ['.docx', '.pdf', '.html', '.htm'];
    const fileName = file.name.toLowerCase();
    const isValidType = validExtensions.some(ext => fileName.endsWith(ext));

    if (!isValidType) {
      setError('Please select a valid template file (.docx, .pdf, or .html)');
      return;
    }

    setIsProcessing(true);
    setError(null);
    setWarnings([]);
    onProcessingStart(); // Show full-screen loading state

    try {
      // Create FormData for file upload
      const formData = new FormData();
      formData.append('file', file);

      // Call the backend template upload endpoint
      const response = await api('/agents/template/upload', {
        method: 'POST',
        body: formData,
      });

      const result: TemplateIngestResponse = await response.json();

      if (!result.success) {
        setError(result.error || 'Failed to process template file');
        onProcessingEnd(); // Hide loading state on error
        return;
      }

      // Show warnings if any (e.g., Mammoth fallback)
      if (result.warnings && result.warnings.length > 0) {
        setWarnings(result.warnings);
      }

      // Log the source for debugging
      console.log(`Template ingested successfully via ${result.source}`);

      // Pass HTML and CSS to parent component
      onSelectTemplate(result.html_body, result.css, result.source);
      onProcessingEnd(); // Hide loading state on success
    } catch (err) {
      console.error('Template upload error:', err);
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to upload template. Please try again.'
      );
      onProcessingEnd(); // Hide loading state on error
    } finally {
      setIsProcessing(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleUploadClick = () => {
    if (!isProcessing) {
      fileInputRef.current?.click();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent, action: () => void) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      action();
    }
  };

  return (
    <div className="template-selection-step">
      <div className="step-header">
        <h2>Choose Your Starting Point</h2>
        <p>
          Start with a blank template or upload your own from your existing company workflows (DOCX, PDF, or HTML, max 2 pages).
        </p>
      </div>

      {error && (
        <div className="template-error-message">
          <span className="error-icon">!</span>
          <span className="error-text">{error}</span>
          <button
            onClick={() => setError(null)}
            className="error-dismiss"
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="template-warning-message">
          <span className="warning-icon">⚠</span>
          <div className="warning-text">
            {warnings.map((warning, idx) => (
              <div key={idx}>{warning}</div>
            ))}
          </div>
          <button
            onClick={() => setWarnings([])}
            className="warning-dismiss"
            aria-label="Dismiss warnings"
          >
            &times;
          </button>
        </div>
      )}

      <div className="template-options">
        {/* Option 1: Create from Scratch */}
        <div
          className="template-option-card"
          onClick={onSelectScratch}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => handleKeyDown(e, onSelectScratch)}
          aria-label="Create template from scratch"
        >
          <div className="option-icon-wrapper scratch-icon">
            <span className="option-icon">+</span>
          </div>
          <h3>Create from Scratch</h3>
          <p>
            Start with a blank canvas and build your template using our rich text
            editor with full formatting controls.
          </p>
          <div className="option-features">
            <span className="feature-tag">Full Control</span>
            <span className="feature-tag">Rich Editor</span>
          </div>
        </div>

        {/* Option 2: Upload Template */}
        <div
          className={`template-option-card ${isProcessing ? 'converting' : ''}`}
          onClick={handleUploadClick}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => handleKeyDown(e, handleUploadClick)}
          aria-label="Upload template file"
          aria-busy={isProcessing}
        >
          <div className="option-icon-wrapper upload-icon">
            <span className="option-icon">📄</span>
          </div>
          <h3>Upload Your Template</h3>
          <p>
            {isProcessing
              ? 'Normalizing your template...'
              : 'Upload DOCX, PDF, or HTML template (max 2 pages) to get started quickly.'}
          </p>
          <div className="option-features">
            <span className="feature-tag">AI-Powered</span>
            <span className="feature-tag">Multi-Format</span>
            <span className="feature-tag">2-Page Limit</span>
          </div>
          {isProcessing && <div className="converting-spinner" />}
        </div>
      </div>

      {/* Hidden file input for template upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".docx,.pdf,.html,.htm,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf,text/html"
        onChange={handleTemplateUpload}
        style={{ display: 'none' }}
        aria-hidden="true"
      />

      <div className="step-actions">
        <button className="btn-secondary" onClick={onBack}>
          Back
        </button>
      </div>
    </div>
  );
};

export default TemplateSelectionStep;
