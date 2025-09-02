import React, { useState, useEffect } from 'react';
import type { Quote, DocumentContent } from '../../types';
import { api } from '../../libs/https';
import './DocumentViewer.css';

interface DocumentViewerProps {
  quote: Quote;
  onClose: () => void;
}

interface PageSection {
  pageNumber: number;
  content: string;
  startPosition: number;
  endPosition: number;
}

// Extended Quote interface to include new precise quote extraction fields
interface ExtendedQuote extends Quote {
  exact_text?: string;
  precise_page?: number;
}

export default function DocumentViewer({ quote, onClose }: DocumentViewerProps) {
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
        
        console.log('Fetching document content for ID:', quote.document_id);  
        const response = await api(`/agents/documents/${quote.document_id}/content`);
        
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
  }, [quote]);

  // Common stop words to filter out
  const STOP_WORDS = new Set([
    'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'an', 'a',
    'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
    'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her',
    'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their', 'what', 'which', 'who', 'when', 'where', 'why', 'how'
  ]);

  // Priority-based text matching with exact match first
  const findTextMatch = (fullText: string, searchText: string, pageSections: PageSection[], currentQuote: Quote): { index: number; length: number; isExactMatch: boolean } | null => {
    // Strategy 1: Exact match anywhere in document (HIGHEST PRIORITY)
    const exactIndex = fullText.indexOf(searchText);
    if (exactIndex !== -1) {
      console.log('Found exact match for:', searchText);
      return { index: exactIndex, length: searchText.length, isExactMatch: true };
    }

    // Strategy 2: Page-aware exact match (within specified page)
    const pageExactMatch = findPageAwareExactMatch(fullText, searchText, pageSections, currentQuote);
    if (pageExactMatch) {
      console.log('Found page-aware exact match for:', searchText);
      return { ...pageExactMatch, isExactMatch: true };
    }

    // Strategy 3: Word sequence match (only if exact fails)
    const wordMatch = findWordSequenceMatch(fullText, searchText);
    if (wordMatch) {
      console.log('Found word sequence match for:', searchText);
      return { ...wordMatch, isExactMatch: false };
    }

    // Strategy 4: Multi-word combination (last resort)
    const multiWordMatch = findMultiWordCombination(fullText, searchText);
    if (multiWordMatch) {
      console.log('Found multi-word combination match for:', searchText);
      return { ...multiWordMatch, isExactMatch: false };
    }

    console.warn('No match found for:', searchText);
    return null;
  };

  // Find exact match within the specified page
  const findPageAwareExactMatch = (fullText: string, searchText: string, pageSections: PageSection[], currentQuote: Quote): { index: number; length: number } | null => {
    const extendedQuote = currentQuote as ExtendedQuote;
    let targetPage = extendedQuote.precise_page;

    if (!targetPage) {
      const pageRangeMatch = currentQuote.page_range.match(/(\d+)/);
      if (pageRangeMatch) {
        targetPage = parseInt(pageRangeMatch[1]);
      }
    }

    if (!targetPage) return null;

    // Find the page section
    const targetSection = pageSections.find(section => section.pageNumber === targetPage);
    if (!targetSection) return null;

    // Extract text from the target page
    const pageText = fullText.substring(targetSection.startPosition, targetSection.endPosition);

    // Look for exact match within this page
    const pageIndex = pageText.indexOf(searchText);
    if (pageIndex !== -1) {
      // Convert page-relative index to document-relative index
      return {
        index: targetSection.startPosition + pageIndex,
        length: searchText.length
      };
    }

    return null;
  };

  // Find word sequence allowing for spacing differences
  const findWordSequenceMatch = (fullText: string, searchText: string): { index: number; length: number } | null => {
    const searchWords = searchText.trim().split(/\s+/).filter(word => word.length > 0);
    if (searchWords.length === 0) return null;

    // Create a regex pattern that allows flexible whitespace between words
    const regexPattern = searchWords
      .map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) // Escape special regex chars
      .join('\\s+'); // Allow one or more whitespace characters between words

    const regex = new RegExp(regexPattern, 'gi');
    const match = regex.exec(fullText);

    if (match) {
      return { index: match.index, length: match[0].length };
    }

    return null;
  };



  // Find multi-word combinations (2-3 words together)
  const findMultiWordCombination = (fullText: string, searchText: string): { index: number; length: number } | null => {
    const words = searchText.trim().split(/\s+/).filter(word =>
      word.length > 2 && !STOP_WORDS.has(word.toLowerCase())
    );

    if (words.length < 2) return null;

    // Try 3-word combinations first
    if (words.length >= 3) {
      for (let i = 0; i <= words.length - 3; i++) {
        const combination = words.slice(i, i + 3).join('\\s+');
        const regex = new RegExp(combination, 'gi');
        const match = regex.exec(fullText);
        if (match) {
          return { index: match.index, length: match[0].length };
        }
      }
    }

    // Try 2-word combinations
    for (let i = 0; i <= words.length - 2; i++) {
      const combination = words.slice(i, i + 2).join('\\s+');
      const regex = new RegExp(combination, 'gi');
      const match = regex.exec(fullText);
      if (match) {
        return { index: match.index, length: match[0].length };
      }
    }

    return null;
  };

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
    const matchResult = findTextMatch(fullText, exactTextToHighlight, sections, currentQuote);

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
