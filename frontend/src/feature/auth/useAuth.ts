import { useEffect, useMemo, useState } from 'react';
import { authClient, type AppSession } from '../../libs/auth';

const urlHasRecovery = () => {
  const q = new URLSearchParams(window.location.search);
  return q.get('type') === 'recovery' || window.location.hash.includes('type=recovery');
};

export function useAuth() {
  const [session, setSession] = useState<AppSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPasswordRecovery, setIsPasswordRecovery] = useState<boolean>(
    urlHasRecovery() || localStorage.getItem('auth:recovery') === '1'
  );

  // keep LS in sync
  useEffect(() => {
    if (isPasswordRecovery) localStorage.setItem('auth:recovery', '1');
    else localStorage.removeItem('auth:recovery');
  }, [isPasswordRecovery]);

  useEffect(() => {
    let mounted = true;

    // Seed session
    authClient.getSession().then(({ data, error }) => {
      if (error) console.warn('Initial session retrieval error:', error);
      if (!mounted) return;
      setSession(data.session);
      setLoading(false);
    });

    // Subscribe once
    const { data: sub } = authClient.onAuthStateChange((event, sess) => {
      if (event === 'PASSWORD_RECOVERY') setIsPasswordRecovery(true);
      if (event === 'SIGNED_OUT') setIsPasswordRecovery(false);

      setSession(sess ?? null);
      setLoading(false);
    });

    // Enforce recovery if URL says so
    if (urlHasRecovery()) setIsPasswordRecovery(true);

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []); // IMPORTANT: no dependency on isPasswordRecovery

  // While recovering, never advertise "authenticated"
  const isAuthenticated = useMemo(
    () => !!session?.user && !isPasswordRecovery,
    [session, isPasswordRecovery]
  );

  const signIn = (email: string, password: string) =>
    authClient.signInWithPassword({ email, password });

  const signInWithToken = (token: string) =>
    authClient.signInWithToken(token);

  const signOut = async () => {
    setLoading(true);
    await authClient.signOut();
    setIsPasswordRecovery(false);
  };

  const clearRecovery = () => setIsPasswordRecovery(false);

  return {
    session,
    user: session?.user ?? null,
    loading,
    isAuthenticated,
    isPasswordRecovery,
    signIn,
    signInWithToken,
    signOut,
    clearRecovery,
  };
}
