import { useState } from 'react';
import './UsageInstructions.css';

type UsageInstructionsProps = {
  deliveryMode?: 'graph_mailbox' | 'generated_alias' | null;
  deliveryAddress?: string | null;
};

export default function UsageInstructions({
  deliveryMode,
  deliveryAddress,
}: UsageInstructionsProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const usesGraphMailbox = deliveryMode === 'graph_mailbox';
  const exampleAddress = deliveryAddress || (
    usesGraphMailbox ? 'attenly@company.com' : 'u_abc123@mail.attenly.example'
  );

  return (
    <div className="settings-card usage-instructions">
      <div className="card-header-section">
        <h2>How to Use Email to Attenly</h2>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="btn btn-text"
        >
          {isExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {isExpanded && (
        <div className="instructions-content">
          <div className="instruction-step">
            <div className="step-number">1</div>
            <div className="step-content">
              <h3>Enable Email Ingest</h3>
              <p>
                {usesGraphMailbox
                  ? 'Enable email ingest to connect the configured Microsoft 365 mailbox to this workspace.'
                  : 'Enable email ingest to generate the address assigned to this workspace.'}
              </p>
            </div>
          </div>

          <div className="instruction-step">
            <div className="step-number">2</div>
            <div className="step-content">
              <h3>Add Verified Senders</h3>
              <p>
                Add the addresses allowed to submit documents. Each sender must click the verification link emailed to them.
              </p>
              <p className="note">
                <strong>Note:</strong> Verification links expire after 24 hours. You can resend one if needed.
              </p>
            </div>
          </div>

          <div className="instruction-step">
            <div className="step-number">3</div>
            <div className="step-content">
              <h3>Send Emails with Attachments</h3>
              <p>
                Send the documents to <strong>{exampleAddress}</strong>. Attenly processes the attachments with the selected default agent and emails a report-ready link to the sender.
              </p>
              {usesGraphMailbox && (
                <p className="note">
                  <strong>Microsoft Graph:</strong> This single-workspace setup uses the configured mailbox directly. You do not need to create the generated internal endpoint as a Microsoft 365 alias.
                </p>
              )}
              <div className="requirements-box">
                <h4>Supported File Types</h4>
                <ul className="file-types-list">
                  <li><strong>Documents:</strong> PDF, DOCX, TXT</li>
                  <li><strong>Images:</strong> PNG, JPG, JPEG, GIF, WEBP</li>
                </ul>
              </div>
              <div className="requirements-box">
                <h4>File Limits</h4>
                <ul className="limits-list">
                  <li>Maximum 10 attachments per email</li>
                  <li>Maximum 25MB per file</li>
                  <li>Maximum 50MB total per email</li>
                </ul>
              </div>
              <div className="requirements-box warning">
                <h4>Important Notes</h4>
                <ul className="notes-list">
                  <li>Unsupported attachment types are ignored</li>
                  <li>Emails with no supported attachments are not processed</li>
                  <li>Only emails from verified senders are accepted</li>
                </ul>
              </div>
            </div>
          </div>

          <div className="example-section">
            <h3>Example Email</h3>
            <div className="example-email">
              <div className="example-header">
                <div className="example-row">
                  <span className="example-label">From:</span>
                  <span>alice@company.com (verified sender)</span>
                </div>
                <div className="example-row">
                  <span className="example-label">To:</span>
                  <span>{exampleAddress}</span>
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
                <p>Create a policy summary report.</p>
              </div>
            </div>
            <div className="example-result">
              <span>Attenly processes the attachments and generates the report automatically.</span>
            </div>
          </div>

          <div className="help-footer">
            <p>
              <strong>Need Help?</strong> Ask the administrator responsible for this Attenly deployment.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
