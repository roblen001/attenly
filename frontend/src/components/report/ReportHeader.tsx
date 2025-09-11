/**
 * ReportHeader Component
 * 
 * Displays the report header with title, description, statistics,
 * and back navigation button. Shows document context and data points.
 * 
 * @param reportData - The report data containing template and document context
 * @param onBack - Function to handle navigation back to dashboard
 */

import React from 'react';
import type { ReportData } from '../../types';
import './ReportHeader.css';

interface ReportHeaderProps {
  reportData: ReportData;
  onBack: () => void;
}

const ReportHeader: React.FC<ReportHeaderProps> = ({ reportData, onBack }) => {
  return (
    <div className="report-header">
      <div className="header-content">
        <div className="header-left">
          <button onClick={onBack} className="back-btn">
            <span className="back-icon">←</span>
            Back to Dashboard
          </button>
          <div className="report-info">
            <h1 className="report-title">
              {reportData.template.name}
            </h1>
            <p className="report-description">
              Generated from {reportData.document_context.total_documents} documents • 
              {reportData.document_context.total_pages} pages • 
              {Object.keys(reportData.answers).length} data points
            </p>
          </div>
        </div>
        <div className="report-stats">
          <div className="stat-item">
            <span className="stat-value">{reportData.document_context.total_documents}</span>
            <span className="stat-label">Documents</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{reportData.document_context.total_pages}</span>
            <span className="stat-label">Pages</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{Object.keys(reportData.answers).length}</span>
            <span className="stat-label">Data Points</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReportHeader;
