import React from 'react';
import { Link } from 'react-router-dom';
import { useCredits } from '../hooks/useCredits';
import './CreditWarningBanner.css';

export default function CreditWarningBanner() {
  const { credits, loading } = useCredits();

  if (loading || !credits) {
    return null;
  }

  // Only show banner for warning, critical, or blocked states
  if (credits.warning_level === 'normal') {
    return null;
  }

  const getBannerContent = () => {
    switch (credits.warning_level) {
      case 'blocked':
        return {
          type: 'error',
          message: "You've reached your monthly credit limit. Your credits will reset on the 1st of next month.",
        };
      case 'critical':
        return {
          type: 'critical',
          message: `You've used ${Math.round(credits.percentage_used)}% of your monthly credits.`,
        };
      case 'warning':
        return {
          type: 'warning',
          message: `You've used ${Math.round(credits.percentage_used)}% of your monthly credits.`,
        };
      default:
        return null;
    }
  };

  const content = getBannerContent();
  if (!content) {
    return null;
  }

  return (
    <div className={`credit-warning-banner credit-warning-banner-${content.type}`}>
      <span className="banner-icon">
        {content.type === 'error' ? '!' : '!'}
      </span>
      <span className="banner-message">{content.message}</span>
      <Link to="/settings?tab=credits" className="banner-link">
        View usage
      </Link>
    </div>
  );
}
