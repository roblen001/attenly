/**
 * ReportInstructions Component
 * 
 * Displays user instructions for interacting with the report.
 * Shows helpful tips on how to edit answers and view source references.
 */

import React from 'react';
import './ReportInstructions.css';

const ReportInstructions: React.FC = () => {
  return (
    <div className="report-instructions">
      <div className="instruction-card">
        <span className="instruction-icon">💡</span>
        <div className="instruction-content">
          <h4>How to use this report</h4>
          <p>Click on any answer to edit it. Click superscript numbers to view source references from your documents.</p>
        </div>
      </div>
    </div>
  );
};

export default ReportInstructions;
