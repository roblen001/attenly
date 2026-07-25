import React from 'react';
import { Navigate, useLocation } from 'react-router';
import { useAuth } from '../feature/auth/useAuth';
import './AuthGate.css';

interface AuthGateProps {
  children: React.ReactNode;
}

const AuthGate: React.FC<AuthGateProps> = ({ children }) => {
  const { isAuthenticated, loading, isPasswordRecovery } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="auth-gate-container">
        <div className="auth-gate-loading">
          <div className="spinner"></div>
          <p>Checking authentication...</p>
        </div>
      </div>
    );
  }

  // While in recovery, allow the callback page to handle the flow.
  if (isPasswordRecovery) {
    if (location.pathname !== '/auth/callback') {
      return <Navigate to="/auth/callback" replace />;
    }
    return <>{children}</>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export default AuthGate;
