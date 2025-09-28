/**
 * DownloadModal Component
 *
 * Modal component for PDF download options with references.
 * Allows users to choose between downloading with or without references.
 */

import React from 'react';
import './DownloadModal.css';

interface DownloadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDownloadWithReferences: () => void;
  onDownloadWithoutReferences: () => void;
  isDownloading?: boolean;
}

const DownloadModal: React.FC<DownloadModalProps> = ({
  isOpen,
  onClose,
  onDownloadWithReferences,
  onDownloadWithoutReferences,
  isDownloading = false
}) => {
  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="download-modal-backdrop" onClick={handleBackdropClick}>
      <div className="download-modal">
        <div className="modal-header">
          <h3 className="modal-title">Download PDF Report</h3>
          <button
            className="modal-close-btn"
            onClick={onClose}
            disabled={isDownloading}
          >
            ×
          </button>
        </div>

        <div className="modal-content">
          <p className="modal-description">
            Choose how you would like to download your report:
          </p>

          <div className="download-options">
            <div className="option-card">
              <div className="option-icon">📄</div>
              <h4>Without References</h4>
              <p>Download the report as shown on screen with superscript references.</p>
              <button
                className="option-btn btn-secondary"
                onClick={onDownloadWithoutReferences}
                disabled={isDownloading}
              >
                {isDownloading ? 'Downloading...' : 'Download'}
              </button>
            </div>

            <div className="option-card featured">
              <div className="option-icon">📋</div>
              <h4>With References</h4>
              <p>Download with inline references and a reference section at the end.</p>
              <button
                className="option-btn btn-primary"
                onClick={onDownloadWithReferences}
                disabled={isDownloading}
              >
                {isDownloading ? 'Downloading...' : 'Download'}
              </button>
            </div>
          </div>

          <div className="reference-info">
            <h5>What are references?</h5>
            <p>
              References convert the superscript numbers (¹ ² ³) to square brackets [1] [2] [3]
              and add a reference section at the end of the PDF with document names and page numbers.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DownloadModal;
