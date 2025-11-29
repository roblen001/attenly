import React, { useState } from 'react';
import { api } from '../../libs/https';
import './AddSenderModal.css';

interface AddSenderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (email: string) => Promise<void>;
}

export default function AddSenderModal({ isOpen, onClose, onSuccess }: AddSenderModalProps) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      setError('Please enter an email address');
      return;
    }

    if (!validateEmail(email.trim())) {
      setError('Please enter a valid email address');
      return;
    }

    try {
      setIsSubmitting(true);
      setError('');

      const response = await api('/email-ingest/verified-senders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to add sender');
      }

      await onSuccess(email.trim());
      setEmail('');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add sender');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setEmail('');
      setError('');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="add-sender-modal-overlay">
      <div className="add-sender-modal">
        <div className="modal-header">
          <h3>Add Verified Sender</h3>
          <button
            onClick={handleClose}
            className="close-button"
            disabled={isSubmitting}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-content">
          <div className="form-group">
            <label htmlFor="senderEmail">Email Address</label>
            <input
              id="senderEmail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="example@company.com"
              disabled={isSubmitting}
              autoFocus
            />
            <p className="field-help">
              A verification email will be sent to this address. The link expires in 24 hours.
            </p>
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
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || !email.trim()}
            >
              {isSubmitting ? 'Sending...' : 'Add Sender'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
