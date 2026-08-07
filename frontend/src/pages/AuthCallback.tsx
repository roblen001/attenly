// AuthCallback.tsx
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { authClient, isOidcAuthProvider, isTokenAuthProvider } from '../libs/auth';
import { useAuth } from '../feature/auth/useAuth';
import './Login.css';

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const { isPasswordRecovery } = useAuth(); // trust the hook as the primary signal

  // modes: checking -> recovery -> done/error
  const [mode, setMode] = useState<'checking' | 'recovery' | 'done' | 'error'>(
    isPasswordRecovery ? 'recovery' : 'checking'
  );
  const modeRef = useRef(mode);
  useEffect(() => { modeRef.current = mode; }, [mode]);

  const recoveryRef = useRef<boolean>(isPasswordRecovery);
  useEffect(() => { recoveryRef.current = isPasswordRecovery; }, [isPasswordRecovery]);

  const [error, setError] = useState<string | null>(null);
  const [pwd, setPwd] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let timer: number | undefined;

    if (isTokenAuthProvider || isOidcAuthProvider) {
      authClient.getSession().then(({ data, error: authError }) => {
        if (authError) {
          setError(authError.message);
          setMode('error');
          return;
        }
        if (data.session) navigate('/dashboard', { replace: true });
        else navigate('/login', { replace: true });
      });
      return () => undefined;
    }

    // If the hook already says "recovery", force recovery UI immediately
    if (isPasswordRecovery) setMode('recovery');

    const { data: sub } = authClient.onAuthStateChange((event, session) => {
      // If the auth event says recovery, lock into recovery mode
      if (event === 'PASSWORD_RECOVERY') {
        recoveryRef.current = true;
        setMode('recovery');
        return;
      }

      // Only redirect to dashboard when NOT recovering
      if (!recoveryRef.current && session && modeRef.current === 'checking') {
        setMode('done');
        navigate('/dashboard', { replace: true });
      }
    });

    // Prime current session; but never redirect if recovering
    authClient.getSession().then(({ data, error: authErr }) => {
      if (authErr) {
        setError(authErr.message);
        setMode('error');
        return;
      }
      const session = data?.session ?? null;

      if (recoveryRef.current) {
        setMode('recovery'); // force UI even if a session exists
      } else if (session && modeRef.current === 'checking') {
        setMode('done');
        navigate('/dashboard', { replace: true });
      } else if (modeRef.current === 'checking') {
        // Wait briefly for an incoming event; otherwise show an error
        timer = window.setTimeout(() => {
          if (modeRef.current === 'checking') {
            setMode('error');
            setError('No active session. Please request a new link or sign in again.');
          }
        }, 800);
      }
    });

    return () => {
      sub.subscription.unsubscribe();
      if (timer) window.clearTimeout(timer);
    };
  }, [navigate, isPasswordRecovery]);

  const setNewPassword = async () => {
    try {
      setBusy(true);
      setError(null);

      const { error } = await authClient.updateUser({ password: pwd });
      if (error) throw error;

      // Fully sign out (global if supported)
      await authClient.signOut({ scope: 'global' });

      // Clear recovery guard so routes treat this as a normal unauthenticated user
      localStorage.removeItem('auth:recovery');

      setMode('done');
      setTimeout(() => navigate('/login?reset=success', { replace: true }), 50);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to set password.');
    } finally {
      setBusy(false);
    }
  };

  if (mode === 'recovery') {
    return (
      <div className="login-page">
        {/* Hero Background */}
        <div className="login-hero">
          <div className="hero-background">
            <div className="hero-gradient"></div>
            <div className="hero-pattern"></div>
          </div>

          <div className="login-container">
            {/* Branding Section */}
            <div className="login-branding">
              <div className="brand-badge">
                <span className="badge-icon">🏢</span>
                <span>Attenly</span>
              </div>
              <h1 className="brand-title">
                Reset Your <span className="title-highlight">Password</span>
              </h1>
              <p className="brand-description">
                Enter your new password and you'll be redirected to sign in
              </p>
            </div>

            {/* Password Reset Form */}
            <div className="login-form-container">
              <div className="form-header">
                <h2 className="form-title">Set New Password</h2>
                <p className="form-subtitle">
                  Choose a secure password for your account
                </p>
              </div>

              <form onSubmit={(e) => { e.preventDefault(); if (pwd) setNewPassword(); }} className="login-form">
                <div className="form-group">
                  <label htmlFor="newPassword" className="form-label">
                    New Password
                  </label>
                  <input
                    id="newPassword"
                    type="password"
                    value={pwd}
                    onChange={(e) => setPwd(e.target.value)}
                    className="form-input"
                    placeholder="Enter your new password"
                    required
                  />
                </div>

                {error && (
                  <div className="form-message error-message">
                    <span className="message-icon">⚠️</span>
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={busy || !pwd}
                  className="form-submit-btn"
                >
                  {busy ? (
                    <>
                      <span className="loading-spinner"></span>
                      Saving Password...
                    </>
                  ) : (
                    <>
                      <span className="btn-icon">🔐</span>
                      Save Password
                      <span className="btn-arrow">→</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>

        </div>
      </div>
    );
  }

  if (mode === 'checking') {
    return (
      <div className="login-page">
        {/* Hero Background */}
        <div className="login-hero">
          <div className="hero-background">
            <div className="hero-gradient"></div>
            <div className="hero-pattern"></div>
          </div>

          <div className="login-container">
            {/* Branding Section */}
            <div className="login-branding">
              <div className="brand-badge">
                <span className="badge-icon">🏢</span>
                <span>Attenly</span>
              </div>
              <h1 className="brand-title">
                Processing <span className="title-highlight">Authentication</span>
              </h1>
              <p className="brand-description">
                Please wait while we verify your authentication link
              </p>
            </div>

            {/* Loading Display */}
            <div className="login-form-container">
              <div className="form-header">
                <h2 className="form-title">Authenticating</h2>
                <p className="form-subtitle">
                  Verifying your credentials...
                </p>
              </div>

              <div className="login-form" style={{ alignItems: 'center', textAlign: 'center' }}>
                <div className="loading-spinner" style={{ width: '32px', height: '32px', margin: '2rem auto' }}></div>
                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-md)' }}>
                  Processing authentication...
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    );
  }

  if (mode === 'error') {
    return (
      <div className="login-page">
        {/* Hero Background */}
        <div className="login-hero">
          <div className="hero-background">
            <div className="hero-gradient"></div>
            <div className="hero-pattern"></div>
          </div>

          <div className="login-container">
            {/* Branding Section */}
            <div className="login-branding">
              <div className="brand-badge">
                <span className="badge-icon">🏢</span>
                <span>Attenly</span>
              </div>
              <h1 className="brand-title">
                Authentication <span className="title-highlight">Error</span>
              </h1>
              <p className="brand-description">
                Your authentication link may have expired or is invalid
              </p>
            </div>

            {/* Error Display */}
            <div className="login-form-container">
              <div className="form-header">
                <h2 className="form-title">Link Expired</h2>
                <p className="form-subtitle">
                  Please request a new authentication link
                </p>
              </div>

              <div className="login-form">
                <div className="form-message error-message">
                  <span className="message-icon">⚠️</span>
                  {error ?? 'Your authentication link has expired or is invalid. Please request a new one.'}
                </div>

                <button
                  onClick={() => navigate('/login', { replace: true })}
                  className="form-submit-btn"
                >
                  <span className="btn-icon">🔑</span>
                  Return to Login
                  <span className="btn-arrow">→</span>
                </button>
              </div>
            </div>
          </div>

        </div>
      </div>
    );
  }

  return null; // 'done' navigates away
};

export default AuthCallback;
