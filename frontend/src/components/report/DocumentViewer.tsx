import React, { useState, useEffect } from 'react';
import type { Quote, DocumentContent } from '../../types';
import { api } from '../../libs/https';
import {
  findTextMatch,
  type PageSection,
  type ExtendedQuote,
  type TextMatchResult
} from '../../utils/quoteMatcher';
import './DocumentViewer.css';

interface DocumentViewerProps {
  quote: Quote;
  onClose: () => void;
  reportType?: 'current' | 'saved';
  reportId?: string;
  agentId?: string;
}

export default function DocumentViewer({ 
  quote, 
  onClose, 
  reportType = 'current',
  reportId,
  agentId 
}: DocumentViewerProps) {
  const [processedContent, setProcessedContent] = useState<string>('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDocumentContent = async () => {
      if (!quote.document_id) {
        setError('No document ID available for this quote');
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        
        console.log('Fetching document content for ID:', quote.document_id, 'Report type:', reportType);
        
        let response;
        if (reportType === 'saved' && reportId) {
          // Use saved report document endpoint
          response = await api(`/agents/reports/saved/${reportId}/documents/${quote.document_id}/content`);
        } else {
          // Use current report document endpoint (default)
          response = await api(`/agents/documents/${quote.document_id}/content`);
        }

        if (!response.ok) {
          throw new Error(`Failed to fetch document content: ${response.status}`);
        }
        
        const content: DocumentContent = await response.json();
        
        // Process the full document content
        processFullDocumentContent(content, quote);
        
      } catch (err) {
        console.error('Error fetching document content:', err);
        const errorMessage = err instanceof Error ? err.message : 'Failed to load document content';
        setError(errorMessage);
        
        // Fallback to showing just the quote
        const fallbackContent = `
          <div class="document-section">
            <div class="section-header">Document Content (${quote.page_range})</div>
            <div class="quote-context">
              <div class="error-message">Unable to load full document content</div>
              <mark class="highlighted-quote">${escapeHtml(quote.text)}</mark>
            </div>
          </div>
        `;
        setProcessedContent(fallbackContent);
      } finally {
        setLoading(false);
      }
    };

    fetchDocumentContent();
  }, [quote, reportType, reportId]);

  const processFullDocumentContent = (content: DocumentContent, currentQuote: Quote) => {
    const fullText = content.full_text;
    
    // Use exact_text if available (from new precise quote extraction), otherwise fall back to text
    const extendedQuote = currentQuote as ExtendedQuote;
    const exactTextToHighlight = extendedQuote.exact_text || currentQuote.text.trim();
    const precisePage = extendedQuote.precise_page;
    
    // Parse page sections from the full text - handle both formats
    const pageMarkerRegex = /(?:--- PAGE (\d+) ---|PAGE (\d+))/gi;
    const sections: PageSection[] = [];
    let match;

    while ((match = pageMarkerRegex.exec(fullText)) !== null) {
      if (sections.length > 0) {
        // Complete the previous section
        sections[sections.length - 1].endPosition = match.index;
        sections[sections.length - 1].content = fullText.substring(
          sections[sections.length - 1].startPosition,
          match.index
        ).trim();
      }

      // Get page number from either capture group
      const pageNumber = parseInt(match[1] || match[2]);
      sections.push({
        pageNumber,
        content: '',
        startPosition: match.index + match[0].length,
        endPosition: fullText.length
      });
    }
    
    // Complete the last section
    if (sections.length > 0) {
      sections[sections.length - 1].content = fullText.substring(
        sections[sections.length - 1].startPosition
      ).trim();
    }
    
    setTotalPages(sections.length);
    
    // Set current page based on precise page number if available
    if (precisePage && sections.some(s => s.pageNumber === precisePage)) {
      setCurrentPage(precisePage);
    } else {
      // Fallback: find which page contains the quote text
      const quoteIndex = fullText.toLowerCase().indexOf(exactTextToHighlight.toLowerCase());
      if (quoteIndex !== -1) {
        const quotePage = sections.find(section => 
          quoteIndex >= section.startPosition && quoteIndex < section.endPosition
        );
        if (quotePage) {
          setCurrentPage(quotePage.pageNumber);
        }
      }
    }
    
    // Create the full document HTML with simple quote highlighting
    let highlightedFullText = fullText;
    
    // Use simple word-based matching to find the quote text
    const matchResult: TextMatchResult | null = findTextMatch(fullText, exactTextToHighlight, sections, currentQuote);

    if (matchResult) {
      const beforeQuote = highlightedFullText.substring(0, matchResult.index);
      const quotePart = highlightedFullText.substring(matchResult.index, matchResult.index + matchResult.length);
      const afterQuote = highlightedFullText.substring(matchResult.index + matchResult.length);

      // Simple yellow highlighting without confidence indicators
      highlightedFullText = beforeQuote +
        `<mark class="highlighted-quote" id="highlighted-quote">${escapeHtml(quotePart)}</mark>` +
        afterQuote;

      console.log('Quote successfully matched and highlighted');
    } else {
      console.warn('No match found for quote:', exactTextToHighlight);
    }

    // Convert page markers to simple page separators with anchors (handle both formats)
    highlightedFullText = highlightedFullText.replace(
      /(?:--- PAGE (\d+) ---|PAGE (\d+))/g,
      (match, p1, p2) => `<div class="page-separator" id="page-${p1 || p2}"></div>`
    );
    
    // Escape HTML for the rest of the content (but preserve our highlights and page markers)
    const parts = highlightedFullText.split(/(<mark class="[^"]*"[^>]*>.*?<\/mark>|<div class="page-separator"[^>]*>.*?<\/div>)/);
    const escapedParts = parts.map((part) => {
      if (part.includes('<mark class="') || part.includes('<div class="page-separator"')) {
        return part; // Keep our HTML tags (both highlighted-quote and partial-highlight)
      }
      return escapeHtml(part);
    });
    
    // Display precise page number if available
    const displayPageInfo = precisePage ? `Page ${precisePage}` : currentQuote.page_range;
    
    const finalContent = `
      <div class="document-section">
        <div class="section-header">Full Document Content</div>
        <div class="document-info">
          <p><strong>File:</strong> ${content.filename}</p>
          <p><strong>Total Pages:</strong> ${content.total_pages}</p>
          <p><strong>Quote Location:</strong> ${displayPageInfo}</p>
          ${matchResult?.isExactMatch && extendedQuote.exact_text ? `<p><strong>Exact Quote:</strong> "${escapeHtml(extendedQuote.exact_text)}"</p>` : ''}
        </div>
        <div class="full-document-content">
          ${escapedParts.join('')}
        </div>
      </div>
    `;
    
    setProcessedContent(finalContent);
  };

  const escapeHtml = (text: string): string => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  };

  const scrollToPage = (pageNumber: number) => {
    setCurrentPage(pageNumber);
    const pageElement = document.getElementById(`page-${pageNumber}`);
    if (pageElement) {
      pageElement.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start' 
      });
    }
  };

  const scrollToQuote = () => {
    const quoteElement = document.getElementById('highlighted-quote');
    if (quoteElement) {
      quoteElement.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'center' 
      });
    }
  };

  const goToPreviousPage = () => {
    if (currentPage > 1) {
      scrollToPage(currentPage - 1);
    }
  };

  const goToNextPage = () => {
    if (currentPage < totalPages) {
      scrollToPage(currentPage + 1);
    }
  };

  useEffect(() => {
    // Auto-scroll to the highlighted quote after content is loaded
    if (processedContent && !loading && !error) {
      const timer = setTimeout(() => {
        scrollToQuote();
      }, 500);

      return () => clearTimeout(timer);
    }
  }, [processedContent, loading, error]);

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

      {/* Page Navigation */}
      {!loading && !error && totalPages > 1 && (
        <div className="page-navigation">
          <div className="nav-controls">
            <button 
              onClick={goToPreviousPage}
              disabled={currentPage <= 1}
              className="nav-button"
            >
              ← Previous Page
            </button>
            <span className="page-indicator">
              Page {currentPage} of {totalPages}
            </span>
            <button 
              onClick={goToNextPage}
              disabled={currentPage >= totalPages}
              className="nav-button"
            >
              Next Page →
            </button>
          </div>
          <button 
            onClick={scrollToQuote}
            className="quote-jump-button"
          >
            🎯 Jump to Quote
          </button>
        </div>
      )}


      {/* Document Content */}
      <div className="document-content">
        <div className="content-container">
          {loading ? (
            <div className="loading-state">
              <p>Loading document content...</p>
            </div>
          ) : error ? (
            <div className="error-state">
              <p>Error: {error}</p>
              <div 
                dangerouslySetInnerHTML={{ __html: processedContent }}
                className="document-text"
              />
            </div>
          ) : (
            <div 
              dangerouslySetInnerHTML={{ __html: processedContent }}
              className="document-text"
            />
          )}
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
