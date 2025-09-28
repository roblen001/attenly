import React, { useState } from 'react';
import './SaveReportModal.css';

interface SaveReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (reportName: string) => Promise<void>;
  isSaving: boolean;
}

export default function SaveReportModal({ isOpen, onClose, onSave, isSaving }: SaveReportModalProps) {
  const [reportName, setReportName] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!reportName.trim()) {
      setError('Please enter a report name');
      return;
    }

    try {
      setError('');
      await onSave(reportName.trim());
      setReportName('');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save report');
    }
  };

  const handleClose = () => {
    if (!isSaving) {
      setReportName('');
      setError('');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="save-report-modal-overlay">
      <div className="save-report-modal">
        <div className="modal-header">
          <h3>Save Report</h3>
          <button 
            onClick={handleClose} 
            className="close-button"
            disabled={isSaving}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-content">
          <div className="form-group">
            <label htmlFor="reportName">Report Name</label>
            <input
              id="reportName"
              type="text"
              value={reportName}
              onChange={(e) => setReportName(e.target.value)}
              placeholder="Enter a name for this report..."
              disabled={isSaving}
              autoFocus
            />
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div className="modal-actions">
            <button 
              type="button" 
              onClick={handleClose}
              className="btn btn-secondary"
              disabled={isSaving}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn btn-primary"
              disabled={isSaving || !reportName.trim()}
            >
              {isSaving ? 'Saving...' : 'Save Report'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
