import React, { useState, useEffect } from 'react';
import type { Quote } from '../../types';
import { api } from '../../libs/https';
import DocumentViewer from '../report/DocumentViewer';
import './AITestingModal.css';

interface AITestingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddToTemplate: (question: string, answer: string, quotes: Quote[]) => void;
  agentId?: string;
  existingQuestion?: string;
  existingAnswer?: string;
  existingQuotes?: Quote[];
}

interface TestResult {
  question: string;
  answer: string;
  quotes: Quote[];
  documentContext: {
    total_documents: number;
    document_ids: string[];
    chunks_searched: number;
    filenames: string[];
  };
}

const AITestingModal: React.FC<AITestingModalProps> = ({
  isOpen,
  onClose,
  onAddToTemplate,
  agentId = 'test-agent',
  existingQuestion,
  existingAnswer,
  existingQuotes
}) => {
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Document viewer state
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
  const [showDocumentViewer, setShowDocumentViewer] = useState(false);

  // Pre-populate form when modal opens with existing data
  useEffect(() => {
    if (isOpen && existingQuestion) {
      setCurrentQuestion(existingQuestion);
      
      // If we have existing answer and quotes, show them as test results
      if (existingAnswer) {
        setTestResult({
          question: existingQuestion,
          answer: existingAnswer,
          quotes: existingQuotes || [],
          documentContext: {
            total_documents: 0,
            document_ids: [],
            chunks_searched: 0,
            filenames: []
          }
        });
      }
    }
  }, [isOpen, existingQuestion, existingAnswer, existingQuotes]);

  const handleTestQuestion = async () => {
    if (!currentQuestion.trim()) return;

    setIsLoading(true);
    setError(null);
    setTestResult(null);

    try {
      const response = await api(`/agents/${agentId}/test-question`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: currentQuestion.trim()
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to test question');
      }

      const result = await response.json();
      
      if (result.success) {
        setTestResult({
          question: result.question,
          answer: result.answer,
          quotes: result.quotes || [],
          documentContext: result.document_context
        });
      } else {
        throw new Error('Test failed');
      }

    } catch (err) {
      console.error('Question testing failed:', err);
      let errorMessage = err instanceof Error ? err.message : 'Failed to test question';
      const jsonStartIndex = errorMessage.indexOf('{');
      if (jsonStartIndex !== -1) {
        try {
          const errorPayload = JSON.parse(errorMessage.substring(jsonStartIndex));
          errorMessage = errorPayload.detail || errorPayload.error || errorMessage;
        } catch {
          // Keep the original network error when the response body is not JSON.
        }
      }
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuoteClick = (quote: Quote) => {
    setSelectedQuote(quote);
    setShowDocumentViewer(true);
  };

  const handleCloseDocumentViewer = () => {
    setShowDocumentViewer(false);
    setSelectedQuote(null);
  };

  const handleAddToTemplate = () => {
    if (testResult) {
      onAddToTemplate(testResult.question, testResult.answer, testResult.quotes);
      handleClose();
    }
  };

  const handleClose = () => {
    setCurrentQuestion('');
    setTestResult(null);
    setError(null);
    setSelectedQuote(null);
    setShowDocumentViewer(false);
    onClose();
  };

  const renderQuoteReferences = (answer: string, quotes: Quote[]) => {
    if (!quotes.length) return answer;

    let processedAnswer = answer;
    
    // If the answer doesn't already have references, add them at the end
    if (!processedAnswer.includes('[') && quotes.length > 0) {
      processedAnswer += ' ';
      quotes.forEach((_, i) => {
        processedAnswer += `[${i + 1}]`;
      });
    }

    // Convert [1][2] format to clickable superscripts
    return processedAnswer.replace(/\[(\d+)\]/g, (match, num) => {
      const quoteIndex = parseInt(num) - 1;
      if (quoteIndex < quotes.length) {
        return `<sup class="quote-reference" data-quote-index="${quoteIndex}">${num}</sup>`;
      }
      return match;
    });
  };

  const handleAnswerClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('quote-reference')) {
      const quoteIndex = parseInt(target.getAttribute('data-quote-index') || '0');
      if (testResult && testResult.quotes[quoteIndex]) {
        handleQuoteClick(testResult.quotes[quoteIndex]);
      }
    }
  };

  if (!isOpen) return null;

  // Show document viewer if quote is selected
  if (showDocumentViewer && selectedQuote) {
    return (
      <DocumentViewer
        quote={selectedQuote}
        onClose={handleCloseDocumentViewer}
        reportType="current"
        agentId={agentId}
      />
    );
  }

  return (
    <div className="ai-testing-modal-overlay">
      <div className="ai-testing-modal">
        <div className="ai-testing-modal-header">
          <h3>🤖 Test AI Question</h3>
          <button className="close-btn" onClick={handleClose}>✕</button>
        </div>

        <div className="ai-testing-modal-body">
          <div className="question-section">
            <label htmlFor="test-question">Question to test:</label>
            <textarea
              id="test-question"
              value={currentQuestion}
              onChange={(e) => setCurrentQuestion(e.target.value)}
              placeholder="e.g., What is the total contract value?"
              rows={3}
              className="question-input"
              disabled={isLoading}
            />
            
            <button 
              className="test-btn"
              onClick={handleTestQuestion}
              disabled={!currentQuestion.trim() || isLoading}
            >
              {isLoading ? '🔄 Testing...' : '🧪 Test Question'}
            </button>
          </div>

          {error && (
            <div className="error-section">
              <div className="error-message">
                <strong>Error:</strong> {error}
              </div>
            </div>
          )}

          {testResult && (
            <div className="results-section">
              <div className="result-header">
                <h4>📋 Test Results</h4>
                <div className="document-info">
                  Searched {testResult.documentContext.chunks_searched} chunks across {testResult.documentContext.total_documents} documents
                </div>
              </div>

              <div className="answer-section">
                <h5>Answer:</h5>
                <div 
                  className="answer-content"
                  onClick={handleAnswerClick}
                  dangerouslySetInnerHTML={{ 
                    __html: renderQuoteReferences(testResult.answer, testResult.quotes) 
                  }}
                />
              </div>

              {testResult.quotes.length > 0 && (
                <div className="quotes-section">
                  <h5>References ({testResult.quotes.length}):</h5>
                  <div className="quotes-list">
                    {testResult.quotes.map((quote, index) => (
                      <div 
                        key={index} 
                        className="quote-item"
                        onClick={() => handleQuoteClick(quote)}
                      >
                        <span className="quote-number">[{index + 1}]</span>
                        <span className="quote-text">{quote.text}</span>
                        <span className="quote-source">({quote.page_range})</span>
                      </div>
                    ))}
                  </div>
                  <div className="quotes-help">
                    💡 Click on references above or superscript numbers in the answer to view source documents
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="ai-testing-modal-actions">
          <button className="btn-secondary" onClick={handleClose}>
            Cancel
          </button>
          
          <button 
            className="btn-primary" 
            onClick={handleAddToTemplate}
            disabled={!testResult}
          >
            ✅ Add to Template
          </button>
        </div>
      </div>
    </div>
  );
};

export default AITestingModal;
