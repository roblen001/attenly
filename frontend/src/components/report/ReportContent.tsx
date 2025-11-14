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
import { generatePopulatedHTML } from '../../utils/reportUtils';
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
                onAnswerEdit(answer);
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
    // First, generate the base populated HTML
    const baseHTML = generatePopulatedHTML(reportData.template.html, reportData.answers);
    
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
    
    // If in audit mode, apply track change decorations
    if (viewMode === 'audit' && Object.keys(auditChanges).length > 0) {
      // Apply audit decorations to each answer with changes
      Object.entries(reportData.answers).forEach(([placeholder, answer]) => {
        const changes = auditChanges[placeholder];
        
        if (!changes || changes.length === 0) {
          return; // Skip answers with no changes
        }
        
        // Find the answer content in the HTML using data-answer-id
        const answerIdPattern = new RegExp(
          `<span class="${answerClass}"[^>]*data-answer-id="${answer.id}"[^>]*>(.*?)</span>`,
          'gs'
        );
        
        styledHTML = styledHTML.replace(answerIdPattern, (match, answerContent) => {
          // Extract plain text from the answer content for offset calculations
          const tempDiv = document.createElement('div');
          tempDiv.innerHTML = answerContent;
          const plainText = tempDiv.textContent || tempDiv.innerText || '';
          
          // Build decorated content
          let decoratedContent = '';
          const sortedChanges = [...changes].sort((a, b) => a.start_offset - b.start_offset);
          let currentPosition = 0;
          
          for (const change of sortedChanges) {
            // Add unchanged text before this change
            if (currentPosition < change.start_offset) {
              const unchangedText = plainText.substring(currentPosition, change.start_offset);
              decoratedContent += unchangedText;
            }
            
            if (change.change_type === 'insert') {
              // Insert: text exists in current version
              const changeText = plainText.substring(change.start_offset, change.end_offset);
              const tooltip = `Added by ${change.user_name} · ${new Date(change.created_at).toLocaleString()}`;
              decoratedContent += `<span class="audit-trail-insert" title="${tooltip}">${changeText}</span>`;
              currentPosition = change.end_offset;
            } else {
              // Delete: text doesn't exist in current version
              const tooltip = `Deleted by ${change.user_name} · ${new Date(change.created_at).toLocaleString()}`;
              decoratedContent += `<span class="audit-trail-delete" title="${tooltip}">${change.text_content}</span>`;
            }
          }
          
          // Add remaining unchanged text
          if (currentPosition < plainText.length) {
            decoratedContent += plainText.substring(currentPosition);
          }
          
          // Return the decorated answer span
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
