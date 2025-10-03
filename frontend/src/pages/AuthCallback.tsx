import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../libs/supabase';

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();

  // modes: checking -> recovery (show form) -> done/error
  const [mode, setMode] = useState<'checking'|'recovery'|'done'|'error'>('checking');
  const [error, setError] = useState<string | null>(null);
  const [pwd, setPwd] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Listen for PASSWORD_RECOVERY event
    const { data: subscription } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') {
        setMode('recovery');
        return;
      }
      if (session && mode === 'checking') {
        // Normal OAuth/magic-link flow: send the user to the app
        setMode('done');
        navigate('/dashboard', { replace: true });
      }
    });

    // Trigger initial session parse from URL so the event fires
    supabase.auth.getSession().then(({ data: { session }, error: authError }) => {
      if (authError) {
        setError(authError.message);
        setMode('error');
        return;
      }
      if (session && mode === 'checking') {
        // If already authenticated and not recovery, go in
        setMode('done');
        navigate('/dashboard', { replace: true });
      } else if (mode === 'checking') {
        // No session yet; wait for onAuthStateChange or show error if nothing arrives
        // Give a tiny grace period; most cases the event will fire immediately.
        setTimeout(() => {
          if (mode === 'checking') {
            setMode('error');
            setError('No active session. Please request a new link or sign in again.');
          }
        }, 800);
      }
    });

    return () => subscription.subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate]);

  const setNewPassword = async () => {
    try {
      setBusy(true);
      setError(null);
      const { error } = await supabase.auth.updateUser({ password: pwd });
      if (error) throw error;
      setMode('done');
      navigate('/dashboard', { replace: true });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to set password.');
    } finally {
      setBusy(false);
    }
  };

  if (mode === 'recovery') {
    return (
      <div className="auth-callback-container">
        <div className="auth-callback-recovery">
          <h2>Set a new password</h2>
          <input
            type="password"
            className="auth-callback-input"
            placeholder="New password"
            value={pwd}
            onChange={(e) => setPwd(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && pwd && setNewPassword()}
          />
          <button
            className="auth-callback-button"
            onClick={setNewPassword}
            disabled={busy || !pwd}
          >
            {busy ? 'Saving...' : 'Save password & continue'}
          </button>
          {error && <p className="auth-callback-error-text">{error}</p>}
        </div>
      </div>
    );
  }

  if (mode === 'checking') {
    return (
      <div className="auth-callback-container">
        <div className="auth-callback-loading">
          <div className="spinner" />
          <p>Processing authentication…</p>
        </div>
      </div>
    );
  }

  if (mode === 'error') {
    return (
      <div className="auth-callback-container">
        <div className="auth-callback-error">
          <h2>Authentication Error</h2>
          <p>{error ?? 'Something went wrong.'}</p>
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

  return null; // 'done' just navigates away
};

export default AuthCallback;
