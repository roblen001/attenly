import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
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

  // 🚫 Do not allow access to protected routes during password recovery.
  if (isPasswordRecovery) {
    return <Navigate to="/auth/callback" replace />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export default AuthGate;
