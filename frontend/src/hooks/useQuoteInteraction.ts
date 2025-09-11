/**
 * useQuoteInteraction Hook
 * 
 * Custom hook for managing quote/superscript interactions in reports.
 * Handles clicking on quote superscripts to show document viewer with
 * the corresponding quote and source reference.
 * 
 * @param reportData - The current report data containing answers and quotes
 * @returns Object containing quote state and functions for managing quote interactions
 */

import { useState, useCallback } from 'react';
import type { ReportData, Quote } from '../types';

export const useQuoteInteraction = (reportData: ReportData | null) => {
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);
  const [showDocumentViewer, setShowDocumentViewer] = useState(false);

  // Handle quote/superscript click
  const handleQuoteClick = useCallback((quoteIndex: number) => {
    if (!reportData) return;

    // Find the quote by index across all answers
    let currentIndex = 0;
    for (const answer of Object.values(reportData.answers)) {
      for (const quote of answer.quotes) {
        if (currentIndex === quoteIndex) {
          setSelectedQuote(quote);
          setShowDocumentViewer(true);
          return;
        }
        currentIndex++;
      }
    }
  }, [reportData]);

  const handleCloseDocumentViewer = () => {
    setShowDocumentViewer(false);
    setSelectedQuote(null);
  };

  return {
    selectedQuote,
    showDocumentViewer,
    handleQuoteClick,
    handleCloseDocumentViewer
  };
};
