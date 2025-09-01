import React, { useState, useEffect } from 'react';
import type { Quote } from '../../types';
import './DocumentViewer.css';

interface DocumentViewerProps {
  quote: Quote;
  onClose: () => void;
}

export default function DocumentViewer({ quote, onClose }: DocumentViewerProps) {
  const [highlightedContent, setHighlightedContent] = useState<string>('');

  useEffect(() => {
    // Process the quote text for display
    const processContent = () => {
      // For now, just display the quote text with highlighting
      // In a real implementation, you would get the full document content
      // and highlight the specific quote within it
      const content = `
        <div class="document-section">
          <div class="section-header">Document Content (${quote.page_range})</div>
          <div class="quote-context">
            <mark class="highlighted-quote">${quote.text}</mark>
          </div>
        </div>
      `;
      
      setHighlightedContent(content);
    };

    processContent();
  }, [quote]);

  useEffect(() => {
    // Scroll to the highlighted quote
    const timer = setTimeout(() => {
      const highlightedElement = document.querySelector('.highlighted-quote');
      if (highlightedElement) {
        highlightedElement.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center' 
        });
      }
    }, 100);

    return () => clearTimeout(timer);
  }, [highlightedContent]);

  return (
    <div className="document-viewer-overlay">
      {/* Header */}
      <div className="document-viewer-header">
        <div className="header-info">
          <h3 className="document-title">
            📄 Source Document
          </h3>
          <p className="document-subtitle">
            Viewing quote from {quote.page_range}
          </p>
        </div>
        <button
          onClick={onClose}
          className="close-button"
        >
          ✕ Close
        </button>
      </div>

      {/* Quote Info */}
      <div className="quote-info-section">
        <div className="quote-info-card">
          <strong className="quote-label">Source Reference:</strong>
          <p className="quote-text">
            "{quote.text}"
          </p>
          <div className="quote-metadata">
            <span className="metadata-item">
              <strong>Page:</strong> {quote.page_range}
            </span>
            <span className="metadata-item">
              <strong>Relevance:</strong> {(quote.relevance_score * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* Document Content */}
      <div className="document-content">
        <div className="content-container">
          <div 
            dangerouslySetInnerHTML={{ __html: highlightedContent }}
            className="document-text"
          />
        </div>
      </div>

      {/* Footer */}
      <div className="document-viewer-footer">
        <button 
          onClick={onClose}
          className="btn btn-secondary"
        >
          Close Viewer
        </button>
      </div>
    </div>
  );
}
