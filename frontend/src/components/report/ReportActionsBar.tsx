/**
 * ReportActionsBar Component
 *
 * Displays action buttons for the report, including download PDF functionality.
 * Provides a clean interface for report-related actions.
 *
 * @param onDownloadPDF - Function to handle PDF download action (shows modal)
 */

import React from 'react';
import './ReportActionsBar.css';

interface ReportActionsBarProps {
  onDownloadPDF: () => void;
  onSaveReport: () => void;
}

const ReportActionsBar: React.FC<ReportActionsBarProps> = ({ onDownloadPDF, onSaveReport }) => {
  return (
    <div className="report-actions-bar">
      <div className="actions-content">
        <button onClick={onSaveReport} className="btn btn-secondary">
          <span className="btn-icon">💾</span>
          Save Report
        </button>
        <button onClick={onDownloadPDF} className="btn btn-primary">
          <span className="btn-icon">⬇️</span>
          Download PDF
        </button>
      </div>
    </div>
  );
};

export default ReportActionsBar;
