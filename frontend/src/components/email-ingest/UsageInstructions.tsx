import React, { useState } from 'react';
import './UsageInstructions.css';

export default function UsageInstructions() {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="settings-card usage-instructions">
      <div className="card-header-section">
        <h2>How to Use Email to Attenly</h2>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="btn btn-text"
        >
          {isExpanded ? '▼ Collapse' : '▶ Expand'}
        </button>
      </div>

      {isExpanded && (
        <div className="instructions-content">
          <div className="instruction-step">
            <div className="step-number">1</div>
            <div className="step-content">
              <h3>Enable Email Ingest</h3>
              <p>
                Click "Enable Email Ingest" to generate your unique email address. This address is private to your account.
              </p>
            </div>
          </div>

          <div className="instruction-step">
            <div className="step-number">2</div>
            <div className="step-content">
              <h3>Add Verified Senders</h3>
              <p>
                Add email addresses that will send documents. Each sender must verify their email address by clicking the verification link sent to them.
              </p>
              <p className="note">
                <strong>Note:</strong> Verification links expire after 24 hours. You can resend if needed.
              </p>
            </div>
          </div>

          <div className="instruction-step">
            <div className="step-number">3</div>
            <div className="step-content">
              <h3>Forward Emails with Attachments</h3>
              <p>
                Forward emails to your Attenly email alias. The system will automatically process attachments and generate reports.
              </p>
              <div className="requirements-box">
                <h4>📎 Supported File Types</h4>
                <ul className="file-types-list">
                  <li><strong>Documents:</strong> PDF, DOCX, TXT</li>
                  <li><strong>Images:</strong> PNG, JPG, JPEG, GIF, WEBP</li>
                </ul>
              </div>
              <div className="requirements-box">
                <h4>📏 File Limits</h4>
                <ul className="limits-list">
                  <li>Maximum 10 attachments per email</li>
                  <li>Maximum 25MB per file</li>
                  <li>Maximum 50MB total per email</li>
                </ul>
              </div>
              <div className="requirements-box warning">
                <h4>⚠️ Important Notes</h4>
                <ul className="notes-list">
                  <li>Unsupported attachment types are ignored</li>
                  <li>Emails with no supported attachments are not processed</li>
                  <li>Only emails from verified senders are accepted</li>
                </ul>
              </div>
            </div>
          </div>

          <div className="instruction-step">
            <div className="step-number">4</div>
            <div className="step-content">
              <h3>Rate Limits</h3>
              <p>
                Your account can process <strong>20 email jobs per 24 hours</strong>. This limit ensures fair usage and optimal performance.
              </p>
              <p className="note">
                Jobs that are discarded (no valid attachments) do not count toward your rate limit.
              </p>
            </div>
          </div>

          <div className="example-section">
            <h3>📧 Example Forwarded Email</h3>
            <div className="example-email">
              <div className="example-header">
                <div className="example-row">
                  <span className="example-label">From:</span>
                  <span>alice@company.com (verified sender)</span>
                </div>
                <div className="example-row">
                  <span className="example-label">To:</span>
                  <span>u_abc123@mail.attenly.ca (your alias)</span>
                </div>
                <div className="example-row">
                  <span className="example-label">Subject:</span>
                  <span>Policy Documents for Review</span>
                </div>
                <div className="example-row">
                  <span className="example-label">Attachments:</span>
                  <span>policy_2024.pdf (2.3 MB), loss_history.pdf (1.8 MB)</span>
                </div>
              </div>
              <div className="example-body">
                <p>Create a 10k filing summary report...</p>
              </div>
            </div>
            <div className="example-result">
              <span className="result-icon">✓</span>
              <span>System processes attachments and generates report automatically</span>
            </div>
          </div>

          <div className="help-footer">
            <p>
              <strong>Need Help?</strong> If you have questions about using Email to Attenly, please contact support.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
