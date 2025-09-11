/**
 * ReportActionsBar Component
 * 
 * Displays action buttons for the report, including download PDF functionality.
 * Provides a clean interface for report-related actions.
 * 
 * @param onDownloadPDF - Function to handle PDF download action
 */

import React from 'react';
import './ReportActionsBar.css';

interface ReportActionsBarProps {
  onDownloadPDF: () => void;
}

const ReportActionsBar: React.FC<ReportActionsBarProps> = ({ onDownloadPDF }) => {
  return (
    <div className="report-actions-bar">
      <div className="actions-content">
        <button onClick={onDownloadPDF} className="btn btn-primary">
          <span className="btn-icon">⬇️</span>
          Download PDF
        </button>
      </div>
    </div>
  );
};

export default ReportActionsBar;
