/**
 * TemplateProcessingLoadingState Component
 * 
 * Displays a full-screen loading state while AI processes/normalizes uploaded templates.
 * Matches the design pattern of other loading screens in the app.
 */

import React from 'react';
import './TemplateProcessingLoadingState.css';

const TemplateProcessingLoadingState: React.FC = () => {
  return (
    <div className="template-processing-loading-page">
      <div className="template-processing-container">
        <div className="template-processing-content">
          <div className="template-processing-icon">🤖</div>
          <h3>Processing Your Template</h3>
          <p>Attenly is normalizing your template into a clean, editable format...</p>
          <div className="progress-bar">
            <div className="progress-fill"></div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TemplateProcessingLoadingState;
