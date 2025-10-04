// AuthCallback.tsx
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../libs/supabase';
import { useAuth } from '../feature/auth/useAuth';
import '../components/AuthGate.css';

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

    // If the hook already says "recovery", force recovery UI immediately
    if (isPasswordRecovery) setMode('recovery');

    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
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
    supabase.auth.getSession().then(({ data, error: authErr }) => {
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
      const { error } = await supabase.auth.updateUser({ password: pwd });
      if (error) throw error;

      setMode('done');
      setTimeout(() => navigate('/dashboard', { replace: true }), 100);
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
            onKeyDown={(e) => e.key === 'Enter' && pwd && setNewPassword()}
          />
          <button className="auth-callback-button" onClick={setNewPassword} disabled={busy || !pwd}>
            {busy ? 'Saving…' : 'Save password & continue'}
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
          <button onClick={() => navigate('/login', { replace: true })} className="auth-callback-button">
            Return to Login
          </button>
        </div>
      </div>
    );
  }

  return null; // 'done' navigates away
};

export default AuthCallback;
