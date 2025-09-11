/**
 * LoadingState Component
 * 
 * Displays a loading state with progress indicators while report data is being fetched.
 * Shows animated loading icon, progress bar, and descriptive text to inform users
 * that their report is being loaded.
 */

import React from 'react';
import './LoadingState.css';

const LoadingState: React.FC = () => {
  return (
    <div className="report-view-page">
      <div className="loading-container">
        <div className="loading-content">
          <div className="loading-icon">📊</div>
          <h3>Loading Report</h3>
          <p>Fetching your generated report...</p>
          <div className="progress-bar">
            <div className="progress-fill"></div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoadingState;
