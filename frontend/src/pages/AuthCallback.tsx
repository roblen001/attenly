import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../libs/supabase';

const AuthCallback: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const handleAuthCallback = async () => {
      try {
        // Get the session from URL parameters
        const { data, error: authError } = await supabase.auth.getSession();
        
        if (authError) {
          console.error('Auth callback error:', authError);
          setError(authError.message);
          setLoading(false);
          return;
        }

        if (data.session) {
          // Session successfully created, redirect to dashboard
          console.log('Auth callback successful, session created');
          navigate('/dashboard', { replace: true });
        } else {
          // No session found, redirect to login
          console.log('No session found in callback');
          navigate('/login', { replace: true });
        }
      } catch (err) {
        console.error('Unexpected error in auth callback:', err);
        setError('An unexpected error occurred during authentication');
        setLoading(false);
      }
    };

    handleAuthCallback();
  }, [navigate]);

  if (loading) {
    return (
      <div className="auth-callback-container">
        <div className="auth-callback-loading">
          <div className="spinner"></div>
          <p>Processing authentication...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="auth-callback-container">
        <div className="auth-callback-error">
          <h2>Authentication Error</h2>
          <p>{error}</p>
          <button 
            onClick={() => navigate('/login', { replace: true })}
            className="auth-callback-button"
          >
            Return to Login
          </button>
        </div>
      </div>
    );
  }

  return null;
};

export default AuthCallback;
