// TemplateSelectionStep.tsx
import React, { useRef, useState } from 'react';
import mammoth from 'mammoth';
import './TemplateSelectionStep.css';

interface TemplateSelectionStepProps {
  onBack: () => void;
  onSelectScratch: () => void;
  onSelectDocx: (htmlContent: string) => void;
}

const TemplateSelectionStep: React.FC<TemplateSelectionStepProps> = ({
  onBack,
  onSelectScratch,
  onSelectDocx
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isConverting, setIsConverting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDocxUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.toLowerCase().endsWith('.docx')) {
      setError('Please select a valid DOCX file (.docx format only)');
      return;
    }

    setIsConverting(true);
    setError(null);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer }, {
        styleMap: [
          "p[style-name='Heading 1'] => h1:fresh",
          "p[style-name='Heading 2'] => h2:fresh",
          "p[style-name='Heading 3'] => h3:fresh",
          "p[style-name='Title'] => h1:fresh",
          "p[style-name='Subtitle'] => h2:fresh",
        ]
      });

      // Clean up unnecessary styles from mammoth output
      let cleanHtml = result.value
        .replace(/style="[^"]*"/g, '') // Remove inline styles
        .replace(/<span><\/span>/g, '') // Remove empty spans
        .replace(/\s+/g, ' ') // Normalize whitespace
        .trim();

      // Log any warnings from conversion for debugging
      if (result.messages.length > 0) {
        console.log('DOCX conversion messages:', result.messages);
      }

      if (!cleanHtml || cleanHtml.length === 0) {
        setError('The document appears to be empty. Please try a different file.');
        return;
      }

      onSelectDocx(cleanHtml);
    } catch (err) {
      console.error('DOCX conversion error:', err);
      setError('Failed to convert the DOCX file. Please ensure the file is not corrupted and try again.');
    } finally {
      setIsConverting(false);
      // Reset file input so the same file can be selected again if needed
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDocxCardClick = () => {
    if (!isConverting) {
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
          Select how you want to create your report template. You can start with a blank
          canvas or upload an existing Word document as your foundation.
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
            Start with a blank canvas and build your template using our
            rich text editor with full formatting controls.
          </p>
          <div className="option-features">
            <span className="feature-tag">Full Control</span>
            <span className="feature-tag">Rich Editor</span>
          </div>
        </div>

        {/* Option 2: Upload DOCX */}
        <div
          className={`template-option-card ${isConverting ? 'converting' : ''}`}
          onClick={handleDocxCardClick}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => handleKeyDown(e, handleDocxCardClick)}
          aria-label="Upload DOCX template"
          aria-busy={isConverting}
        >
          <div className="option-icon-wrapper docx-icon">
            <span className="option-icon">W</span>
          </div>
          <h3>Upload DOCX Template</h3>
          <p>
            {isConverting
              ? 'Converting your document...'
              : 'Import an existing Word document to use as your template foundation.'
            }
          </p>
          <div className="option-features">
            <span className="feature-tag">Quick Start</span>
            <span className="feature-tag">.docx Format</span>
          </div>
          {isConverting && <div className="converting-spinner" />}
        </div>
      </div>

      {/* Hidden file input for DOCX upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        onChange={handleDocxUpload}
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
