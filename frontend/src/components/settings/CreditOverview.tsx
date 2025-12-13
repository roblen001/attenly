import React from 'react';
import type { CreditStatus } from '../../types';
import { formatCredits, getProgressColor } from '../../hooks/useCredits';
import './CreditOverview.css';

interface CreditOverviewProps {
  credits: CreditStatus;
}

export default function CreditOverview({ credits }: CreditOverviewProps) {
  const progressColor = getProgressColor(credits.percentage_used);
  const resetDate = new Date(credits.reset_date);
  const formattedResetDate = resetDate.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });

  const getWarningMessage = () => {
    switch (credits.warning_level) {
      case 'blocked':
        return {
          type: 'error',
          message: "You've reached your monthly credit limit. Your credits will reset on the 1st of next month."
        };
      case 'critical':
        return {
          type: 'warning',
          message: `Warning: You've used over 90% of your monthly credits.`
        };
      case 'warning':
        return {
          type: 'info',
          message: `Note: You've used over 70% of your monthly credits.`
        };
      default:
        return null;
    }
  };

  const warning = getWarningMessage();

  return (
    <div className="credit-overview">
      <div className="credit-header">
        <h3>Credits This Month</h3>
        <span className="credit-percentage" style={{ color: progressColor }}>
          {Math.round(credits.percentage_used)}% used
        </span>
      </div>

      <div className="credit-progress-container">
        <div className="credit-progress-bar">
          <div
            className="credit-progress-fill"
            style={{
              width: `${Math.min(credits.percentage_used, 100)}%`,
              backgroundColor: progressColor
            }}
          />
        </div>
      </div>

      <div className="credit-stats">
        <div className="credit-stat">
          <span className="credit-stat-value">
            {formatCredits(credits.credits_used)} / {formatCredits(credits.credits_limit)}
          </span>
          <span className="credit-stat-label">credits used</span>
        </div>
        <div className="credit-stat">
          <span className="credit-stat-value" style={{ color: progressColor }}>
            {formatCredits(credits.credits_remaining)}
          </span>
          <span className="credit-stat-label">credits remaining</span>
        </div>
      </div>

      <div className="credit-reset-info">
        Resets: {formattedResetDate} ({credits.days_until_reset} days)
      </div>

      {warning && (
        <div className={`credit-warning credit-warning-${warning.type}`}>
          {warning.message}
        </div>
      )}
    </div>
  );
}
