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

    // Update the answer in report data
    const updatedAnswers = {
      ...reportData.answers,
      [editingAnswer.placeholder]: {
        ...editingAnswer,
        answer: editedAnswerText,
        word_count: editedAnswerText.split(' ').length
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
