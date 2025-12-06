/**
 * ReportContent Component
 * 
 * Displays the main report content with interactive elements.
 * Handles click events for editing answers and viewing quotes.
 * Supports audit trail mode with track changes visualization.
 * 
 * @param reportData - The report data containing template and answers
 * @param onAnswerEdit - Function to handle answer editing
 * @param onQuoteClick - Function to handle quote/superscript clicks
 * @param auditMode - Whether to display in audit trail mode
 * @param auditChanges - Changes to display in audit mode (keyed by placeholder)
 */

import React, { useEffect, useMemo } from 'react';
import type { ReportData, ReportAnswer, AuditChange } from '../../types';
import { generatePopulatedHTML, escapeHtml } from '../../utils/reportUtils';
import { decorateWithAuditSpans } from '../../utils/auditDecorator';
import './ReportContent.css';

interface ReportContentProps {
  reportData: ReportData;
  onAnswerEdit: (answer: ReportAnswer) => void;
  onQuoteClick: (quoteIndex: number) => void;
  viewMode: 'editable' | 'readonly' | 'audit';
  auditChanges?: Record<string, AuditChange[]>;
}

const ReportContent: React.FC<ReportContentProps> = ({
  reportData,
  onAnswerEdit,
  onQuoteClick,
  viewMode,
  auditChanges = {}
}) => {
  // Add click event listeners for quote and edit interactions
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
      
      // Handle answer editing clicks ONLY in editable mode
      if (viewMode === 'editable') {
        if (target.classList.contains('answer-editable') || target.closest('.answer-editable')) {
          // Don't trigger edit if clicking on a superscript
          if (target.classList.contains('quote-superscript') || target.closest('.quote-superscript')) {
            return;
          }
          
          e.preventDefault();
          e.stopPropagation();
          
          const answerElement = target.classList.contains('answer-editable') 
            ? target 
            : target.closest('.answer-editable');
          
          if (answerElement) {
            const answerId = answerElement.getAttribute('data-answer-id');
            if (answerId) {
              // Find the answer by ID
              const answer = Object.values(reportData.answers).find(a => a.id === answerId);
              if (answer) {
                // Check if this is a granular edit (list item or table cell)
                const listIndex = answerElement.getAttribute('data-list-index');
                const tableRow = answerElement.getAttribute('data-table-row');
                const tableCol = answerElement.getAttribute('data-table-col');
                
                if (listIndex !== null) {
                  // Editing a specific list item
                  const index = parseInt(listIndex, 10);
                  const listAnswer = Array.isArray(answer.answer) ? answer.answer : [];
                  if (listAnswer[index] !== undefined) {
                    // Filter quotes to only those targeting this specific list item
                    // If quotes don't have target metadata yet, show all quotes as fallback
                    const filteredQuotes = answer.quotes.filter(q => {
                      const target = (q as any).target;
                      return target?.type === 'list' && target?.index === index;
                    });
                    
                    const modifiedAnswer: ReportAnswer & { _editMetadata?: any } = {
                      ...answer,
                      answer: String(listAnswer[index]), // Extract the specific item
                      quotes: filteredQuotes,  // Only show quotes for this item
                      _editMetadata: {
                        type: 'list',
                        listIndex: index,
                        originalAnswer: listAnswer
                      }
                    };
                    onAnswerEdit(modifiedAnswer);
                  }
                } else if (tableRow !== null && tableCol !== null) {
                  // Editing a specific table cell
                  const row = parseInt(tableRow, 10);
                  const col = tableCol;
                  const tableAnswer = Array.isArray(answer.answer) ? answer.answer : [];
                  if (tableAnswer[row] && tableAnswer[row][col] !== undefined) {
                    // Filter quotes to only those targeting this specific table cell
                    // If quotes don't have target metadata yet, show all quotes as fallback
                    const filteredQuotes = answer.quotes.filter(q => {
                      const target = (q as any).target;
                      return target?.type === 'table' && target?.row === row && target?.key === col;
                    });
                    
                    const modifiedAnswer: ReportAnswer & { _editMetadata?: any } = {
                      ...answer,
                      answer: String(tableAnswer[row][col]), // Extract the specific cell value
                      quotes: filteredQuotes,  // Only show quotes for this cell
                      _editMetadata: {
                        type: 'table',
                        tableRow: row,
                        tableCol: col,
                        originalAnswer: tableAnswer
                      }
                    };
                    onAnswerEdit(modifiedAnswer);
                  }
                } else {
                  // Regular string answer editing
                  onAnswerEdit(answer);
                }
              }
            }
          }
          return;
        }
      }
    };

    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [reportData, onAnswerEdit, onQuoteClick, viewMode]);

  // Generate populated HTML with appropriate styling based on view mode
  const content = useMemo(() => {
    // Get questions from template for answer_type metadata
    const questions = reportData.template.questions || [];
    
    // First, generate the base populated HTML with questions metadata
    const baseHTML = generatePopulatedHTML(reportData.template.html, reportData.answers, questions);
    
    // Determine CSS class based on view mode
    let answerClass = 'answer-content';
    if (viewMode === 'editable') {
      answerClass = 'answer-editable';
    } else if (viewMode === 'readonly') {
      answerClass = 'answer-readonly';
    } else if (viewMode === 'audit') {
      answerClass = 'answer-audit';
    }
    
    // Apply view mode class to all answer spans
    let styledHTML = baseHTML;
    
    // Replace the default class from generatePopulatedHTML with our view mode class
    // The generatePopulatedHTML function wraps answers in spans with data-answer-id
    styledHTML = styledHTML.replace(
      /class="editable-answer"/g,
      `class="${answerClass}"`
    );
    
    // If in audit mode, apply track change decorations using the decorator utility
    if (viewMode === 'audit' && Object.keys(auditChanges).length > 0) {
      console.log('[ReportContent] Entering audit mode rendering');
      
      // Apply audit decorations to each answer with changes
      Object.entries(reportData.answers).forEach(([placeholder, answer]) => {
        const changes = auditChanges[placeholder];
        
        if (!changes || changes.length === 0) {
          return; // Skip answers with no changes
        }
        
        console.log(`[ReportContent] Processing answer ${placeholder} with ${changes.length} changes`);
        
        // Find the answer content in the HTML using data-answer-id
        const answerIdPattern = new RegExp(
          `<span class="${answerClass}"[^>]*data-answer-id="${answer.id}"[^>]*>(.*?)</span>`,
          'gs'
        );
        
        styledHTML = styledHTML.replace(answerIdPattern, (matchedSpan, capturedContent) => {
          // Use the plain text version provided by backend (guaranteed to match diff offsets)
          // This is the same text that was used to compute the diff on the backend
          const answerWithPlain = answer as ReportAnswer & { answer_plain?: string };
          const plainText = answerWithPlain.answer_plain || answer.answer || '';
          
          console.log(`[ReportContent] Matched span for ${placeholder}`);
          console.log(`[ReportContent] Captured content: ${capturedContent}`);
          console.log(`[ReportContent] Using answer_plain: ${plainText} (len=${plainText.length})`);
          
          // Extract superscripts from captured content to preserve them
          const superscriptPattern = /<sup[^>]*class="quote-superscript"[^>]*>.*?<\/sup>/g;
          const superscripts = capturedContent.match(superscriptPattern) || [];
          const superscriptsHTML = superscripts.join('');
          
          console.log(`[ReportContent] Extracted ${superscripts.length} superscripts to preserve`);
          
          // Use the decorator utility for logging and validation
          decorateWithAuditSpans(plainText, changes);
          
          // Build decorated HTML string with audit trail spans
          let decoratedContent = '';
          const sortedChanges = [...changes].sort((a, b) => a.start_offset - b.start_offset);
          let currentPosition = 0;
          let lastProcessedOffset = -1;
          
          for (const change of sortedChanges) {
            // Add unchanged text before this change, but only if we haven't already processed this offset
            // This prevents duplication when DELETE and INSERT occur at the same position
            if (currentPosition < change.start_offset && lastProcessedOffset < change.start_offset) {
              const unchangedText = plainText.substring(currentPosition, change.start_offset);
              decoratedContent += unchangedText;
              lastProcessedOffset = change.start_offset;
              currentPosition = change.start_offset; // Advance position to prevent re-processing this range
            }
            
            if (change.change_type === 'insert') {
              // Insert: text exists in current version
              const changeText = plainText.substring(change.start_offset, change.end_offset);
              const tooltip = escapeHtml(`Added by ${change.user_name} · ${new Date(change.created_at).toLocaleString()}`);
              decoratedContent += `<span class="audit-trail-insert" title="${tooltip}">${escapeHtml(changeText)}</span>`;
              currentPosition = change.end_offset;
            } else {
              // Delete: text doesn't exist in current version
              const tooltip = escapeHtml(`Deleted by ${change.user_name} · ${new Date(change.created_at).toLocaleString()}`);
              decoratedContent += `<span class="audit-trail-delete" title="${tooltip}">${escapeHtml(change.text_content)}</span>`;
              // Don't advance currentPosition for deletes (deleted text not in final string)
            }
          }
          
          // Add remaining unchanged text
          if (currentPosition < plainText.length) {
            decoratedContent += plainText.substring(currentPosition);
          }
          
          // Append the preserved superscripts at the end
          decoratedContent += superscriptsHTML;
          
          // Return the completely new decorated answer span (this replaces matchedSpan entirely)
          return `<span class="${answerClass}" data-answer-id="${answer.id}">${decoratedContent}</span>`;
        });
      });
    }
    
    return <div className="report-html" dangerouslySetInnerHTML={{ __html: styledHTML }} />;
  }, [reportData, viewMode, auditChanges]);

  return (
    <div className="report-main">
      <div className="report-container">
        <div className="report-content">
          {content}
        </div>
      </div>
    </div>
  );
};

export default ReportContent;
