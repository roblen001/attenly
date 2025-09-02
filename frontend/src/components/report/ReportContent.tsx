/**
 * ReportContent Component
 * 
 * Displays the main report content with interactive elements.
 * Handles click events for editing answers and viewing quotes.
 * 
 * @param reportData - The report data containing template and answers
 * @param onAnswerEdit - Function to handle answer editing
 * @param onQuoteClick - Function to handle quote/superscript clicks
 */

import React, { useEffect } from 'react';
import type { ReportData, ReportAnswer } from '../../types';
import { generatePopulatedHTML } from '../../utils/reportUtils';
import './ReportContent.css';

interface ReportContentProps {
  reportData: ReportData;
  onAnswerEdit: (answer: ReportAnswer) => void;
  onQuoteClick: (quoteIndex: number) => void;
}

const ReportContent: React.FC<ReportContentProps> = ({
  reportData,
  onAnswerEdit,
  onQuoteClick
}) => {
  // Add click event listeners for edit and quote interactions
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      
      // Handle superscript clicks FIRST (higher priority)
      if (target.classList.contains('quote-superscript')) {
        e.preventDefault();
        e.stopPropagation();
        const quoteIndex = parseInt(target.getAttribute('data-quote-index') || '0');
        onQuoteClick(quoteIndex);
        return;
      }
      
      // Handle answer editing clicks (only if not a superscript)
      if (target.classList.contains('editable-answer') || target.closest('.editable-answer')) {
        // Don't trigger edit if clicking on a superscript
        if (target.classList.contains('quote-superscript') || target.closest('.quote-superscript')) {
          return;
        }
        
        e.preventDefault();
        e.stopPropagation();
        
        const answerElement = target.classList.contains('editable-answer') 
          ? target 
          : target.closest('.editable-answer');
        
        if (answerElement) {
          const answerId = answerElement.getAttribute('data-answer-id');
          if (answerId) {
            // Find the answer by ID
            const answer = Object.values(reportData.answers).find(a => a.id === answerId);
            if (answer) {
              onAnswerEdit(answer);
            }
          }
        }
        return;
      }
    };

    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [reportData, onAnswerEdit, onQuoteClick]);

  const populatedHTML = generatePopulatedHTML(reportData.template.html, reportData.answers);

  return (
    <div className="report-main">
      <div className="report-container">
        <div className="report-content">
          <div 
            className="report-html"
            dangerouslySetInnerHTML={{ __html: populatedHTML }}
          />
        </div>
      </div>
    </div>
  );
};

export default ReportContent;
