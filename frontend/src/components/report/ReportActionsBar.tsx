/**
 * ReportActionsBar Component
 *
 * Displays action buttons for the report, including download PDF functionality.
 * Provides a clean interface for report-related actions.
 *
 * @param onDownloadPDF - Function to handle PDF download action (shows modal)
 * @param onSaveReport - Function to handle save report action (shows modal)
 * @param showSaveButton - Whether to show the save report button (hidden for saved reports)
 */

import React from 'react';
import './ReportActionsBar.css';

interface ReportActionsBarProps {
  onDownloadPDF: () => void;
  onSaveReport: () => void;
  showSaveButton?: boolean;
}

const ReportActionsBar: React.FC<ReportActionsBarProps> = ({ 
  onDownloadPDF, 
  onSaveReport, 
  showSaveButton = true 
}) => {
  return (
    <div className="report-actions-bar">
      <div className="actions-content">
        {showSaveButton && (
          <button onClick={onSaveReport} className="btn btn-secondary">
            <span className="btn-icon">💾</span>
            Save Report
          </button>
        )}
        <button onClick={onDownloadPDF} className="btn btn-primary">
          <span className="btn-icon">⬇️</span>
          Download PDF
        </button>
      </div>
    </div>
  );
};

export default ReportActionsBar;
