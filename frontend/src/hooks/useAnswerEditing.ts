/**
 * useAnswerEditing Hook
 * 
 * Custom hook for managing answer editing functionality in reports.
 * Handles the state and operations for editing report answers, including
 * opening/closing the edit modal and saving changes.
 * 
 * @param reportData - The current report data
 * @param setReportData - Function to update the report data
 * @returns Object containing editing state and functions for managing answer edits
 */

import { useState } from 'react';
import type { ReportAnswer, ReportData } from '../types';

export const useAnswerEditing = (
  reportData: ReportData | null,
  setReportData: (data: ReportData) => void
) => {
  const [editingAnswer, setEditingAnswer] = useState<ReportAnswer | null>(null);
  const [editedAnswerText, setEditedAnswerText] = useState('');

  const handleEditAnswer = (answer: ReportAnswer) => {
    setEditingAnswer(answer);
    setEditedAnswerText(answer.answer);
  };

  const handleSaveAnswer = () => {
    if (!editingAnswer || !reportData) return;

    // Check if this is a granular edit (list item or table cell)
    const metadata = (editingAnswer as any)._editMetadata;
    
    let updatedAnswer: any;
    
    if (metadata) {
      if (metadata.type === 'list') {
        // Update specific list item
        const newArray = [...metadata.originalAnswer];
        newArray[metadata.listIndex] = editedAnswerText;
        updatedAnswer = newArray;
      } else if (metadata.type === 'table') {
        // Update specific table cell
        const newArray = metadata.originalAnswer.map((row: any, idx: number) => {
          if (idx === metadata.tableRow) {
            return {
              ...row,
              [metadata.tableCol]: editedAnswerText
            };
          }
          return row;
        });
        updatedAnswer = newArray;
      } else {
        // String type (shouldn't have metadata, but handle it)
        updatedAnswer = editedAnswerText;
      }
    } else {
      // Regular string answer editing
      updatedAnswer = editedAnswerText;
    }

    // Calculate word count based on answer type
    // Use regex split with filter to handle multiple spaces, newlines, and empty strings
    const countWords = (text: string): number => {
      return text.split(/\s+/).filter(word => word.length > 0).length;
    };

    let wordCount = 0;
    if (typeof updatedAnswer === 'string') {
      wordCount = countWords(updatedAnswer);
    } else if (Array.isArray(updatedAnswer)) {
      // For arrays, count words across all items
      wordCount = updatedAnswer.reduce((count, item) => {
        if (typeof item === 'string') {
          return count + countWords(item);
        } else if (typeof item === 'object') {
          // For table rows, count words in all cell values
          return count + Object.values(item).reduce((sum: number, val) => {
            return sum + countWords(String(val));
          }, 0);
        }
        return count;
      }, 0);
    }

    // Update the answer in report data
    const updatedAnswers = {
      ...reportData.answers,
      [editingAnswer.placeholder]: {
        ...editingAnswer,
        answer: updatedAnswer,
        word_count: wordCount,
        _editMetadata: undefined  // Remove metadata
      }
    };

    setReportData({
      ...reportData,
      answers: updatedAnswers
    });

    // Close editing modal
    setEditingAnswer(null);
    setEditedAnswerText('');
  };

  const handleCancelEdit = () => {
    setEditingAnswer(null);
    setEditedAnswerText('');
  };

  return {
    editingAnswer,
    editedAnswerText,
    setEditedAnswerText,
    handleEditAnswer,
    handleSaveAnswer,
    handleCancelEdit
  };
};
