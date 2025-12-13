import React from 'react';
import { useNavigate } from 'react-router-dom';
import { formatCredits } from '../hooks/useCredits';
import './CreditBlockedModal.css';

interface CreditBlockedModalProps {
  isOpen: boolean;
  onClose: () => void;
  creditsUsed?: number;
  creditsLimit?: number;
  resetDate?: string;
}

export default function CreditBlockedModal({
  isOpen,
  onClose,
  creditsUsed,
  creditsLimit,
  resetDate,
}: CreditBlockedModalProps) {
  const navigate = useNavigate();

  if (!isOpen) {
    return null;
  }

  const formattedResetDate = resetDate
    ? new Date(resetDate).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : 'the 1st of next month';

  const handleViewUsage = () => {
    onClose();
    navigate('/settings?tab=credits');
  };

  return (
    <div className="credit-blocked-overlay" onClick={onClose}>
      <div className="credit-blocked-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          &times;
        </button>

        <div className="modal-icon">!</div>

        <h2 className="modal-title">Monthly Credit Limit Reached</h2>

        <p className="modal-description">
          {creditsUsed !== undefined && creditsLimit !== undefined ? (
            <>You've used all {formatCredits(creditsLimit)} credits for this month.</>
          ) : (
            <>You've reached your monthly credit limit.</>
          )}
        </p>

        <p className="modal-reset-info">
          Your credits will reset on <strong>{formattedResetDate}</strong>.
        </p>

        <div className="modal-actions">
          <button className="btn btn-primary" onClick={handleViewUsage}>
            View Usage Details
          </button>
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
