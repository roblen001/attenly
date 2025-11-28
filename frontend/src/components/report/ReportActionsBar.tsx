/**
 * ReportActionsBar Component
 *
 * Displays action buttons for the report with mode-specific visibility.
 * Provides different actions based on whether viewing a current report,
 * saved report in normal mode, or saved report in audit mode.
 *
 * @param onDownloadPDF - Function to handle PDF download action (shows modal)
 * @param onSaveReport - Function to handle save report action (shows modal)
 * @param showSaveButton - Whether to show the save report button (for current reports)
 * @param viewMode - Current view mode ('normal' or 'audit')
 * @param onToggleAuditMode - Function to toggle between normal and audit modes (for saved reports)
 */

import React from 'react';
import type { ReportViewMode } from '../../types';
import './ReportActionsBar.css';

interface ReportActionsBarProps {
  onDownloadPDF: () => void;
  onSaveReport: () => void;
  showSaveButton?: boolean;
  viewMode?: ReportViewMode;
  onToggleAuditMode?: () => void;
}

const ReportActionsBar: React.FC<ReportActionsBarProps> = ({ 
  onDownloadPDF, 
  onSaveReport, 
  showSaveButton = true,
  viewMode = 'normal',
  onToggleAuditMode
}) => {
  const isAuditMode = viewMode === 'audit';
  const isSavedReport = onToggleAuditMode !== undefined;

  return (
    <div className="report-actions-bar">
      <div className="actions-content">
        {/* Save button - show for current reports AND saved reports in normal mode */}
        {showSaveButton && !isAuditMode && (
          <button onClick={onSaveReport} className="btn btn-secondary">
            <span className="btn-icon">💾</span>
            {isSavedReport ? 'Save Changes' : 'Save Report'}
          </button>
        )}

        {/* Audit mode toggle - only for saved reports */}
        {isSavedReport && onToggleAuditMode && (
          <button onClick={onToggleAuditMode} className="btn btn-secondary">
            {isAuditMode ? (
              <>
                <span className="btn-icon">👁️</span>
                Exit Audit Mode
              </>
            ) : (
              <>
                <span className="btn-icon">📋</span>
                View Audit Trail
              </>
            )}
          </button>
        )}

        {/* Download button - hidden in audit mode */}
        {!isAuditMode && (
          <button onClick={onDownloadPDF} className="btn btn-primary">
            <span className="btn-icon">⬇️</span>
            Download PDF
          </button>
        )}
      </div>
    </div>
  );
};

export default ReportActionsBar;
