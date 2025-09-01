/**
 * ErrorState Component
 * 
 * Displays error state when report data fails to load.
 * Shows error message and provides navigation back to dashboard.
 * 
 * @param error - The error message to display
 * @param onBack - Function to handle navigation back to dashboard
 */

import React from 'react';
import './ErrorState.css';

interface ErrorStateProps {
  error: string;
  onBack: () => void;
}

const ErrorState: React.FC<ErrorStateProps> = ({ error, onBack }) => {
  return (
    <div className="report-view-page">
      <div className="error-container">
        <div className="error-content">
          <div className="error-icon">❌</div>
          <h3>Error Loading Report</h3>
          <p>{error}</p>
          <button onClick={onBack} className="btn btn-primary">
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};

export default ErrorState;
