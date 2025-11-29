import React, { useState } from 'react';
import type { VerifiedSender } from '../../types';
import { api } from '../../libs/https';
import AddSenderModal from './AddSenderModal';
import './VerifiedSendersList.css';

interface VerifiedSendersListProps {
  senders: VerifiedSender[];
  onUpdate: () => Promise<void>;
}

export default function VerifiedSendersList({ senders, onUpdate }: VerifiedSendersListProps) {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const showSuccess = (message: string) => {
    setSuccessMessage(message);
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  const handleDelete = async (senderId: string, email: string) => {
    if (!window.confirm(`Are you sure you want to remove ${email} from verified senders?`)) {
      return;
    }

    try {
      setDeletingId(senderId);
      setError(null);
      const response = await api(`/email-ingest/verified-senders/${senderId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to delete sender');
      }
      showSuccess(`Removed ${email} from verified senders`);
      await onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete sender');
    } finally {
      setDeletingId(null);
    }
  };

  const handleResend = async (senderId: string, email: string) => {
    try {
      setResendingId(senderId);
      setError(null);
      const response = await api(`/email-ingest/verified-senders/${senderId}/resend`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Failed to resend verification email');
      }
      showSuccess(`Verification email resent to ${email}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resend verification');
    } finally {
      setResendingId(null);
    }
  };

  const getStatusBadge = (sender: VerifiedSender) => {
    if (sender.is_verified) {
      return <span className="status-badge verified">✓ Verified</span>;
    }
    return <span className="status-badge pending">⏳ Pending</span>;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div className="settings-card">
      <div className="card-header-section">
        <h2>Verified Senders</h2>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="btn btn-primary btn-small"
        >
          + Add Sender
        </button>
      </div>

      <p className="help-text">
        Only emails from verified sender addresses will be processed. Each sender must verify their email address.
      </p>

      {error && (
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError(null)} className="close-error">✕</button>
        </div>
      )}

      {successMessage && (
        <div className="success-message">
          <span className="success-icon">✓</span>
          <span>{successMessage}</span>
        </div>
      )}

      {senders.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📭</div>
          <p>No verified senders yet</p>
          <p className="empty-subtext">
            Add an email address to start receiving documents
          </p>
        </div>
      ) : (
        <div className="senders-table">
          <table>
            <thead>
              <tr>
                <th>Email Address</th>
                <th>Status</th>
                <th>Added</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {senders.map((sender) => (
                <tr key={sender.id}>
                  <td className="email-cell">{sender.email}</td>
                  <td>{getStatusBadge(sender)}</td>
                  <td className="date-cell">{formatDate(sender.created_at)}</td>
                  <td className="actions-cell">
                    {!sender.is_verified && (
                      <button
                        onClick={() => handleResend(sender.id, sender.email)}
                        disabled={resendingId === sender.id}
                        className="btn btn-text"
                        title="Resend verification email"
                      >
                        {resendingId === sender.id ? 'Sending...' : '↻ Resend'}
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(sender.id, sender.email)}
                      disabled={deletingId === sender.id}
                      className="btn btn-danger-text"
                      title="Remove sender"
                    >
                      {deletingId === sender.id ? 'Removing...' : '✕ Remove'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddSenderModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSuccess={async (email) => {
          showSuccess(`Verification email sent to ${email}`);
          await onUpdate();
        }}
      />
    </div>
  );
}
